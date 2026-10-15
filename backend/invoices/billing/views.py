from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from rest_framework import serializers as schema_fields
from rest_framework.exceptions import (
    MethodNotAllowed,
    PermissionDenied,
    ValidationError,
)
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import HasOrgContext, is_org_admin

from .assets import normalize_scan
from .models import LegalEntity, LegalEntityBankAccount
from .serializers import (
    BankAccountSerializer,
    LegalEntitySerializer,
)


def require_admin(request):
    if not is_org_admin(request.profile):
        raise PermissionDenied()


class BillingView(APIView):
    permission_classes = (IsAuthenticated, HasOrgContext)


@extend_schema_view(
    get=extend_schema(
        responses={
            200: inline_serializer(
                name="LegalEntityPage",
                fields={"results": LegalEntitySerializer(many=True)},
            )
        }
    ),
    post=extend_schema(
        request=LegalEntitySerializer, responses={201: LegalEntitySerializer}
    ),
)
class LegalEntityListView(BillingView):
    serializer_class = LegalEntitySerializer

    def get(self, request):
        rows = LegalEntity.objects.filter(org=request.profile.org)
        return Response({"results": LegalEntitySerializer(rows, many=True).data})

    def post(self, request):
        require_admin(request)
        serializer = LegalEntitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entity = serializer.save(org=request.profile.org, created_by=request.user)
        return Response(LegalEntitySerializer(entity).data, status=201)


class LegalEntityDetailView(BillingView):
    serializer_class = LegalEntitySerializer

    def get(self, request, pk):
        entity = get_object_or_404(
            LegalEntity.objects.filter(org=request.profile.org), pk=pk
        )
        return Response(LegalEntitySerializer(entity).data)

    @transaction.atomic
    def patch(self, request, pk):
        entity = get_object_or_404(
            LegalEntity.objects.select_for_update().filter(org=request.profile.org),
            pk=pk,
        )
        require_admin(request)
        serializer = LegalEntitySerializer(entity, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    put = patch


class BankAccountView(BillingView):
    serializer_class = BankAccountSerializer

    def save_bank(self, serializer, **fields):
        try:
            with transaction.atomic():
                return serializer.save(**fields)
        except IntegrityError as exc:
            raise ValidationError({"iban": "Цей IBAN уже додано."}) from exc

    def entity(self, request, pk):
        return get_object_or_404(
            LegalEntity.objects.filter(org=request.profile.org), pk=pk
        )

    def get(self, request, pk, bank_id=None):
        entity = self.entity(request, pk)
        rows = LegalEntityBankAccount.objects.filter(
            org=request.profile.org, entity=entity
        )
        if not is_org_admin(request.profile):
            rows = rows.filter(active=True)
        if bank_id:
            return Response(
                BankAccountSerializer(get_object_or_404(rows, pk=bank_id)).data
            )
        return Response({"results": BankAccountSerializer(rows, many=True).data})

    def post(self, request, pk, bank_id=None):
        if bank_id is not None:
            raise MethodNotAllowed("POST")
        entity = self.entity(request, pk)
        require_admin(request)
        serializer = BankAccountSerializer(
            data=request.data, context={"entity": entity}
        )
        serializer.is_valid(raise_exception=True)
        bank = self.save_bank(
            serializer, org=request.profile.org, entity=entity, created_by=request.user
        )
        return Response(BankAccountSerializer(bank).data, status=201)

    @transaction.atomic
    def patch(self, request, pk, bank_id=None):
        if bank_id is None:
            raise MethodNotAllowed(request.method)
        entity = self.entity(request, pk)
        bank = get_object_or_404(
            LegalEntityBankAccount.objects.select_for_update().filter(
                org=request.profile.org, entity=entity
            ),
            pk=bank_id,
        )
        require_admin(request)
        serializer = BankAccountSerializer(
            bank, data=request.data, partial=True, context={"entity": entity}
        )
        serializer.is_valid(raise_exception=True)
        self.save_bank(serializer)
        return Response(serializer.data)

    put = patch

    def delete(self, request, pk, bank_id=None):
        if bank_id is None:
            raise MethodNotAllowed("DELETE")
        entity = self.entity(request, pk)
        bank = get_object_or_404(
            LegalEntityBankAccount.objects.filter(
                org=request.profile.org, entity=entity
            ),
            pk=bank_id,
        )
        require_admin(request)
        if bank.invoices.exists():
            raise ValidationError("Використаний рахунок можна лише архівувати.")
        bank.delete()
        return Response(status=204)


@extend_schema_view(
    get=extend_schema(
        operation_id="billing_bank_accounts_list",
        responses={
            200: inline_serializer(
                name="LegalEntityBankPage",
                fields={"results": BankAccountSerializer(many=True)},
            )
        },
    ),
    post=extend_schema(
        operation_id="billing_bank_accounts_create",
        request=BankAccountSerializer,
        responses={201: BankAccountSerializer},
    ),
)
class BankAccountListView(BankAccountView):
    http_method_names = ["get", "post", "head", "options"]


@extend_schema_view(
    get=extend_schema(
        operation_id="billing_bank_account_retrieve", responses=BankAccountSerializer
    ),
    put=extend_schema(
        operation_id="billing_bank_account_update",
        request=BankAccountSerializer,
        responses=BankAccountSerializer,
    ),
    patch=extend_schema(
        operation_id="billing_bank_account_partial_update",
        request=BankAccountSerializer,
        responses=BankAccountSerializer,
    ),
    delete=extend_schema(
        operation_id="billing_bank_account_destroy", responses={204: None}
    ),
)
class BankAccountDetailView(BankAccountView):
    http_method_names = ["get", "put", "patch", "delete", "head", "options"]


@extend_schema_view(
    get=extend_schema(responses={(200, "image/png"): OpenApiTypes.BINARY}),
    put=extend_schema(
        request={
            "multipart/form-data": inline_serializer(
                name="BillingScanUpload", fields={"file": schema_fields.ImageField()}
            )
        },
        responses={
            200: inline_serializer(
                name="BillingScanHash", fields={"sha256": schema_fields.CharField()}
            )
        },
    ),
    delete=extend_schema(responses={204: None}),
)
class ScanView(BillingView):
    parser_classes = (MultiPartParser,)

    def entity(self, request, pk, kind):
        entity = get_object_or_404(
            LegalEntity.objects.filter(org=request.profile.org), pk=pk
        )
        require_admin(request)
        if kind not in ("signature", "stamp"):
            from django.http import Http404

            raise Http404
        return entity

    def get(self, request, pk, kind):
        entity = self.entity(request, pk, kind)
        png = (
            LegalEntity.objects.filter(pk=entity.pk, org=request.profile.org)
            .values_list(kind + "_png", flat=True)
            .get()
        )
        if not png:
            from django.http import Http404

            raise Http404
        response = HttpResponse(bytes(png), content_type="image/png")
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response

    def put(self, request, pk, kind):
        entity = self.entity(request, pk, kind)
        upload = request.FILES.get("file")
        if not upload:
            raise ValidationError({"file": "Оберіть зображення."})
        scan = normalize_scan(upload)
        LegalEntity.objects.filter(pk=entity.pk, org=request.profile.org).update(
            **{kind + "_png": scan["png"], kind + "_sha256": scan["sha256"]}
        )
        return Response({"sha256": scan["sha256"]})

    def delete(self, request, pk, kind):
        entity = self.entity(request, pk, kind)
        LegalEntity.objects.filter(pk=entity.pk, org=request.profile.org).update(
            **{kind + "_png": None, kind + "_sha256": ""}
        )
        return Response(status=204)
