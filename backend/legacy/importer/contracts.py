"""Shared import state and explicit projection writes; no request-based side effects."""

from datetime import datetime, timezone
from itertools import islice

from django.apps import apps
from django.db import connection, transaction

from legacy.models import LegacyProjection, LegacyRecord, LegacySource

from .identity import SOURCE_KEY, object_fingerprint, stable_id


class ImportConflict(ValueError):
    pass


def source_time(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return (
            parsed.replace(tzinfo=timezone.utc)
            if parsed.tzinfo is None
            else parsed.astimezone(timezone.utc)
        )
    except (ValueError, TypeError):
        return None


def chunks(items, size=300):
    iterator = iter(items)
    while block := list(islice(iterator, size)):
        yield block


def set_org(org_id):
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('app.current_org',%s,false)", [str(org_id)]
            )


class ImportContext:
    def __init__(self, org, reader):
        self.org = org
        self.reader = reader
        self.results = []
        set_org(org.id)
        self.source, created = LegacySource.objects.get_or_create(
            key=SOURCE_KEY,
            defaults={
                "org": org,
                "version": "7.12.6",
                "metadata": {"snapshot_sha256": reader.manifest["snapshot_sha256"]},
            },
        )
        if self.source.org_id != org.id:
            raise ImportConflict("Source belongs to another organization")
        if (
            self.source.metadata.get("snapshot_sha256")
            != reader.manifest["snapshot_sha256"]
        ):
            raise ImportConflict(
                "A different snapshot requires a separately reviewed update migration"
            )
        self.projections = {
            (p.record_id, p.role): p
            for p in LegacyProjection.objects.filter(
                org=org, record__source=self.source
            )
        }
        self._email_index = None

    def record_id(self, table, key):
        return stable_id(table, str(key), "history")

    def native_id(self, table, key, role="native"):
        if key in (None, ""):
            return None
        value = self.projections.get((self.record_id(table, key), role))
        return value.target_id if value else None

    def stage_history(self):
        for table, entry in self.reader.manifest["tables"].items():
            if entry["category"] != "history" or not entry["total"]:
                continue
            for block in chunks(self.reader.rows(table)):
                ids = [self.record_id(table, row["source_id"]) for row in block]
                old = LegacyRecord.objects.filter(id__in=ids).in_bulk()
                create = []
                for row, pk in zip(block, ids):
                    if pk in old:
                        if old[pk].payload_sha256 != row["row_sha256"]:
                            raise ImportConflict(
                                "Previously imported history differs from snapshot"
                            )
                        continue
                    data = row["values"]
                    title = (
                        data.get("name")
                        or data.get("subject")
                        or " ".join(
                            str(data.get(x) or "") for x in ["first_name", "last_name"]
                        ).strip()
                        or data.get("user_name")
                        or f"{table}:{row['source_id']}"
                    )
                    kind = {
                        "emails": "email",
                        "calls": "call",
                        "meetings": "meeting",
                        "aos_invoices": "invoice",
                        "aos_quotes": "quote",
                        "notes": "note",
                        "sugarfeed": "change",
                    }.get(table, "audit" if table.endswith("_audit") else "record")
                    search = " ".join(
                        str(v) for v in data.values() if isinstance(v, (str, int))
                    )
                    create.append(
                        LegacyRecord(
                            id=pk,
                            source=self.source,
                            org=self.org,
                            source_table=table,
                            source_pk=row["source_id"],
                            payload=data,
                            payload_sha256=row["row_sha256"],
                            source_deleted=row["deleted"],
                            title=str(title),
                            search_text=search,
                            kind=kind,
                            source_created_at=source_time(
                                data.get("date_entered") or data.get("date_created")
                            ),
                            source_updated_at=source_time(data.get("date_modified")),
                        )
                    )
                LegacyRecord.objects.bulk_create(create, batch_size=300)

    def write(self, table, row, obj, role="native", adaptations=None, reuse=False):
        record_id = self.record_id(table, row["source_id"])
        previous = self.projections.get((record_id, role))
        model = type(obj)
        if previous:
            existing = model.objects.filter(pk=previous.target_id).first()
            if (
                existing is None
                or object_fingerprint(existing) != previous.projected_sha256
            ):
                raise ImportConflict("Target record was changed after import")
            return existing
        with transaction.atomic():
            if reuse:
                existing = model.objects.filter(pk=obj.pk).first()
                if existing is None:
                    raise ImportConflict("Reused target disappeared")
                obj = existing
            else:
                if model.objects.filter(pk=obj.pk).exists():
                    raise ImportConflict(
                        "Target identity exists without an import mapping"
                    )
                data = row["values"]
                created = source_time(
                    data.get("date_entered") or data.get("date_created")
                )
                updated = source_time(data.get("date_modified")) or created
                if hasattr(obj, "created_at") and created is None:
                    raise ImportConflict(
                        "Source record has no representable creation timestamp"
                    )
                model.objects.bulk_create([obj])
                stamps = []
                for name, value in [("created_at", created), ("updated_at", updated)]:
                    if hasattr(obj, name):
                        setattr(obj, name, value)
                        stamps.append(name)
                if stamps:
                    model.objects.bulk_update([obj], stamps)
                obj.refresh_from_db()
            mapping = LegacyProjection.objects.create(
                record_id=record_id,
                org=self.org,
                target_model=model._meta.label,
                target_id=obj.pk,
                role=role,
                projected_sha256=object_fingerprint(obj),
            )
            self.projections[(record_id, role)] = mapping
            if adaptations:
                LegacyRecord.objects.filter(pk=record_id).update(
                    adaptations=adaptations
                )
            self.results.append(
                {
                    "source_record_id": str(record_id),
                    "target_model": model._meta.label,
                    "target_id": str(obj.pk),
                    "role": role,
                    "status": "native",
                    "adaptations": adaptations or [],
                }
            )
            return obj

    def restamp_projection(self, record_id, role="native"):
        p = self.projections[(record_id, role)]
        obj = apps.get_model(p.target_model).objects.get(pk=p.target_id)
        p.projected_sha256 = object_fingerprint(obj)
        p.save(update_fields=["projected_sha256"])

    def primary_email(self, module, key):
        if self._email_index is None:
            addresses = {
                row["source_id"]: row["values"].get("email_address", "")
                for row in self.reader.rows("email_addresses", True)
            }
            index = {}
            for row in self.reader.rows("email_addr_bean_rel", True):
                data = row["values"]
                if str(data.get("primary_address", "0")) == "1":
                    ref = (data.get("bean_module"), str(data.get("bean_id")))
                    if ref not in index:
                        index[ref] = addresses.get(
                            str(data.get("email_address_id")), ""
                        )
            self._email_index = index
        return self._email_index.get((module, str(key)), "")

    def actor(self, data):
        return self.native_id("users", data.get("created_by"))

    def updater(self, data):
        return self.native_id("users", data.get("modified_user_id"))
