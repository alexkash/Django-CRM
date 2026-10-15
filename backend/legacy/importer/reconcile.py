"""Evidence-based coverage: source rows/links/files plus tracked native fingerprints."""

from collections import Counter, defaultdict

from django.apps import apps

from legacy.models import LegacyFile, LegacyProjection, LegacyRecord, LegacyRelation

from .contracts import chunks, set_org
from .files import private_root
from .identity import fingerprint, object_fingerprint
from .reader import file_hash, safe_file
from .relations import walk_relations

PRIMARY_MODELS = {
    "users": "common.User",
    "accounts": "accounts.Account",
    "contacts": "contacts.Contact",
    "leads": "leads.Lead",
    "opportunities": "opportunity.Opportunity",
    "aos_products": "invoices.Product",
    "emails": "accounts.AccountEmail",
    "tasks": "tasks.Task",
}


def projection_conflicts(ctx):
    grouped = defaultdict(list)
    for p in LegacyProjection.objects.filter(org=ctx.org, record__source=ctx.source):
        grouped[p.target_model].append(p)
    conflicts = []
    for label, mappings in grouped.items():
        model = apps.get_model(label)
        for block in chunks(mappings):
            qs = model.objects.filter(pk__in=[p.target_id for p in block])
            if any(f.name == "org" for f in model._meta.fields):
                qs = qs.filter(org=ctx.org)
            qs = qs.prefetch_related(*[f.name for f in model._meta.many_to_many])
            objects = {obj.pk: obj for obj in qs}
            for p in block:
                obj = objects.get(p.target_id)
                if obj is None or object_fingerprint(obj) != p.projected_sha256:
                    conflicts.append(
                        {
                            "model": label,
                            "id": str(p.target_id),
                            "reason": "target_changed_or_missing",
                        }
                    )
    return conflicts


