"""Real two-connection races, not SQL-lock mocks or SQLite success claims."""

import threading
from types import SimpleNamespace

import pytest
from django.db import close_old_connections, connection

from invoices.tests.ua_helpers import act_payload, create_invoice, issued_invoice

pytestmark = [pytest.mark.postgres_only, pytest.mark.django_db(transaction=True)]


def run_race(org, callables):
    barrier = threading.Barrier(len(callables))
    results = []

    def run(fn):
        close_old_connections()
        from common.tasks import set_rls_context

        try:
            set_rls_context(org.pk)
            barrier.wait(timeout=10)
            value = fn()
            results.append(("ok", value))
        except Exception as exc:
            results.append(("error", getattr(exc, "status_code", None), str(exc)))
        finally:
            connection.close()

    threads = [threading.Thread(target=run, args=(fn,)) for fn in callables]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert all(not thread.is_alive() for thread in threads), results
    return results


def test_concurrent_acts_cannot_close_same_remaining_quantity(
    admin_client, org_a, admin_profile, admin_user
):
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL required")
    inv = issued_invoice(admin_client, org_a)
    ids = []
    for _ in range(2):
        row = admin_client.post(
            "/api/invoices/billing/acts/", act_payload(inv, "12"), format="json"
        )
        assert row.status_code == 201, row.content
        ids.append(row.data["id"])
    actor = SimpleNamespace(profile=admin_profile, user=admin_user)
    from invoices.billing.services import issue_act

    results = run_race(
        org_a,
        [lambda uid=uid: issue_act(actor=actor, act_id=uid).number for uid in ids],
    )
    assert [r[0] for r in results].count("ok") == 1, results
    assert [r[1] for r in results if r[0] == "error"] == [409], results
    from invoices.models import ServiceAct

    assert ServiceAct.objects.filter(invoice_id=inv["id"], status="Issued").count() == 1


def test_same_invoice_issue_is_idempotent_under_concurrency(
    admin_client, org_a, admin_profile, admin_user
):
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL required")
    inv = create_invoice(admin_client, org_a)
    actor = SimpleNamespace(profile=admin_profile, user=admin_user)
    from invoices.billing.services import issue_invoice

    results = run_race(
        org_a,
        [lambda: issue_invoice(actor=actor, invoice_id=inv["id"]).invoice_number] * 2,
    )
    assert results == [("ok", "РХ-000001"), ("ok", "РХ-000001")], results


def test_distinct_invoices_share_one_serialized_company_counter(
    admin_client, org_a, admin_profile, admin_user
):
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL required")
    from invoices.tests.ua_helpers import invoice_payload

    body = invoice_payload(admin_client, org_a)
    ids = []
    for index in range(2):
        row = admin_client.post(
            "/api/invoices/",
            {**body, "invoice_title": f"Concurrent {index}"},
            format="json",
        )
        assert row.status_code == 201, row.content
        ids.append(row.data["invoice"]["id"])
    actor = SimpleNamespace(profile=admin_profile, user=admin_user)
    from invoices.billing.services import issue_invoice

    results = run_race(
        org_a,
        [
            lambda uid=uid: issue_invoice(actor=actor, invoice_id=uid).invoice_number
            for uid in ids
        ],
    )
    assert sorted(results) == [("ok", "РХ-000001"), ("ok", "РХ-000002")], results


def test_cancel_and_reissue_serialize_on_same_invoice(
    admin_client, org_a, admin_profile, admin_user
):
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL required")
    from invoices.billing.services import cancel_act, get_closure_summary, issue_act
    from invoices.models import Invoice

    inv = issued_invoice(admin_client, org_a)
    rows = [
        admin_client.post(
            "/api/invoices/billing/acts/", act_payload(inv, "12"), format="json"
        ).data
        for _ in range(2)
    ]
    actor = SimpleNamespace(profile=admin_profile, user=admin_user)
    issue_act(actor=actor, act_id=rows[0]["id"])
    results = run_race(
        org_a,
        [
            lambda: (
                cancel_act(
                    actor=actor, act_id=rows[0]["id"], reason="Correction"
                ).status
            ),
            lambda: issue_act(actor=actor, act_id=rows[1]["id"]).status,
        ],
    )
    assert ("ok", "Cancelled") in results, results
    assert all(r[0] == "ok" or r[1] == 409 for r in results), results
    summary = get_closure_summary(Invoice.objects.get(pk=inv["id"]))
    assert summary["closed_total"] in ("0.00", "14400.00")
