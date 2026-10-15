"""Hash existing destination records without writing or printing customer values."""

import base64
import hashlib
import json
import os
import sys
from pathlib import Path

import django

django.setup()
from django.apps import apps  # noqa: E402
from django.core.serializers.json import DjangoJSONEncoder  # noqa: E402
from django.db import connection  # noqa: E402

mode, path, org_id = sys.argv[1:]
with connection.cursor() as cursor:
    cursor.execute("SELECT set_config('app.current_org',%s,false)", [org_id])


def digest(obj):
    values = {}
    for field in obj._meta.concrete_fields:
        if obj._meta.label == "common.User" and field.name in {
            "last_login",
            "activation_key",
            "key_expires",
        }:
            continue
        value = getattr(obj, field.attname)
        if hasattr(value, "name") and field.get_internal_type() in {
            "FileField",
            "ImageField",
        }:
            value = value.name
        if isinstance(value, (bytes, memoryview)):
            value = {"binary": base64.b64encode(value).decode()}
        values[field.attname] = value
    values["_relations"] = {
        field.name: sorted(str(row.pk) for row in getattr(obj, field.name).all())
        for field in obj._meta.many_to_many
    }
    return hashlib.sha256(
        json.dumps(
            values,
            cls=DjangoJSONEncoder,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


try:
    if mode == "capture":
        result = {"org_id": org_id, "models": {}}
        for model in apps.get_models():
            names = {field.name for field in model._meta.fields}
            if "org" in names:
                qs = model.objects.filter(org_id=org_id)
            elif model._meta.label == "common.User":
                qs = model.objects.all()
            elif model._meta.label == "common.Org":
                qs = model.objects.filter(pk=org_id)
            else:
                continue
            qs = qs.prefetch_related(
                *[field.name for field in model._meta.many_to_many]
            )
            result["models"][model._meta.label] = {
                str(obj.pk): digest(obj) for obj in qs.iterator(chunk_size=200)
            }
        Path(path).write_text(json.dumps(result, sort_keys=True))
        os.chmod(path, 0o600)
        print("Destination baseline captured privately")
    elif mode == "verify":
        result = json.loads(Path(path).read_text())
        assert result["org_id"] == org_id
        errors = []
        for label, expected in result["models"].items():
            model = apps.get_model(label)
            for offset in range(0, len(expected), 200):
                ids = list(expected)[offset : offset + 200]
                qs = model.objects.filter(pk__in=ids).prefetch_related(
                    *[field.name for field in model._meta.many_to_many]
                )
                actual = {str(obj.pk): digest(obj) for obj in qs}
                if any(actual.get(pk) != expected[pk] for pk in ids):
                    errors.append(label)
        if errors:
            raise ValueError(
                "Existing destination records changed: "
                + ", ".join(sorted(set(errors)))
            )
        print("All pre-existing destination records and owner credentials preserved")
    else:
        raise ValueError("Unknown mode")
finally:
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.current_org','',false)")
