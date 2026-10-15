"""Transactions issuing immutable billing documents; no email side effects."""

import hashlib

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from invoices.models import Invoice
from invoices.permissions import get_invoice_or_error

from .models import LegalEntity
from .numbering import next_document_number
from .pdf import render_ua_pdf, scans_for
from .snapshots import invoice_snapshot


def freeze_document(document, snapshot, signature, stamp):
    clean = render_ua_pdf(snapshot, signature=None, stamp=None)
    stamped = render_ua_pdf(snapshot, signature=signature, stamp=stamp)
    document.print_snapshot = snapshot
    document.snapshot_version = 1
    document.archived_pdf_clean, document.archived_pdf_stamped = clean, stamped
    document.pdf_clean_sha256 = hashlib.sha256(clean).hexdigest()
    document.pdf_stamped_sha256 = hashlib.sha256(stamped).hexdigest()
    document.issued_at = timezone.now()


@transaction.atomic
def issue_invoice(*, actor, invoice_id):
    invoice, error = get_invoice_or_error(
        actor, invoice_id, queryset=Invoice.objects.select_for_update()
    )
    if error:
        raise NotFound("Invoice not found")
    if not invoice.issuer_id:
        raise ValidationError("Це не українська форма рахунку.")
    if invoice.issued_at:
        return invoice
    if invoice.status != "Draft":
        raise ValidationError("Випуск дозволено лише з чернетки.")
    # Prefix changes and scan/profile changes use the same entity row lock.
    entity = LegalEntity.objects.select_for_update().get(
        pk=invoice.issuer_id, org_id=invoice.org_id
    )
    invoice.issuer = entity
    if invoice.vat_status != entity.vat_status:
        raise ValidationError(
            {"vat_status": "Статус ПДВ компанії змінився. Оновіть чернетку."}
        )
    invoice.recalculate_totals()
    snapshot = invoice_snapshot(invoice, actor=actor)
    invoice.invoice_number = next_document_number(
        org=actor.profile.org, entity=entity, kind="INVOICE"
    )
    snapshot["number"] = invoice.invoice_number
    signature, stamp = scans_for(entity.pk, invoice.org_id)
    freeze_document(invoice, snapshot, signature, stamp)
    invoice.status = "Sent"
    invoice.reminder_enabled = invoice.public_link_enabled = False
    invoice.save()
    return invoice


# All act mutations use the same parent-first locking order.
def _invoice_for_act(actor, invoice_id):
    invoice, error = get_invoice_or_error(
        actor, invoice_id, queryset=Invoice.objects.select_for_update()
    )
    if error:
        raise NotFound("Invoice not found")
    if not invoice.issuer_id or not invoice.issued_at or invoice.status == "Cancelled":
        raise ValidationError("Для акта потрібен виписаний український рахунок.")
    return invoice


def _locked_act(actor, act_id):
    from .access import visible_acts_qs
    from .models import ServiceAct

    entry = (
        visible_acts_qs(actor.profile)
        .filter(pk=act_id)
        .values("id", "invoice_id")
        .first()
    )
    if not entry:
        raise NotFound("Act not found")
    invoice, error = get_invoice_or_error(
        actor, entry["invoice_id"], queryset=Invoice.objects.select_for_update()
    )
    if error:
        raise NotFound("Act not found")
    act = ServiceAct.objects.select_for_update().get(
        org=actor.profile.org, pk=act_id, invoice=invoice
    )
    act.invoice = invoice
    return act


def _issued_allocations(invoice):
    from django.db.models import Sum

    from .models import ServiceActLine
    from .money import IssuedAllocation

    rows = (
        ServiceActLine.objects.filter(
            org_id=invoice.org_id, act__invoice=invoice, act__status="Issued"
        )
        .values("source_line_id")
        .annotate(q=Sum("quantity"), net=Sum("net_amount"), vat=Sum("vat_amount"))
    )
    return {
        row["source_line_id"]: IssuedAllocation(row["q"], row["net"], row["vat"])
        for row in rows
    }


def get_closure_summary(invoice):
    from decimal import Decimal

    from .money import IssuedAllocation

    issued = _issued_allocations(invoice)
    rows = []
    closed_net = closed_vat = Decimal(0)
    for line in invoice.line_items.order_by("order", "id"):
        current = issued.get(line.pk, IssuedAllocation())
        closed_net += current.net
        closed_vat += current.vat
        rows.append(
            {
                "source_line_id": str(line.pk),
                "name": line.name or line.description,
                "unit": line.unit,
                "unit_price": str(line.unit_price),
                "quantity": str(line.quantity),
                "closed_quantity": f"{current.quantity:.8f}",
                "remaining_quantity": f"{line.quantity - current.quantity:.8f}",
                "remaining_net": f"{line.subtotal - current.net:.2f}",
                "remaining_vat": f"{line.tax_amount - current.vat:.2f}",
            }
        )
    return {
        "closed_net": f"{closed_net:.2f}",
        "closed_vat": f"{closed_vat:.2f}",
        "closed_total": f"{closed_net + closed_vat:.2f}",
        "remaining_net": f"{invoice.subtotal - closed_net:.2f}",
        "remaining_vat": f"{invoice.tax_amount - closed_vat:.2f}",
        "remaining_total": f"{invoice.total_amount - closed_net - closed_vat:.2f}",
        "lines": rows,
    }


