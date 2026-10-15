from django.db import connection
from django.test.utils import CaptureQueriesContext

from invoices.tests.ua_helpers import create_invoice


def test_ordinary_lists_do_not_load_binary_archives(admin_client, org_a):
    inv = create_invoice(admin_client, org_a)
    from invoices.models import Invoice, LegalEntity

    Invoice.objects.filter(pk=inv["id"]).update(
        archived_pdf_clean=b"private pdf", archived_pdf_stamped=b"private stamped"
    )
    with CaptureQueriesContext(connection) as queries:
        response = admin_client.get("/api/invoices/")
    assert response.status_code == 200
    for query in queries:
        if query["sql"].lstrip().upper().startswith("SELECT"):
            assert "archived_pdf_" not in query["sql"]
    assert {"archived_pdf_clean", "archived_pdf_stamped"} <= Invoice.objects.get(
        pk=inv["id"]
    ).get_deferred_fields()
    assert {"signature_png", "stamp_png"} <= LegalEntity.objects.get(
        pk=inv["issuer"]["id"]
    ).get_deferred_fields()


def test_related_invoice_reads_do_not_load_archives(admin_client, org_a):
    from django.utils import timezone

    from invoices.models import Invoice, Payment
    from invoices.tests.ua_helpers import issued_invoice

    inv = issued_invoice(admin_client, org_a)
    invoice = Invoice.objects.get(pk=inv["id"])
    payment = Payment.objects.create(
        org=org_a,
        invoice=invoice,
        amount="1.00",
        payment_date=timezone.localdate(),
        payment_method="BANK_TRANSFER",
    )
    with CaptureQueriesContext(connection) as queries:
        response = admin_client.delete(
            "/api/invoices/" + inv["id"] + "/payments/" + str(payment.pk) + "/"
        )
    assert response.status_code == 200
    for query in queries:
        if query["sql"].lstrip().upper().startswith("SELECT"):
            assert "archived_pdf_" not in query["sql"]
