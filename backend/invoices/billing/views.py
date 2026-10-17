from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiParameter,
    extend_schema,
    extend_schema_view,
    inline_serializer,
)
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
from invoices.serializer import InvoiceSerializer

from .assets import normalize_scan
from .models import LegalEntity, LegalEntityBankAccount
from .serializers import (
    ActCreateRequestSerializer,
    ActInputSerializer,
    BankAccountSerializer,
    LegalEntitySerializer,
    ServiceActSerializer,
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


@extend_schema_view(
    put=extend_schema(
        request=LegalEntitySerializer(partial=True), responses=LegalEntitySerializer
    ),
)
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
        request=BankAccountSerializer(partial=True),
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
        if kind not in ("signature", "stamp", "logo"):
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


@extend_schema_view(
    post=extend_schema(
        request=None,
        responses={
            200: inline_serializer(
                name="IssuedUAInvoice", fields={"invoice": InvoiceSerializer()}
            )
        },
    )
)
class UAInvoiceIssueView(BillingView):
    def post(self, request, pk):
        from invoices.serializer import InvoiceSerializer

        from .services import issue_invoice

        try:
            invoice = issue_invoice(actor=request, invoice_id=pk)
        except (ValidationError,):
            raise
        except Exception as exc:
            from rest_framework.exceptions import APIException

            if isinstance(exc, APIException):
                raise
            import logging

            logging.getLogger(__name__).exception("UA invoice issuing failed")
            return Response(
                {
                    "error": True,
                    "message": "Не вдалося сформувати PDF. Документ не виписано.",
                },
                status=503 if isinstance(exc, ImportError) else 500,
            )
        return Response({"invoice": InvoiceSerializer(invoice).data})


def pdf_response(content, number):
    from django.utils.http import content_disposition_header

    response = HttpResponse(content, content_type="application/pdf")
    response["Content-Disposition"] = content_disposition_header(
        False, filename=str(number) + ".pdf"
    )
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@extend_schema_view(
    get=extend_schema(
        parameters=[
            OpenApiParameter("invoice", OpenApiTypes.UUID),
            OpenApiParameter("account", OpenApiTypes.UUID),
            OpenApiParameter("issuer", OpenApiTypes.UUID),
            OpenApiParameter(
                "status", OpenApiTypes.STR, enum=["Draft", "Issued", "Cancelled"]
            ),
            OpenApiParameter("period_start", OpenApiTypes.DATE),
            OpenApiParameter("period_end", OpenApiTypes.DATE),
            OpenApiParameter("limit", OpenApiTypes.INT),
            OpenApiParameter("offset", OpenApiTypes.INT),
        ],
        responses={
            200: inline_serializer(
                name="ServiceActPage",
                fields={
                    "count": schema_fields.IntegerField(),
                    "next": schema_fields.URLField(allow_null=True),
                    "previous": schema_fields.URLField(allow_null=True),
                    "results": ServiceActSerializer(many=True),
                },
            )
        },
    ),
    post=extend_schema(
        request=ActCreateRequestSerializer, responses={201: ServiceActSerializer}
    ),
)
class ServiceActListView(BillingView):
    def get(self, request):
        from rest_framework import serializers
        from rest_framework.pagination import LimitOffsetPagination

        from .access import visible_acts_qs
        from .serializers import ServiceActSerializer

        rows = visible_acts_qs(request.profile).prefetch_related("lines")
        for param, field in [
            ("invoice", "invoice_id"),
            ("account", "invoice__account_id"),
            ("issuer", "issuer_id"),
        ]:
            if request.query_params.get(param):
                uid = serializers.UUIDField().run_validation(
                    request.query_params[param]
                )
                rows = rows.filter(**{field: uid})
        if request.query_params.get("status"):
            rows = rows.filter(status=request.query_params["status"])
        for param, field in [
            ("period_start", "service_period_start__gte"),
            ("period_end", "service_period_end__lte"),
        ]:
            if request.query_params.get(param):
                rows = rows.filter(
                    **{
                        field: serializers.DateField().run_validation(
                            request.query_params[param]
                        )
                    }
                )
        pagination = LimitOffsetPagination()
        page = pagination.paginate_queryset(rows, request, view=self)
        return pagination.get_paginated_response(
            ServiceActSerializer(page, many=True).data
        )

    def post(self, request):
        from .serializers import ActInputSerializer, ServiceActSerializer
        from .services import create_act

        serializer = ActInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        uid = data.pop("invoice_id", None)
        if uid is None:
            raise ValidationError({"invoice_id": "Оберіть рахунок."})
        act = create_act(actor=request, invoice_id=uid, data=data)
        return Response(ServiceActSerializer(act).data, status=201)


@extend_schema_view(
    get=extend_schema(responses=ServiceActSerializer),
    put=extend_schema(request=ActInputSerializer, responses=ServiceActSerializer),
    delete=extend_schema(responses={204: None}),
)
class ServiceActDetailView(BillingView):
    def get(self, request, pk):
        from .access import get_act_or_error
        from .serializers import ServiceActSerializer

        act, error = get_act_or_error(request, pk)
        if error:
            return error
        return Response(ServiceActSerializer(act).data)

    def put(self, request, pk):
        from .serializers import ActInputSerializer, ServiceActSerializer
        from .services import update_act

        serializer = ActInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        return Response(
            ServiceActSerializer(
                update_act(actor=request, act_id=pk, data=serializer.validated_data)
            ).data
        )

    def delete(self, request, pk):
        from .services import delete_act

        delete_act(actor=request, act_id=pk)
        return Response(status=204)


@extend_schema_view(
    post=extend_schema(
        request=inline_serializer(
            name="ServiceActAction",
            fields={"reason": schema_fields.CharField(required=False, max_length=2000)},
        ),
        responses=ServiceActSerializer,
    )
)
class ServiceActActionView(BillingView):
    def post(self, request, pk, action):
        from rest_framework.exceptions import APIException

        from .serializers import ServiceActSerializer
        from .services import cancel_act, issue_act

        try:
            act = (
                issue_act(actor=request, act_id=pk)
                if action == "issue"
                else cancel_act(
                    actor=request, act_id=pk, reason=request.data.get("reason", "")
                )
            )
        except APIException:
            raise
        except Exception as exc:
            import logging

            logging.getLogger(__name__).exception("Act issuing failed")
            return Response(
                {
                    "error": True,
                    "message": "Не вдалося сформувати PDF. Акт не виписано.",
                },
                status=503 if isinstance(exc, ImportError) else 500,
            )
        return Response(ServiceActSerializer(act).data)


@extend_schema_view(
    get=extend_schema(
        parameters=[
            OpenApiParameter(
                "variant", OpenApiTypes.STR, enum=["clean", "stamped"], default="clean"
            ),
        ],
        responses={(200, "application/pdf"): OpenApiTypes.BINARY},
    )
)
class ServiceActPDFView(BillingView):
    def get(self, request, pk):
        from .access import get_act_or_error
        from .pdf import document_pdf

        act, error = get_act_or_error(request, pk)
        if error:
            return error
        return pdf_response(
            document_pdf(act, variant=request.query_params.get("variant", "clean")),
            act.number or "act-draft",
        )
