"""Documentation-only serializers for the existing invoice HTTP envelopes."""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter
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

INVOICE_LIST_PARAMETERS = [
    OpenApiParameter("search", OpenApiTypes.STR),
    OpenApiParameter("status", OpenApiTypes.STR),
    *[
        OpenApiParameter(name, OpenApiTypes.UUID)
        for name in ("account", "contact", "opportunity", "assigned_to", "created_by")
    ],
    *[
        OpenApiParameter(name, OpenApiTypes.DATE)
        for name in ("issue_date_gte", "issue_date_lte", "due_date_gte", "due_date_lte")
    ],
    OpenApiParameter(
        "sort",
        OpenApiTypes.STR,
        description="created_at, due_date, issue_date, total_amount or status; prefix with - for descending order.",
        default="-created_at",
    ),
    OpenApiParameter("limit", OpenApiTypes.INT),
    OpenApiParameter("offset", OpenApiTypes.INT),
]


class InvoiceWriteRequestSerializer(InvoiceCreateSerializer):
    """Custom fields are parsed by the view outside the runtime serializer."""

    custom_fields = serializers.JSONField(required=False, allow_null=True)

    class Meta(InvoiceCreateSerializer.Meta):
        fields = (*InvoiceCreateSerializer.Meta.fields, "custom_fields")


class InvoiceCreateRequestSerializer(InvoiceWriteRequestSerializer):
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
