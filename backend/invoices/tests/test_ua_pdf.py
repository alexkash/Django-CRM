import pytest

from invoices.tests.ua_helpers import create_invoice, scan_bytes


def test_preview_has_no_issuing_side_effect_and_variants_are_validated(
    admin_client, org_a
):
    inv = create_invoice(admin_client, org_a)
    url = "/api/invoices/" + inv["id"] + "/pdf/"
    preview = admin_client.get(url)
    assert preview.status_code == 200
    assert preview.content.startswith(b"%PDF-")
    from invoices.models import DocumentSequence, Invoice

    stored = Invoice.objects.get(pk=inv["id"])
    assert stored.issued_at is None
    assert (
        DocumentSequence.objects.get(entity=stored.issuer, kind="INVOICE").last_value
        == 0
    )
    assert admin_client.get(url + "?variant=not-valid").status_code == 400


def test_print_scans_and_archives_never_follow_later_edits(admin_client, org_a):
    inv = create_invoice(admin_client, org_a)
    from invoices.models import Invoice, LegalEntity

    LegalEntity.objects.filter(pk=inv["issuer"]["id"]).update(
        signature_png=scan_bytes(), signature_sha256="a" * 64
    )
    url = "/api/invoices/" + inv["id"] + "/"
    assert admin_client.post(url + "issue/", {}, format="json").status_code == 200
    clean = admin_client.get(url + "pdf/?variant=clean")
    stamped = admin_client.get(url + "pdf/?variant=stamped")
    assert clean.content.startswith(b"%PDF-")
    assert stamped.content.startswith(b"%PDF-")
    assert clean.content != stamped.content
    assert clean["Cache-Control"] == "private, no-store"
    LegalEntity.objects.filter(pk=inv["issuer"]["id"]).update(
        legal_name="Changed", signature_png=None
    )
    Invoice.objects.filter(pk=inv["id"]).update(amount_paid="100.00")
    assert admin_client.get(url + "pdf/?variant=clean").content == clean.content
    assert admin_client.get(url + "pdf/?variant=stamped").content == stamped.content


def test_bound_pdf_resources_refuse_arbitrary_file_and_network_urls():
    from invoices.billing.pdf import BillingResources

    fetcher = BillingResources({"billing-asset://signature": b"png"})
    for url in [
        "file:///etc/passwd",
        "http://127.0.0.1/",
        "data:text/html,hello",
        "billing-asset://other",
    ]:
        import pytest

        with pytest.raises(ValueError):
            fetcher(url)


@pytest.mark.parametrize("kind", ["invoice", "act"])
def test_supplied_vat_registration_numbers_are_printed(kind):
    from django.template.loader import render_to_string

    html = render_to_string(
        "invoices/pdf/ua/" + kind + ".html",
        {
            "d": {
                "kind": kind,
                "seller": {
                    "legal_name": "Seller",
                    "vat_registration_number": "111111111111",
                },
                "customer": {
                    "legal_name": "Customer",
                    "vat_registration_number": "222222222222",
                },
                "payer": {},
                "bank": {},
                "lines": [],
            }
        },
    )
    assert "111111111111" in html
    assert "222222222222" in html
