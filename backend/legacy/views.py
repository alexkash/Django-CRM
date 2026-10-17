"""Authenticated, read-only history. All filters run after the common policy."""

from datetime import date, datetime, time, timedelta, timezone

from django.db.models import F, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.custom_fields import visible_custom_field_values
from common.permissions import HasOrgContext, is_org_admin
from legacy.access import read_rules, readable_record, visible_records
from legacy.importer.files import private_root
from legacy.importer.reader import file_hash, safe_file
from legacy.models import (
    LegacyFile,
    LegacyImportBatch,
    LegacyProjection,
    LegacyRelation,
)
from legacy.search import search_records
from legacy.serializers import FileSummary, RecordSummary

KINDS = {
    "record",
    "call",
    "meeting",
    "email",
    "invoice",
    "quote",
    "note",
    "change",
    "audit",
}


class HistoryView(APIView):
    permission_classes = (IsAuthenticated, HasOrgContext)
    http_method_names = ["get", "head", "options"]


def page(
    request,
    qs,
    serializer=RecordSummary,
    ordering=None,
    deferred=("payload", "search_text"),
):
    params = request.query_params
    try:
        limit = int(params.get("limit", 50))
        offset = int(params.get("offset", 0))
        if not 1 <= limit <= 100 or not 0 <= offset <= 2**31 - 1:
            raise ValueError
    except (ValueError, TypeError):
        raise ValidationError("Invalid pagination")
    count = qs.count()
    rows = qs.defer(*deferred).order_by(
        *(ordering or (F("source_created_at").desc(nulls_last=True), "id"))
    )[offset : offset + limit]

    def link(value):
        args = params.copy()
        args["offset"] = value
        args["limit"] = limit
        return request.path + "?" + args.urlencode()

    return Response(
        {
            "results": serializer(rows, many=True).data,
            "count": count,
            "next": link(offset + limit) if offset + limit < count else None,
            "previous": link(max(offset - limit, 0)) if offset else None,
        }
    )


def filters(request, qs):
    import json
    from pathlib import Path

    policy = json.loads(
        (Path(__file__).parent / "importer/source_policy.json").read_text()
    )
    params = request.query_params
    table = params.get("table")
    if table:
        if table not in policy or policy[table]["category"] != "history":
            raise ValidationError("Invalid table")
        qs = qs.filter(source_table=table)
    kind = params.get("kind")
    if kind:
        if kind not in KINDS:
            raise ValidationError("Invalid kind")
        qs = qs.filter(kind=kind)
    deleted = params.get("deleted")
    if deleted is not None:
        if deleted not in ("true", "false", "all"):
            raise ValidationError("Invalid deleted filter")
        if deleted != "all":
            qs = qs.filter(source_deleted=deleted == "true")
    else:
        qs = qs.filter(source_deleted=False)
    for name, lookup in [("from", "gte"), ("to", "lt")]:
        if params.get(name):
            try:
                value = datetime.combine(
                    date.fromisoformat(params[name]), time.min, tzinfo=timezone.utc
                )
                if name == "to":
                    value += timedelta(days=1)
            except (ValueError, OverflowError):
                raise ValidationError("Invalid date")
            qs = qs.filter(**{"source_created_at__" + lookup: value})
    query = params.get("q", "").strip()
    if len(query) > 500:
        raise ValidationError("Search is too long")
    return search_records(qs, query) if query else qs


class RecordList(HistoryView):
    def get(self, request):
        return page(request, filters(request, visible_records(request.profile)))


