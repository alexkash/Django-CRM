"""Stable identities do not assume SuiteCRM keys are UUIDs or numbers."""

import hashlib
import json
from uuid import NAMESPACE_URL, uuid5

from django.core.serializers.json import DjangoJSONEncoder

SOURCE_KEY = "suitecrm-coloris"

# These optional fields did not exist when the deployed SuiteCRM fingerprints
# were recorded. Empty defaults must not turn unchanged records into conflicts.
# Nonempty values remain in the fingerprint, so billing edits are still protected.
BILLING_EMPTY_ADDITIONS = {
    "accounts.Account": {
        "legal_name",
        "registration_code",
        "vat_registration_number",
        "legal_address",
        "iban",
        "bank_name",
        "mfo",
        "tax_system_text",
        "signer_name",
        "signer_title",
    },
    "invoices.Product": {"unit"},
}


def stable_id(table, source_id, role="native"):
    value = json.dumps(
        [SOURCE_KEY, str(table), str(source_id), role],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return uuid5(NAMESPACE_URL, value)


def canonical(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        cls=DjangoJSONEncoder,
    )


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def object_fingerprint(obj):
    # Login/password rotation must not be mistaken for a business edit or replayed.
    volatile = (
        {"password", "last_login", "activation_key", "key_expires"}
        if obj._meta.label == "common.User"
        else set()
    )
    volatile.update(
        name
        for name in BILLING_EMPTY_ADDITIONS.get(obj._meta.label, ())
        if getattr(obj, name, None) == ""
    )
    data = {
        f.attname: getattr(obj, f.attname)
        for f in obj._meta.concrete_fields
        if f.name not in volatile
    }
    data["_relations"] = {
        f.name: sorted(str(item.pk) for item in getattr(obj, f.name).all())
        for f in obj._meta.many_to_many
    }
    return fingerprint(data)