def _replace_act_lines(act, line_data):
    from .models import ServiceActLine
    from .money import IssuedAllocation, SourceLineBudget, allocate_act_line

    invoice = act.invoice
    sources = {
        line.pk: line for line in invoice.line_items.filter(org_id=invoice.org_id)
    }
    allocations = _issued_allocations(invoice)
    seen = set()
    pending = []
    for index, data in enumerate(line_data):
        uid = data["source_line_id"]
        if uid in seen or uid not in sources:
            raise ValidationError({"lines": "Позиція недоступна або повторюється."})
        seen.add(uid)
        line = sources[uid]
        try:
            amount = allocate_act_line(
                SourceLineBudget(line.quantity, line.subtotal, line.tax_amount),
                data["quantity"],
                allocations.get(uid, IssuedAllocation()),
            )
        except ValueError as exc:
            raise ValidationError({"lines": str(exc)}) from exc
        pending.append(
            ServiceActLine(
                org_id=invoice.org_id,
                act=act,
                source_line=line,
                quantity=amount.quantity,
                name=line.name or line.description,
                unit=line.unit,
                net_amount=amount.net,
                vat_amount=amount.vat,
                total_amount=amount.total,
                order=index,
            )
        )
    if not pending:
        raise ValidationError({"lines": "Оберіть хоча б одну позицію."})
    act.lines.all().delete()
    ServiceActLine.objects.bulk_create(pending)
    _act_totals(act)


def _act_totals(act):
    from decimal import Decimal

    lines = list(act.lines.all())
    act.subtotal = sum((line.net_amount for line in lines), Decimal(0))
    act.tax_amount = sum((line.vat_amount for line in lines), Decimal(0))
    act.total_amount = act.subtotal + act.tax_amount


@transaction.atomic
def create_act(*, actor, invoice_id, data):
    from .models import ServiceAct

    invoice = _invoice_for_act(actor, invoice_id)
    act = ServiceAct.objects.create(
        org=actor.profile.org,
        invoice=invoice,
        issuer_id=invoice.issuer_id,
        created_by=actor.user,
        **{
            key: data[key]
            for key in ("issue_date", "service_period_start", "service_period_end")
            if key in data
        },
    )
    _replace_act_lines(act, data.get("lines", []))
    act.save()
    return act


@transaction.atomic
def update_act(*, actor, act_id, data):
    act = _locked_act(actor, act_id)
    if act.status != "Draft":
        raise ValidationError("Змінювати можна лише чернетку акта.")
    if data.get("invoice_id", act.invoice_id) != act.invoice_id:
        raise ValidationError({"invoice_id": "Рахунок акта не змінюється."})
    for key in ("issue_date", "service_period_start", "service_period_end"):
        if key in data:
            setattr(act, key, data[key])
    if "lines" in data:
        _replace_act_lines(act, data["lines"])
    act.save()
    return act


def act_snapshot(act, *, preview=False):
    from copy import deepcopy

    from .formatting import amount_in_words_uk

    snapshot = deepcopy(act.invoice.print_snapshot)
    snapshot.update(
        kind="act",
        draft=preview,
        invoice_number=snapshot["number"],
        invoice_date=snapshot["issue_date"],
        number="без номера" if preview else act.number,
        issue_date=act.issue_date.isoformat(),
        service_period_start=act.service_period_start.isoformat()
        if act.service_period_start
        else "",
        service_period_end=act.service_period_end.isoformat()
        if act.service_period_end
        else "",
        subtotal=str(act.subtotal),
        tax_amount=str(act.tax_amount),
        total_amount=str(act.total_amount),
        amount_words=amount_in_words_uk(act.total_amount),
    )
    sources = {str(line.pk): line for line in act.invoice.line_items.all()}
    snapshot["lines"] = [
        {
            "source_line_id": str(line.source_line_id),
            "name": line.name,
            "description": "",
            "unit": line.unit,
            "quantity": str(line.quantity),
            "unit_price": str(sources[str(line.source_line_id)].unit_price),
            "net_amount": str(line.net_amount),
            "vat_amount": str(line.vat_amount),
            "total_amount": str(line.total_amount),
        }
        for line in act.lines.all()
    ]
    entity = LegalEntity.objects.get(pk=act.issuer_id, org_id=act.org_id)
    snapshot.update(
        signature_sha256=entity.signature_sha256, stamp_sha256=entity.stamp_sha256
    )
    return snapshot


