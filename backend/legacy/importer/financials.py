"""Preserve incomplete financial evidence without inventing balances or payments."""

from legacy.models import LegacyRecord


def project_financials(ctx):
    for table in ("aos_invoices", "aos_quotes"):
        for row in ctx.reader.rows(table, True):
            d = row["values"]
            reasons = ["historical_financial_record"]
            if d.get("total_amount") is None:
                reasons.append("unknown_total")
            if not d.get("billing_account_id"):
                reasons.append("missing_billing_account")
            if table == "aos_quotes":
                reasons.append("no_certified_complete_line_items")
            LegacyRecord.objects.filter(
                pk=ctx.record_id(table, row["source_id"])
            ).update(adaptations=reasons)
