import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from legacy.tests.test_access import linked_context


def test_history_api_hides_counts_search_and_foreign_rows(
    org_a,
    tmp_path,
    regular_user,
    user_client,
    admin_client,
    org_b_client,
    unauthenticated_client,
):
    ctx = linked_context(org_a, tmp_path, regular_user)
    pk = ctx.record_id("emails", "e")
    url = f"/api/legacy/records/{pk}/"
    assert user_client.get(url).status_code == 404
    assert user_client.get("/api/legacy/records/?q=Secret").json()["count"] == 0
    assert org_b_client.get(url).status_code == 404
    assert org_b_client.get("/api/legacy/records/").json()["count"] == 0
    assert unauthenticated_client.get(url).status_code in (401, 403)
    response = admin_client.get(url)
    assert response.status_code == 200
    assert response.json()["fields"]["name"] == "Secret phrase"
    assert {r["source_table"] for r in response.json()["links"]} == {
        "accounts",
        "emails_text",
    }
    assert admin_client.post("/api/legacy/records/", {}).status_code == 405
    assert (
        admin_client.patch(url, {"is_historical": False}, format="json").status_code
        == 405
    )
    listing = admin_client.get("/api/legacy/records/").json()
    assert all(
        "fields" not in row and "payload" not in row for row in listing["results"]
    )


@pytest.mark.parametrize(
    "query",
    [
        "limit=no",
        "limit=101",
        "offset=-1",
        "offset=999999999999999999999999999",
        "deleted=yes",
        "from=not-a-date",
        "table=not_a_table",
        "kind=wat",
    ],
)
def test_invalid_history_filters_are_400(admin_client, query):
    assert admin_client.get("/api/legacy/records/?" + query).status_code == 400


def test_page_queries_are_bounded(org_a, tmp_path, regular_user, user_client):
    linked_context(org_a, tmp_path, regular_user)
    with CaptureQueriesContext(connection) as queries:
        response = user_client.get("/api/legacy/records/?limit=50")
    assert response.status_code == 200
    assert len(queries) < 25


def test_message_fulltext_and_global_search_find_body(org_a, tmp_path, admin_client):
    from legacy.importer.communications import project_communications
    from legacy.tests.helpers import make_context

    ctx = make_context(
        org_a,
        tmp_path,
        {
            "emails": [{"id": "e", "name": "Old message"}],
            "emails_text": [{"email_id": "e", "description": "Needlebodytoken"}],
        },
    )
    project_communications(ctx)
    response = admin_client.get("/api/legacy/records/?kind=email&q=Needlebodytoken")
    assert response.status_code == 200
    assert response.json()["count"] == 1
    result = admin_client.get("/api/search/?q=Needlebodytoken").json()
    assert any(
        r["type"] == "legacy" and r["id"] == str(ctx.record_id("emails", "e"))
        for r in result["results"]
    )
