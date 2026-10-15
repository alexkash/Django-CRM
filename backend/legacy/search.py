"""Parameterized full text search against the indexed derived text."""

from django.db import connection
from django.db.models import BooleanField
from django.db.models.expressions import RawSQL


def search_records(queryset, query):
    if connection.vendor == "postgresql":
        return queryset.filter(
            RawSQL(
                "to_tsvector('simple', search_text) @@ plainto_tsquery('simple', %s)",
                [query],
                output_field=BooleanField(),
            )
        )
    return queryset.filter(search_text__icontains=query)
