"""Billing models belong to the existing invoices app and tenant boundary."""

from django.db import models
from django.db.models import Q
from django.utils import timezone

from common.base import BaseOrgModel, OrgScopedManager, OrgScopedQuerySet


class BillingQuerySet(OrgScopedQuerySet):
    def select_related(self, *fields):
        qs = super().select_related(*fields)
        deferred = []
        for path in fields:
            if not path:
                continue
            model = self.model
            for part in path.split("__"):
                model = model._meta.get_field(part).related_model
            deferred.extend(
                f"{path}__{f.name}"
                for f in model._meta.fields
                if isinstance(f, models.BinaryField)
            )
        return qs.defer(*deferred) if deferred else qs

    def with_blobs(self):
        return self.defer(None)


class BillingManager(OrgScopedManager.from_queryset(BillingQuerySet)):
    def get_queryset(self):
        fields = [
            f.name for f in self.model._meta.fields if isinstance(f, models.BinaryField)
        ]
        return BillingQuerySet(self.model, using=self._db, hints=self._hints).defer(
            *fields
        )


class ArchivedDocument(models.Model):
    issued_at = models.DateTimeField(null=True, blank=True, editable=False)
    print_snapshot = models.JSONField(default=dict, blank=True, editable=False)
    snapshot_version = models.PositiveSmallIntegerField(default=0, editable=False)
    archived_pdf_clean = models.BinaryField(null=True, editable=False)
    archived_pdf_stamped = models.BinaryField(null=True, editable=False)
    pdf_clean_sha256 = models.CharField(max_length=64, blank=True, editable=False)
    pdf_stamped_sha256 = models.CharField(max_length=64, blank=True, editable=False)

    class Meta:
        abstract = True


class LegalEntity(BaseOrgModel):
    entity_type = models.CharField(
        max_length=3, choices=[("FOP", "ФОП"), ("LLC", "ТОВ")]
    )
    legal_name = models.CharField(max_length=255)
    registration_code = models.CharField(max_length=10)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    vat_status = models.CharField(
        max_length=12,
        choices=[("NON_PAYER", "Без ПДВ"), ("PAYER", "Платник ПДВ")],
        default="NON_PAYER",
    )
    default_vat_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    vat_registration_number = models.CharField(max_length=30, blank=True)
    tax_system_text = models.TextField(blank=True)
    signer_name = models.CharField(max_length=255, blank=True)
    signer_title = models.CharField(max_length=150, blank=True)
    active = models.BooleanField(default=True)
    invoice_prefix = models.CharField(max_length=30, default="РХ-")
    act_prefix = models.CharField(max_length=30, default="АКТ-")
    signature_png = models.BinaryField(null=True, editable=False)
    stamp_png = models.BinaryField(null=True, editable=False)
    signature_sha256 = models.CharField(max_length=64, blank=True, editable=False)
    stamp_sha256 = models.CharField(max_length=64, blank=True, editable=False)
    objects = BillingManager()

    class Meta:
        db_table = "legal_entity"
        ordering = ["legal_name", "id"]
        base_manager_name = "objects"
        indexes = [models.Index(fields=["org", "-created_at"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(default_vat_rate__gte=0, default_vat_rate__lte=100),
                name="legal_entity_valid_vat",
            )
        ]

    def __str__(self):
        return self.legal_name


class LegalEntityBankAccount(BaseOrgModel):
    entity = models.ForeignKey(
        LegalEntity, on_delete=models.PROTECT, related_name="bank_accounts"
    )
    iban = models.CharField(max_length=29)
    bank_name = models.CharField(max_length=255)
    mfo = models.CharField(max_length=6, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "legal_entity_bank_account"
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["org", "-created_at"])]
        constraints = [
            models.UniqueConstraint(
                fields=["org", "entity", "iban"], name="bank_account_unique_iban"
            )
        ]


class DocumentSequence(BaseOrgModel):
    entity = models.ForeignKey(
        LegalEntity, on_delete=models.PROTECT, related_name="sequences"
    )
    kind = models.CharField(
        max_length=7, choices=[("INVOICE", "Invoice"), ("ACT", "Act")]
    )
    last_value = models.PositiveBigIntegerField(default=0)

    class Meta:
        db_table = "billing_document_sequence"
        indexes = [models.Index(fields=["org", "-created_at"])]
        constraints = [
            models.UniqueConstraint(
                fields=["org", "entity", "kind"], name="billing_sequence_unique_kind"
            )
        ]


class ServiceAct(ArchivedDocument, BaseOrgModel):
    invoice = models.ForeignKey(
        "invoices.Invoice", on_delete=models.PROTECT, related_name="service_acts"
    )
    issuer = models.ForeignKey(
        LegalEntity, on_delete=models.PROTECT, related_name="service_acts"
    )
    status = models.CharField(
        max_length=10,
        choices=[
            ("Draft", "Чернетка"),
            ("Issued", "Виписано"),
            ("Cancelled", "Скасовано"),
        ],
        default="Draft",
    )
    number = models.CharField(max_length=50, blank=True, null=True, editable=False)
    issue_date = models.DateField(default=timezone.localdate)
    service_period_start = models.DateField(null=True, blank=True)
    service_period_end = models.DateField(null=True, blank=True)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cancelled_at = models.DateTimeField(null=True, blank=True, editable=False)
    cancellation_reason = models.TextField(blank=True)
    objects = BillingManager()

    class Meta:
        db_table = "service_act"
        ordering = ["-issue_date", "-created_at"]
        base_manager_name = "objects"
        indexes = [
            models.Index(fields=["org", "-created_at"]),
            models.Index(fields=["org", "invoice", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["org", "issuer", "number"],
                condition=Q(status__in=["Issued", "Cancelled"]),
                name="issued_act_unique_number",
            ),
            models.CheckConstraint(
                condition=Q(subtotal__gte=0, tax_amount__gte=0, total_amount__gte=0),
                name="act_nonnegative_amounts",
            ),
        ]


class ServiceActLine(BaseOrgModel):
    act = models.ForeignKey(ServiceAct, on_delete=models.CASCADE, related_name="lines")
    source_line = models.ForeignKey(
        "invoices.InvoiceLineItem", on_delete=models.PROTECT, related_name="act_lines"
    )
    quantity = models.DecimalField(max_digits=18, decimal_places=8)
    name = models.CharField(max_length=500)
    unit = models.CharField(max_length=30)
    net_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    vat_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "service_act_line"
        ordering = ["order", "id"]
        indexes = [models.Index(fields=["org", "-created_at"])]
        constraints = [
            models.UniqueConstraint(
                fields=["act", "source_line"], name="act_unique_source_line"
            ),
            models.CheckConstraint(
                condition=Q(
                    quantity__gt=0,
                    net_amount__gte=0,
                    vat_amount__gte=0,
                    total_amount__gte=0,
                ),
                name="act_line_valid_amounts",
            ),
        ]
