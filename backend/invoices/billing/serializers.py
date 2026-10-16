import re
from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from .models import DocumentSequence, LegalEntity, LegalEntityBankAccount
from .validators import BillingParticularsValidationMixin, validate_ua_iban

ENTITY_FIELDS = (
    "id",
    "entity_type",
    "legal_name",
    "registration_code",
    "address",
    "phone",
    "email",
    "city",
    "vat_status",
    "default_vat_rate",
    "vat_registration_number",
    "tax_system_text",
    "signer_name",
    "signer_title",
    "active",
    "invoice_prefix",
    "act_prefix",
    "signature_sha256",
    "stamp_sha256",
)


class LegalEntitySerializer(
    BillingParticularsValidationMixin, serializers.ModelSerializer
):
    class Meta:
        model = LegalEntity
        fields = ENTITY_FIELDS
        read_only_fields = ("id", "signature_sha256", "stamp_sha256")

    def validate(self, attrs):
        instance = self.instance
        for field, kind in [("invoice_prefix", "INVOICE"), ("act_prefix", "ACT")]:
            if field in attrs:
                if not attrs[field] or re.search(r"[\x00-\x1f/\\]", attrs[field]):
                    raise serializers.ValidationError({field: "Некоректний префікс."})
                if (
                    instance
                    and attrs[field] != getattr(instance, field)
                    and instance.sequences.filter(kind=kind, last_value__gt=0).exists()
                ):
                    raise serializers.ValidationError(
                        {field: "Префікс уже використовується."}
                    )
        rate = attrs.get(
            "default_vat_rate", instance.default_vat_rate if instance else Decimal(0)
        )
        status = attrs.get(
            "vat_status", instance.vat_status if instance else "NON_PAYER"
        )
        if not 0 <= rate <= 100 or (status == "NON_PAYER" and rate != 0):
            raise serializers.ValidationError(
                {"default_vat_rate": "Перевірте ставку ПДВ."}
            )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        entity = super().create(validated_data)
        for kind in ("INVOICE", "ACT"):
            DocumentSequence.objects.create(org=entity.org, entity=entity, kind=kind)
        return entity


class BankAccountSerializer(
    BillingParticularsValidationMixin, serializers.ModelSerializer
):
    class Meta:
        model = LegalEntityBankAccount
        fields = ("id", "iban", "bank_name", "mfo", "active")
        read_only_fields = ("id",)
        validators = []

    def validate_iban(self, value):
        value = validate_ua_iban(value)
        entity = self.context.get("entity")
        qs = LegalEntityBankAccount.objects.filter(
            org=entity.org, entity=entity, iban=value
        )
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Цей IBAN уже додано.")
        return value


class ActLineInputSerializer(serializers.Serializer):
    source_line_id = serializers.UUIDField()
    quantity = serializers.DecimalField(
        max_digits=18, decimal_places=8, min_value=Decimal("0.00000001")
    )


class ActInputSerializer(serializers.Serializer):
    invoice_id = serializers.UUIDField(required=False)
    issue_date = serializers.DateField(required=False)
    service_period_start = serializers.DateField(required=False, allow_null=True)
    service_period_end = serializers.DateField(required=False, allow_null=True)
    lines = ActLineInputSerializer(many=True, required=False, allow_empty=False)


class ActCreateRequestSerializer(ActInputSerializer):
    """Document the fields checked by the create view and service."""

    invoice_id = serializers.UUIDField()
    lines = ActLineInputSerializer(many=True, allow_empty=False)


class ServiceActLineSerializer(serializers.ModelSerializer):
    source_line_id = serializers.UUIDField(read_only=True)

    class Meta:
        from .models import ServiceActLine

        model = ServiceActLine
        fields = (
            "id",
            "source_line_id",
            "name",
            "unit",
            "quantity",
            "net_amount",
            "vat_amount",
            "total_amount",
            "order",
        )
        read_only_fields = fields


class ServiceActSerializer(serializers.ModelSerializer):
    invoice_id = serializers.UUIDField(read_only=True)
    issuer_id = serializers.UUIDField(read_only=True)
    vat_status = serializers.CharField(source="invoice.vat_status", read_only=True)
    vat_rate = serializers.DecimalField(
        source="invoice.tax_rate", max_digits=5, decimal_places=2, read_only=True
    )
    issuer_name = serializers.SerializerMethodField()

    def get_issuer_name(self, obj) -> str:
        return obj.invoice.print_snapshot.get("seller", {}).get("legal_name", "")

    lines = ServiceActLineSerializer(many=True, read_only=True)
    invoice_number = serializers.CharField(
        source="invoice.invoice_number", read_only=True
    )

    class Meta:
        from .models import ServiceAct

        model = ServiceAct
        fields = (
            "id",
            "invoice_id",
            "invoice_number",
            "issuer_id",
            "issuer_name",
            "vat_status",
            "vat_rate",
            "status",
            "number",
            "issue_date",
            "service_period_start",
            "service_period_end",
            "subtotal",
            "tax_amount",
            "total_amount",
            "issued_at",
            "cancelled_at",
            "cancellation_reason",
            "lines",
        )
        read_only_fields = fields
