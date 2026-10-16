"""Documentation-only serializers for the existing invoice HTTP envelopes."""

from rest_framework import serializers

from common.serializer import (
    AttachmentsSerializer,
    CommentSerializer,
    CustomFieldDefinitionSerializer,
)
from invoices.serializer import (
    InvoiceCreateSerializer,
    InvoiceHistorySerializer,
    InvoiceListSerializer,
    InvoiceSerializer,
)


class InvoiceCreateRequestSerializer(InvoiceCreateSerializer):
    """Create requires account/contact; issuer opts into the Ukrainian form."""

    account_id = serializers.UUIDField(required=True)
    contact_id = serializers.UUIDField(required=True)


class InvoiceMutationResponseSerializer(serializers.Serializer):
    error = serializers.BooleanField()
    message = serializers.CharField()
    invoice = InvoiceSerializer()


class InvoiceListResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = InvoiceListSerializer(many=True)
    totals = serializers.JSONField()


class InvoiceDetailResponseSerializer(serializers.Serializer):
    invoice = InvoiceSerializer()
    attachments = AttachmentsSerializer(many=True)
    comments = CommentSerializer(many=True)
    history = InvoiceHistorySerializer(many=True)
    custom_field_definitions = CustomFieldDefinitionSerializer(many=True)
