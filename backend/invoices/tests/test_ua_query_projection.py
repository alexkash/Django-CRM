from django.db import connection
from django.test.utils import CaptureQueriesContext


def test_ordinary_lists_do_not_load_binary_archives(admin_client, org_a):
    from invoices.models import Invoice, LegalEntity

    invoice = Invoice.objects.create(
        org=org_a, invoice_title="Existing generic invoice"
    )
    Invoice.objects.filter(pk=invoice.pk).update(
        archived_pdf_clean=b"private pdf", archived_pdf_stamped=b"private stamped"
    )
    entity = LegalEntity.objects.create(
        org=org_a,
        entity_type="LLC",
        legal_name="Test",
        registration_code="12345678",
        signature_png=b"private image",
    )
    with CaptureQueriesContext(connection) as queries:
        response = admin_client.get("/api/invoices/")
    assert response.status_code == 200
    for query in queries:
        if query["sql"].lstrip().upper().startswith("SELECT"):
            assert "archived_pdf_" not in query["sql"]
    assert {"archived_pdf_clean", "archived_pdf_stamped"} <= Invoice.objects.get(
        pk=invoice.pk
    ).get_deferred_fields()
    assert {"signature_png", "stamp_png"} <= LegalEntity.objects.get(
        pk=entity.pk
    ).get_deferred_fields()


def test_related_invoice_reads_do_not_load_archives(admin_client, org_a):
    from django.utils import timezone

    from invoices.models import Invoice, Payment

    invoice = Invoice.objects.create(
        org=org_a, invoice_title="Existing", total_amount="100", amount_due="100"
    )
    payment = Payment.objects.create(
        org=org_a,
        invoice=invoice,
        amount="1.00",
        payment_date=timezone.localdate(),
        payment_method="BANK_TRANSFER",
    )
    with CaptureQueriesContext(connection) as queries:
        response = admin_client.delete(
            f"/api/invoices/{invoice.pk}/payments/{payment.pk}/"
        )
    assert response.status_code == 200
    for query in queries:
        if query["sql"].lstrip().upper().startswith("SELECT"):
            assert "archived_pdf_" not in query["sql"]


def test_timesheet_does_not_join_invoice_archive_bytes(admin_client):
    with CaptureQueriesContext(connection) as queries:
        response = admin_client.get("/api/time-entries/timesheet/")
    assert response.status_code == 200
    for query in queries:
        if query["sql"].lstrip().upper().startswith("SELECT"):
            assert "archived_pdf_" not in query["sql"]