@transaction.atomic
def issue_act(*, actor, act_id):
    from datetime import date

    from rest_framework.exceptions import APIException

    from .models import ServiceActLine
    from .money import IssuedAllocation, SourceLineBudget, allocate_act_line
    from .snapshots import validate_period

    act = _locked_act(actor, act_id)
    invoice = act.invoice
    if act.status == "Issued":
        return act
    if act.status != "Draft" or invoice.status == "Cancelled":
        raise ValidationError("Цей акт не можна виписати.")
    validate_period(act.service_period_start, act.service_period_end)
    source_snapshot = invoice.print_snapshot
    if act.service_period_start < date.fromisoformat(
        source_snapshot["service_period_start"]
    ) or act.service_period_end > date.fromisoformat(
        source_snapshot["service_period_end"]
    ):
        raise ValidationError(
            {"service_period": "Період акта має бути в межах періоду рахунку."}
        )
    issued = _issued_allocations(invoice)
    lines = list(act.lines.select_related("source_line"))
    if not lines:
        raise ValidationError({"lines": "Оберіть позиції."})
    for line in lines:
        source = line.source_line
        try:
            part = allocate_act_line(
                SourceLineBudget(source.quantity, source.subtotal, source.tax_amount),
                line.quantity,
                issued.get(source.pk, IssuedAllocation()),
            )
        except ValueError as exc:
            error = APIException("Залишок змінився. Перевірте позиції акта.")
            error.status_code = 409
            raise error from exc
        line.net_amount, line.vat_amount, line.total_amount = (
            part.net,
            part.vat,
            part.total,
        )
    ServiceActLine.objects.bulk_update(
        lines, ["net_amount", "vat_amount", "total_amount"]
    )
    _act_totals(act)
    entity = LegalEntity.objects.select_for_update().get(
        pk=act.issuer_id, org_id=act.org_id
    )
    act.number = next_document_number(org=actor.profile.org, entity=entity, kind="ACT")
    snapshot = act_snapshot(act)
    signature, stamp = scans_for(entity.pk, act.org_id)
    freeze_document(act, snapshot, signature, stamp)
    act.status = "Issued"
    act.save()
    return act


@transaction.atomic
def cancel_act(*, actor, act_id, reason):
    act = _locked_act(actor, act_id)
    if act.status == "Cancelled":
        return act
    if (
        act.status != "Issued"
        or not isinstance(reason, str)
        or not reason.strip()
        or len(reason) > 2000
    ):
        raise ValidationError({"reason": "Вкажіть причину скасування виписаного акта."})
    act.status = "Cancelled"
    act.cancelled_at = timezone.now()
    act.cancellation_reason = reason.strip()
    act.save(
        update_fields=[
            "status",
            "cancelled_at",
            "cancellation_reason",
            "updated_at",
            "updated_by",
        ]
    )
    return act


@transaction.atomic
def delete_act(*, actor, act_id):
    act = _locked_act(actor, act_id)
    if act.status != "Draft":
        raise ValidationError("Видаляти можна лише чернетку.")
    act.delete()


@transaction.atomic
def duplicate_ua_invoice(*, actor, original):
    from copy import deepcopy

    from invoices.models import InvoiceLineItem

    if not original.issuer.active or not original.bank_account.active:
        raise ValidationError("Для нового рахунку оберіть активну компанію та IBAN.")
    issuer = original.issuer
    copied = {
        field: getattr(original, field)
        for field in (
            "account_id",
            "contact_id",
            "opportunity_id",
            "payer_id",
            "client_name",
            "client_email",
            "client_phone",
            "contract_number",
            "contract_date",
            "order_reference",
            "place_of_issue",
            "payment_terms",
            "notes",
            "terms",
        )
    }
    invoice = Invoice.objects.create(
        org=actor.profile.org,
        created_by=actor.user,
        invoice_title="Копія " + original.invoice_title,
        issuer=issuer,
        bank_account=original.bank_account,
        vat_status=issuer.vat_status,
        tax_rate=original.tax_rate if issuer.vat_status == "PAYER" else 0,
        currency="UAH",
        draft_parties=deepcopy(original.draft_parties),
        reminder_enabled=False,
        public_link_enabled=False,
        **copied,
    )
    for line in original.line_items.all():
        InvoiceLineItem.objects.create(
            org=actor.profile.org,
            invoice=invoice,
            product=line.product,
            name=line.name,
            description=line.description,
            quantity=line.quantity,
            unit=line.unit,
            unit_price=line.unit_price,
            tax_rate=invoice.tax_rate,
            order=line.order,
        )
    invoice.recalculate_totals()
    invoice.save()
    return invoice
