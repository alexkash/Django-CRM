"""Immutable SuiteCRM evidence and its explicitly tracked CRM projections."""

from django.core.exceptions import ValidationError
from django.db import models

from common.base import BaseOrgModel


class LegacyBase(BaseOrgModel):
    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        for name in ("source", "record", "source_record", "from_record", "to_record"):
            related = getattr(self, name, None)
            if related is not None and self.org_id != related.org_id:
                raise ValidationError(
                    {name: "Related history must belong to the same organization."}
                )

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)


class LegacySource(LegacyBase):
    key = models.CharField(max_length=64, unique=True)
    version = models.CharField(max_length=32, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "legacy_source"
        indexes = [models.Index(fields=["org", "key"])]

    def clean(self):
        super().clean()
        old = type(self).objects.filter(pk=self.pk).values("org_id", "key").first()
        if old and (old["org_id"] != self.org_id or old["key"] != self.key):
            raise ValidationError(
                "An imported source cannot change its identity or organization."
            )


class LegacyImportBatch(LegacyBase):
    source = models.ForeignKey(
        LegacySource, on_delete=models.PROTECT, related_name="batches"
    )
    snapshot_sha256 = models.CharField(max_length=64)
    captured_at = models.DateTimeField(null=True, blank=True)
    state = models.CharField(max_length=16, default="PREPARED")
    checkpoint = models.CharField(max_length=64, blank=True, default="")
    report = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "legacy_import_batch"
        constraints = [
            models.UniqueConstraint(
                fields=["source", "snapshot_sha256"],
                name="legacy_unique_snapshot_batch",
            )
        ]
        indexes = [models.Index(fields=["org", "state"])]


class LegacyRecord(LegacyBase):
    source = models.ForeignKey(
        LegacySource, on_delete=models.PROTECT, related_name="records"
    )
    source_table = models.CharField(max_length=100)
    source_pk = models.TextField()
    payload = models.JSONField(default=dict, blank=True)
    payload_sha256 = models.CharField(max_length=64)
    source_created_at = models.DateTimeField(null=True, blank=True)
    source_updated_at = models.DateTimeField(null=True, blank=True)
    source_deleted = models.BooleanField(default=False)
    title = models.TextField(blank=True, default="")
    search_text = models.TextField(blank=True, default="")
    kind = models.CharField(max_length=32, default="record")
    adaptations = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "legacy_record"
        constraints = [
            models.UniqueConstraint(
                fields=["source", "source_table", "source_pk"],
                name="legacy_unique_source_record",
            )
        ]
        indexes = [
            models.Index(fields=["org", "source_table", "source_deleted"]),
            models.Index(fields=["org", "kind", "source_created_at"]),
        ]


class LegacyRelation(LegacyBase):
    source = models.ForeignKey(
        LegacySource, on_delete=models.PROTECT, related_name="relations"
    )
    source_record = models.ForeignKey(
        LegacyRecord, on_delete=models.CASCADE, related_name="derived_relations"
    )
    from_record = models.ForeignKey(
        LegacyRecord,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="outgoing_relations",
    )
    to_record = models.ForeignKey(
        LegacyRecord,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="incoming_relations",
    )
    from_table = models.CharField(max_length=100, blank=True, default="")
    from_source_id = models.TextField(blank=True, default="")
    to_table = models.CharField(max_length=100, blank=True, default="")
    to_source_id = models.TextField(blank=True, default="")
    role = models.CharField(max_length=100)
    state = models.CharField(max_length=24, default="resolved")
    source_deleted = models.BooleanField(default=False)

    class Meta:
        db_table = "legacy_relation"
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "source_record",
                    "role",
                    "from_table",
                    "from_source_id",
                    "to_table",
                    "to_source_id",
                ],
                name="legacy_unique_source_relation",
            )
        ]
        indexes = [
            models.Index(fields=["org", "from_record"]),
            models.Index(fields=["org", "to_record"]),
        ]


class LegacyFile(LegacyBase):
    source = models.ForeignKey(
        LegacySource, on_delete=models.PROTECT, related_name="files"
    )
    record = models.ForeignKey(
        LegacyRecord,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="files",
    )
    storage_key = models.CharField(max_length=1024)
    original_name = models.TextField()
    size = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64)

    class Meta:
        db_table = "legacy_file"
        constraints = [
            models.UniqueConstraint(
                fields=["source", "original_name"], name="legacy_unique_source_file"
            )
        ]
        indexes = [models.Index(fields=["org", "record"])]


class LegacyProjection(LegacyBase):
    record = models.ForeignKey(
        LegacyRecord, on_delete=models.PROTECT, related_name="projections"
    )
    target_model = models.CharField(max_length=100)
    target_id = models.UUIDField()
    role = models.CharField(max_length=160, default="native")
    projected_sha256 = models.CharField(max_length=64)

    class Meta:
        db_table = "legacy_projection"
        constraints = [
            models.UniqueConstraint(
                fields=["record", "role"], name="legacy_unique_projection_role"
            )
        ]
        indexes = [models.Index(fields=["org", "target_model", "target_id"])]
