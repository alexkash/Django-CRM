import re
from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from .models import DocumentSequence, LegalEntity, LegalEntityBankAccount

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


class LegalEntitySerializer(serializers.ModelSerializer):
    class Meta:
        model = LegalEntity
        fields = ENTITY_FIELDS
        read_only_fields = ("id", "signature_sha256", "stamp_sha256")

    def validate_registration_code(self, value):
        if not re.fullmatch(r"\d{8}|\d{10}", value):
            raise serializers.ValidationError("Вкажіть код із 8 або 10 цифр.")
        return value

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


class BankAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = LegalEntityBankAccount
        fields = ("id", "iban", "bank_name", "mfo", "active")
        read_only_fields = ("id",)
        validators = []

    def validate_iban(self, value):
        value = value.replace(" ", "").upper()
        if not re.fullmatch(r"UA\d{27}", value):
            raise serializers.ValidationError("IBAN має містити UA та 27 цифр.")
        digits = value[4:] + "3010" + value[2:4]
        if int(digits) % 97 != 1:
            raise serializers.ValidationError("Некоректна контрольна сума IBAN.")
        entity = self.context.get("entity")
        qs = LegalEntityBankAccount.objects.filter(
            org=entity.org, entity=entity, iban=value
        )
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Цей IBAN уже додано.")
        return value

    def validate_mfo(self, value):
        if value and not re.fullmatch(r"\d{6}", value):
            raise serializers.ValidationError("МФО має містити 6 цифр.")
        return value
