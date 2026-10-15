"""Number allocation is serialized within the issuing transaction."""

from .models import DocumentSequence


def next_document_number(*, org, entity, kind):
    if entity.org_id != org.pk or kind not in ("INVOICE", "ACT"):
        raise ValueError("Invalid issuing entity or document kind")
    counter = DocumentSequence.objects.select_for_update().get(
        org=org, entity=entity, kind=kind
    )
    counter.last_value += 1
    counter.save(update_fields=["last_value"])
    prefix = entity.invoice_prefix if kind == "INVOICE" else entity.act_prefix
    return f"{prefix}{counter.last_value:06d}"
