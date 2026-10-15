"""Transactional checkpoints and source-scoped locking; never replay an applied import."""

import hashlib
from contextlib import contextmanager

from django.db import connection, transaction

from legacy.models import LegacyImportBatch

from .contracts import ImportConflict, set_org, source_time
from .identity import fingerprint
from .reader import file_hash, safe_file
from .reconcile import projection_conflicts, reconcile

PHASES = (
    "history",
    "people",
    "core",
    "relations",
    "communications",
    "events",
    "financials",
    "files",
)


@contextmanager
def import_lock(ctx):
    key = int.from_bytes(
        hashlib.sha256((ctx.source.key + str(ctx.org.pk)).encode()).digest()[:8],
        "big",
        signed=True,
    )
    locked = False
    try:
        if connection.vendor == "postgresql":
            with connection.cursor() as c:
                c.execute("SELECT pg_try_advisory_lock(%s)", [key])
                locked = c.fetchone()[0]
            if not locked:
                raise ImportConflict("Another import owns this source/organization")
        yield
    finally:
        if locked:
            with connection.cursor() as c:
                c.execute("SELECT pg_advisory_unlock(%s)", [key])


def validate_inputs(ctx):
    if (
        fingerprint(ctx.reader.manifest) != ctx.reader.manifest_hash
        or ctx.source.metadata.get("manifest_sha256") != ctx.reader.manifest_hash
    ):
        raise ImportConflict("Snapshot manifest changed after binding")
    for entry in ctx.reader.manifest["files"]:
        path = safe_file(ctx.reader.root.parent / "upload", entry["path"])
        if path.stat().st_size != entry["size"] or file_hash(path) != entry["sha256"]:
            raise ImportConflict("Snapshot attachment changed")
    for entry in ctx.reader.manifest.get("metadata_files", []):
        path = safe_file(ctx.reader.root.parent / "metadata", entry["path"])
        if path.stat().st_size != entry["size"] or file_hash(path) != entry["sha256"]:
            raise ImportConflict("Snapshot metadata changed")


def execute_phase(ctx, phase):
    from .communications import project_communications
    from .crm_records import (
        project_accounts,
        project_contacts,
        project_leads,
        project_opportunities,
        project_products,
    )
    from .fields import project_definitions
    from .files import project_files
    from .financials import project_financials
    from .history import project_events
    from .people import project_people
    from .relations import project_relations

    if phase == "history":
        ctx.stage_history()
    elif phase == "people":
        project_people(ctx)
        project_definitions(ctx)
    elif phase == "core":
        for fn in (
            project_accounts,
            project_contacts,
            project_leads,
            project_opportunities,
            project_products,
        ):
            fn(ctx)
    elif phase == "relations":
        project_relations(ctx)
    elif phase == "communications":
        project_communications(ctx)
    elif phase == "events":
        project_events(ctx)
    elif phase == "financials":
        project_financials(ctx)
    elif phase == "files":
        project_files(ctx)


def run_import(ctx, mode, on_phase=None):
    if mode not in ("prepare", "apply", "resume"):
        raise ValueError("Unknown import mode")
    batch = None
    try:
        set_org(ctx.org.pk)
        with import_lock(ctx):
            validate_inputs(ctx)
            batch = LegacyImportBatch.objects.filter(
                org=ctx.org,
                source=ctx.source,
                snapshot_sha256=ctx.reader.manifest["snapshot_sha256"],
            ).first()
            if mode == "prepare":
                if batch and batch.state != "PREPARED":
                    raise ImportConflict(
                        "Existing batch has already started; use resume or verify"
                    )
                if batch is None:
                    batch = LegacyImportBatch.objects.create(
                        org=ctx.org,
                        source=ctx.source,
                        snapshot_sha256=ctx.reader.manifest["snapshot_sha256"],
                        captured_at=source_time(ctx.reader.manifest["captured_at_utc"]),
                    )
                ctx.source.metadata["snapshot_path"] = str(ctx.reader.root)
                type(ctx.source).objects.filter(pk=ctx.source.pk, org=ctx.org).update(
                    metadata=ctx.source.metadata
                )
                batch.report = {
                    "org_id": str(ctx.org.pk),
                    "source_key": ctx.source.key,
                    "prepared": True,
                    "verified": False,
                    "manifest_sha256": ctx.reader.manifest_hash,
                    "source_tables": len(ctx.reader.manifest["tables"]),
                    "source_history_rows": sum(
                        t["total"]
                        for t in ctx.reader.manifest["tables"].values()
                        if t["category"] == "history"
                    ),
                }
                batch.save(update_fields=["report"])
                return {**batch.report, "batch_id": str(batch.pk)}
            if batch is None:
                raise ImportConflict("Prepare this exact snapshot before applying")
            if batch.state == "APPLIED":
                report = reconcile(ctx)
                if not report["verified"]:
                    batch.report = report
                    batch.save(update_fields=["report"])
                    raise ImportConflict(
                        "Applied target differs from its recorded projections"
                    )
                return {**report, "batch_id": str(batch.pk)}
            if mode == "apply" and batch.state != "PREPARED":
                raise ImportConflict("Interrupted import requires resume")
            if mode == "resume" and batch.state == "PREPARED":
                raise ImportConflict("Prepared batch must use apply first")
            start = PHASES.index(batch.checkpoint) + 1 if batch.checkpoint else 0
            batch.state = "RUNNING"
            batch.save(update_fields=["state"])
            for phase in PHASES[start:]:
                # Fresh mappings/config caches are essential after an aborted transaction.
                ctx.reload()
                conflicts = projection_conflicts(ctx)
                if conflicts:
                    batch.report = {"verified": False, "conflicts": conflicts}
                    raise ImportConflict(
                        "Target was changed after a completed import phase"
                    )
                with transaction.atomic():
                    execute_phase(ctx, phase)
                    batch.checkpoint = phase
                    batch.save(update_fields=["checkpoint"])
                if on_phase:
                    on_phase(phase)
            report = reconcile(ctx)
            batch.report = report
            if not report["verified"]:
                raise ImportConflict("Reconciliation found unexplained differences")
            batch.state = "APPLIED"
            batch.save(update_fields=["state", "report"])
            return {**report, "batch_id": str(batch.pk)}
    except Exception as exc:
        if batch and mode != "prepare" and batch.state != "APPLIED":
            batch.state = "FAILED"
            batch.report = {
                **batch.report,
                "verified": False,
                "last_error_type": type(exc).__name__,
            }
            batch.save(update_fields=["state", "report"])
        raise
    finally:
        set_org("")