def reconcile(ctx):
    set_org(ctx.org.pk)
    report = {
        "org_id": str(ctx.org.pk),
        "source_key": ctx.source.key,
        "verified": False,
        "snapshot_sha256": ctx.reader.manifest["snapshot_sha256"],
        "manifest_sha256": ctx.reader.manifest_hash,
        "tables": {},
        "history_mismatches": [],
        "relation_mismatches": [],
        "file_hash_mismatches": [],
        "conflicts": projection_conflicts(ctx),
        "source_orphans": {},
        "new_orphans": 0,
        "files": {"source": len(ctx.reader.manifest["files"]), "verified": 0},
    }
    native = Counter()
    for table in LegacyProjection.objects.filter(
        org=ctx.org,
        record__source=ctx.source,
        role="native",
        record__source_deleted=False,
    ).values_list("record__source_table", flat=True):
        native[table] += 1
    adaptations = Counter()
    for table, entry in ctx.reader.manifest["tables"].items():
        total = entry["total"]
        sealed = entry["category"] == "sealed"
        history = LegacyRecord.objects.filter(
            org=ctx.org, source=ctx.source, source_table=table
        )
        count = history.count()
        deleted = history.filter(source_deleted=True).count()
        expected = 0 if sealed else total
        if count != expected or (not sealed and deleted != entry["deleted"]):
            report["history_mismatches"].append(
                {"table": table, "reason": "count_or_deleted_mismatch"}
            )
        expected_native = (
            entry["active"] if table in PRIMARY_MODELS and not sealed else 0
        )
        if native[table] != expected_native:
            report["history_mismatches"].append(
                {"table": table, "reason": "native_projection_count"}
            )
        report["tables"][table] = {
            "source_total": total,
            "history_total": count,
            "native_active": native[table],
            "history_only_active": 0 if sealed else entry["active"] - native[table],
            "deleted_history": 0 if sealed else deleted,
            "sealed": total if sealed else 0,
            "history_only_reason": "sealed_runtime"
            if sealed
            else "preserved_source_evidence",
        }
        if sealed:
            continue
        for block in chunks(ctx.reader.rows(table)):
            ids = [ctx.record_id(table, r["source_id"]) for r in block]
            actual = history.filter(pk__in=ids).in_bulk()
            for row, pk in zip(block, ids):
                saved = actual.get(pk)
                if (
                    saved is None
                    or saved.source_pk != row["source_id"]
                    or saved.source_deleted != row["deleted"]
                    or saved.payload_sha256 != row["row_sha256"]
                    or fingerprint(saved.payload) != row["row_sha256"]
                ):
                    report["history_mismatches"].append(
                        {
                            "table": table,
                            "id": str(pk),
                            "reason": "source_payload_mismatch",
                        }
                    )
                if saved:
                    for item in saved.adaptations:
                        adaptations[
                            item
                            if isinstance(item, str)
                            else item.get("reason", "other")
                        ] += 1
    source_orphans = Counter()
    expected_edge_ids = set()
    edge_fields = (
        "source_record_id",
        "from_record_id",
        "to_record_id",
        "from_table",
        "from_source_id",
        "to_table",
        "to_source_id",
        "role",
        "state",
        "source_deleted",
    )

    def check_edges(block):
        actual = LegacyRelation.objects.filter(
            org=ctx.org, source=ctx.source, pk__in=[r.pk for r in block]
        ).in_bulk()
        for edge in block:
            # The source metadata can describe the same physical edge twice.
            if edge.pk in expected_edge_ids:
                continue
            expected_edge_ids.add(edge.pk)
            if edge.state != "resolved" and not edge.source_deleted:
                source_orphans[edge.state] += 1
            saved = actual.get(edge.pk)
            if saved is None or any(
                getattr(saved, f) != getattr(edge, f) for f in edge_fields
            ):
                report["relation_mismatches"].append(
                    {"id": str(edge.pk), "reason": "source_edge_mismatch"}
                )

    walk_relations(ctx, check_edges)
    actual_edges = LegacyRelation.objects.filter(
        org=ctx.org, source=ctx.source
    ).exclude(role="recipient_match")
    extras = set(actual_edges.values_list("pk", flat=True)) - expected_edge_ids
    if extras:
        report["relation_mismatches"].append(
            {"reason": "unexpected_edges", "count": len(extras)}
        )
    report["source_orphans"] = {
        "missing": source_orphans["missing"],
        "deleted_parent": source_orphans["deleted_parent"],
    }
    report["relations"] = {
        "source_derived": len(expected_edge_ids),
        "actual_source_derived": actual_edges.count(),
    }
    report["new_orphans"] = len(report["relation_mismatches"])
    files = {
        f.original_name: f
        for f in LegacyFile.objects.filter(org=ctx.org, source=ctx.source)
    }
    expected_names = {f["path"] for f in ctx.reader.manifest["files"]}
    if set(files) != expected_names:
        report["file_hash_mismatches"].append({"reason": "file_key_coverage"})
    for entry in ctx.reader.manifest["files"]:
        saved = files.get(entry["path"])
        try:
            if (
                saved is None
                or saved.size != entry["size"]
                or saved.sha256 != entry["sha256"]
            ):
                raise ValueError("File metadata mismatch")
            path = safe_file(private_root(), saved.storage_key)
            source = safe_file(ctx.reader.root.parent / "upload", entry["path"])
            if (
                path.stat().st_size != entry["size"]
                or file_hash(path) != entry["sha256"]
                or file_hash(source) != entry["sha256"]
            ):
                raise ValueError("File bytes mismatch")
            report["files"]["verified"] += 1
        except (OSError, ValueError):
            report["file_hash_mismatches"].append(
                {"id": str(saved.pk) if saved else None, "reason": "file_checksum"}
            )
    report["adaptations"] = dict(adaptations)
    report["history_total"] = sum(t["history_total"] for t in report["tables"].values())
    report["native_primary"] = sum(native.values())
    report["projections_total"] = LegacyProjection.objects.filter(
        org=ctx.org, record__source=ctx.source
    ).count()
    report["verified"] = not any(
        report[key]
        for key in [
            "history_mismatches",
            "relation_mismatches",
            "file_hash_mismatches",
            "conflicts",
        ]
    )
    return report