class RecordDetail(HistoryView):
    def get(self, request, pk):
        profile = request.profile
        record = readable_record(profile, pk)
        visible = visible_records(profile)
        # Raw edge DTOs would expose hidden IDs and source labels. Return only
        # visible endpoint summaries; actor/sealed links stay out for members.
        edges = LegacyRelation.objects.filter(
            org=profile.org, source_deleted=False
        ).filter(Q(from_record=record) | Q(to_record=record) | Q(source_record=record))
        related_ids = set()
        for a, b in edges.values_list("from_record_id", "to_record_id"):
            related_ids.update(x for x in (a, b) if x and x != record.pk)
        links = (
            visible.filter(pk__in=related_ids)
            .defer("payload", "search_text")
            .order_by("source_table", "id")[:100]
        )
        content_ids = LegacyRelation.objects.filter(
            org=profile.org,
            to_record=record,
            role__in=["content", "fields"],
            source_deleted=False,
            state="resolved",
        ).values("from_record_id")
        parts = visible.filter(pk__in=content_ids).order_by("source_table", "id")[:100]
        data = dict(RecordSummary(record).data)
        data.update(
            fields=visible_custom_field_values(record.payload),
            links=RecordSummary(links, many=True).data,
            content=[
                {
                    "source_table": r.source_table,
                    "fields": visible_custom_field_values(r.payload),
                }
                for r in parts
            ],
            files=FileSummary(record.files.filter(org=profile.org), many=True).data,
            native=list(
                record.projections.filter(org=profile.org)
                .exclude(
                    target_model__in=[
                        "common.Activity",
                        "common.User",
                        "common.Profile",
                    ]
                )
                .values("target_model", "target_id", "role")
            ),
        )
        return Response(data)


class FileList(HistoryView):
    def get(self, request):
        profile = request.profile
        qs = LegacyFile.objects.filter(org=profile.org)
        if not is_org_admin(profile):
            qs = qs.filter(record_id__in=visible_records(profile).values("pk"))
        query = request.query_params.get("q", "").strip()
        if len(query) > 500:
            raise ValidationError("Search is too long")
        if query:
            qs = qs.filter(original_name__icontains=query)
        return page(request, qs, FileSummary, ("original_name", "id"), ())


class FileDownload(HistoryView):
    def get(self, request, pk):
        profile = request.profile
        qs = LegacyFile.objects.filter(org=profile.org)
        if not is_org_admin(profile):
            qs = qs.filter(record_id__in=visible_records(profile).values("pk"))
        entry = get_object_or_404(qs, pk=pk)
        try:
            path = safe_file(private_root(), entry.storage_key)
            if path.stat().st_size != entry.size or file_hash(path) != entry.sha256:
                return Response({"detail": "Stored file checksum mismatch"}, status=409)
            response = FileResponse(
                path.open("rb"),
                as_attachment=True,
                filename=entry.original_name.rsplit("/", 1)[-1],
                content_type="application/octet-stream",
            )
        except (ValueError, OSError):
            raise Http404
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        return response


class EntityHistory(HistoryView):
    def get(self, request, model, pk):
        labels = {
            "accounts": "accounts.Account",
            "contacts": "contacts.Contact",
            "leads": "leads.Lead",
            "opportunities": "opportunity.Opportunity",
            "tasks": "tasks.Task",
        }
        label = labels.get(model)
        rules = read_rules(request.profile)
        if label == "tasks.Task":
            from tasks.access import visible_tasks_qs

            rules[label] = visible_tasks_qs(request.profile)
        if label not in rules or not rules[label].filter(pk=pk).exists():
            raise Http404
        roots = LegacyProjection.objects.filter(
            org=request.profile.org, target_model=label, target_id=pk
        ).values("record_id")
        edges = LegacyRelation.objects.filter(
            org=request.profile.org, to_record_id__in=roots, source_deleted=False
        )
        qs = visible_records(request.profile).filter(
            Q(pk__in=roots)
            | Q(pk__in=edges.values("from_record_id"))
            | Q(pk__in=edges.values("source_record_id"))
        )
        return page(request, filters(request, qs))


class BatchReport(HistoryView):
    def get(self, request, pk):
        if not is_org_admin(request.profile):
            raise PermissionDenied
        batch = get_object_or_404(LegacyImportBatch, org=request.profile.org, pk=pk)
        return Response(
            {
                "id": batch.pk,
                "state": batch.state,
                "snapshot_sha256": batch.snapshot_sha256,
                "captured_at": batch.captured_at,
                "report": batch.report,
            }
        )
