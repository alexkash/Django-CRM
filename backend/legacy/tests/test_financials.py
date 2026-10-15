from invoices.models import Invoice, Payment
from legacy.models import LegacyRecord
from legacy.tests.helpers import make_context


def test_incomplete_paid_invoice_stays_historical(org_a, tmp_path):
    try:
        from legacy.importer.financials import project_financials
    except ModuleNotFoundError as exc:
        raise AssertionError("Financial archive projection not implemented") from exc
    ctx = make_context(
        org_a,
        tmp_path,
        {
            "aos_invoices": [
                {
                    "id": "i",
                    "name": "Historical",
                    "status": "Paid",
                    "total_amount": None,
                    "total_amt": "123.45",
                }
            ]
        },
    )
    project_financials(ctx)
    legacy = LegacyRecord.objects.get(org=org_a, source_table="aos_invoices")
    assert legacy.payload["total_amount"] is None
    assert legacy.payload["total_amt"] == "123.45"
    assert legacy.kind == "invoice"
    assert Invoice.objects.filter(org=org_a).count() == 0
    assert Payment.objects.filter(org=org_a).count() == 0
