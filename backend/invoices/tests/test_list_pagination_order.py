"""Adjacent pages remain deterministic when the primary sort values tie."""

import datetime
import uuid

import pytest
from django.utils import timezone

from contacts.models import Contact
from invoices.models import Estimate, Invoice, Product, RecurringInvoice


@pytest.mark.django_db
@pytest.mark.parametrize(
    "model,url,fields,params,envelope",
    [
        (
            Invoice,
            "/api/invoices/",
            {"invoice_title": "Same", "due_date": datetime.date(2026, 10, 15)},
            {"sort": "due_date"},
            "results",
        ),
        (Invoice, "/api/invoices/", {"invoice_title": "Same"}, {}, "results"),
        (Product, "/api/invoices/products/", {"name": "Same"}, {}, "results"),
        (Estimate, "/api/invoices/estimates/", {"title": "Same"}, {}, "results"),
        (
            RecurringInvoice,
            "/api/invoices/recurring/",
            {"title": "Same"},
            {},
            "results",
        ),
        (Contact, "/api/contacts/", {"first_name": "Same"}, {}, "contact_obj_list"),
    ],
)
def test_pages_with_tied_sort_values_use_id_order(
    admin_client, org_a, model, url, fields, params, envelope
):
    ids = [uuid.UUID(int=n) for n in (4, 1, 3, 2)]
    for pk in ids:
        model.objects.create(id=pk, org=org_a, **fields)
    # Historical imports commonly have identical timestamps.
    model.objects.filter(id__in=ids).update(created_at=timezone.now())
    pages = []
    for offset in (0, 2):
        response = admin_client.get(url, {**params, "limit": 2, "offset": offset})
        assert response.status_code == 200
        rows = response.data[envelope]
        pages.extend(str(row["id"]) for row in rows)
    assert pages == [str(pk) for pk in sorted(ids)]
