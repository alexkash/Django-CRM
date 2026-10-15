"""Small list DTOs never contain mail bodies, raw payloads or storage paths."""

from rest_framework import serializers

from legacy.models import LegacyFile, LegacyRecord


class RecordSummary(serializers.ModelSerializer):
    source_id = serializers.CharField(source="source_pk")

    class Meta:
        model = LegacyRecord
        fields = (
            "id",
            "source_table",
            "source_id",
            "title",
            "kind",
            "source_created_at",
            "source_updated_at",
            "source_deleted",
            "adaptations",
        )


class FileSummary(serializers.ModelSerializer):
    class Meta:
        model = LegacyFile
        fields = ("id", "original_name", "size", "sha256")
