"""Two trusted A4 forms. No filesystem or network access through document data."""

from copy import deepcopy
from decimal import Decimal
from importlib.resources import files

from django.template.loader import render_to_string
from weasyprint import CSS, HTML
from weasyprint.text.fonts import FontConfiguration
from weasyprint.urls import URLFetcher, URLFetcherResponse

from .models import LegalEntity

RESOURCE_ROOT = files("invoices").joinpath("templates/invoices/pdf/ua")


class BillingResources(URLFetcher):
    def __init__(self, resources):
        super().__init__()
        self.resources = resources

    def fetch(self, url, headers=None):
        if url not in self.resources:
            raise ValueError("Document resource is not allowed")
        mime = "font/ttf" if url == "billing-asset://font" else "image/png"
        return URLFetcherResponse(url, self.resources[url], {"Content-Type": mime})


def scans_for(entity_id, org_id):
    signature, stamp = (
        LegalEntity.objects.filter(pk=entity_id, org_id=org_id)
        .values_list("signature_png", "stamp_png")
        .get()
    )
    return bytes(signature) if signature else None, bytes(stamp) if stamp else None


def display_money(value):
    return f"{Decimal(value):,.2f}".replace(",", " ").replace(".", ",")


def render_ua_pdf(snapshot, *, signature=None, stamp=None, logo=None):
    resources = {
        "billing-asset://font": RESOURCE_ROOT.joinpath(
            "fonts/DejaVuSans.ttf"
        ).read_bytes()
    }
    if signature:
        resources["billing-asset://signature"] = signature
    if stamp:
        resources["billing-asset://stamp"] = stamp
    if logo:
        resources["billing-asset://logo"] = logo
    d = deepcopy(snapshot)
    for field in ("subtotal", "tax_amount", "total_amount"):
        d[field + "_display"] = display_money(d[field])
    for line in d["lines"]:
        for field in ("unit_price", "net_amount", "vat_amount", "total_amount"):
            line[field + "_display"] = display_money(line[field])
        q = format(Decimal(line["quantity"]), "f")
        line["quantity_display"] = q.rstrip("0").rstrip(".") if "." in q else q
    kind = d["kind"]
    if kind not in ("invoice", "act"):
        raise ValueError("Unknown document kind")
    html = render_to_string(
        "invoices/pdf/ua/" + kind + ".html",
        {
            "d": d,
            "signature": bool(signature),
            "stamp": bool(stamp),
            "logo": bool(logo),
        },
    )
    fonts = FontConfiguration()
    fetcher = BillingResources(resources)
    css = CSS(
        string=RESOURCE_ROOT.joinpath("billing.css").read_text(encoding="utf-8"),
        font_config=fonts,
        url_fetcher=fetcher,
    )
    pdf = HTML(string=html, url_fetcher=fetcher).write_pdf(
        stylesheets=[css], font_config=fonts
    )
    if len(pdf) > 10 * 1024 * 1024:
        raise ValueError("PDF перевищує 10 MiB.")
    return pdf


def invoice_logo(invoice):
    from invoices.models import Invoice

    png = (
        Invoice.objects.filter(pk=invoice.pk, org_id=invoice.org_id)
        .values_list("branding_logo_png", flat=True)
        .get()
    )
    return bytes(png) if png else None


def document_pdf(document, *, variant="clean", actor=None):
    if variant not in ("clean", "stamped"):
        from rest_framework.exceptions import ValidationError

        raise ValidationError({"variant": "Оберіть clean або stamped."})
    if document.issued_at:
        content = (
            type(document)
            .objects.filter(org_id=document.org_id, pk=document.pk)
            .values_list("archived_pdf_" + variant, flat=True)
            .get()
        )
        if not content:
            raise ValueError("Missing archived PDF")
        return bytes(content)
    from .snapshots import document_logo, invoice_snapshot

    if document._meta.model_name == "serviceact":
        from .services import act_snapshot

        snapshot = act_snapshot(document, preview=True)
        logo = invoice_logo(document.invoice)
    else:
        snapshot = invoice_snapshot(document, actor=actor, preview=True)
        logo = document_logo(document)
    signature, stamp = (
        scans_for(document.issuer_id, document.org_id)
        if variant == "stamped"
        else (None, None)
    )
    return render_ua_pdf(snapshot, signature=signature, stamp=stamp, logo=logo)
