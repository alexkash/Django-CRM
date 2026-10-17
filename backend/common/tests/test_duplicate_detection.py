"""The matching rules in `common.duplicate_detection`.

Every search here runs through a read-rule queryset, as the views do, and the
visibility cases prove a record the caller cannot open is never returned.
"""

import pytest

from accounts.access import visible_accounts_qs
from accounts.models import Account
from common.duplicate_detection import (
    MAX_RESULTS,
    account_name_core,
    find_duplicates,
    normalize_domain,
)
from contacts.access import visible_contacts_qs
from contacts.models import Contact
from leads.access import visible_leads_qs
from leads.models import Lead


def _ids(found):
    return {record.id for record, _reasons in found}


def _leads(profile):
    return visible_leads_qs(profile)


def _accounts(profile):
    return visible_accounts_qs(profile)


@pytest.mark.parametrize(
    "model, visible",
    [
        (Account, visible_accounts_qs),
        (Contact, visible_contacts_qs),
        (Lead, visible_leads_qs),
    ],
)
class TestUnusableContactDetails:
    @pytest.mark.parametrize(
        "email",
        [
            None,
            "",
            "   ",
            "-",
            "not-an-email",
            "no-reply@gmail.com",
            "NO_REPLY@GMAIL.COM",
            "noreply@acme.com",
            "do.not.reply@acme.com",
            "no-reply+crm@acme.com",
            "noemail@acme.com",
            "test@example.com",
            "person@sub.example.org",
            "person@sample.invalid",
            "person@sample.test",
        ],
    )
    def test_unusable_email_is_not_a_match(
        self, org_a, admin_profile, model, visible, email
    ):
        model.objects.create(org=org_a, email=email)
        assert find_duplicates(visible(admin_profile), {"email": email}) == []

    @pytest.mark.parametrize(
        "phone",
        [
            None,
            "",
            "   ",
            "-",
            "12345",
            "0000000",
            "+1 (000) 000-0000",
            "1111111111",
            "0123456789",
            "1234567890",
            "9876543210",
        ],
    )
    def test_unusable_phone_is_not_a_match(
        self, org_a, admin_profile, model, visible, phone
    ):
        model.objects.create(org=org_a, phone=phone)
        assert find_duplicates(visible(admin_profile), {"phone": phone}) == []

    def test_name_still_matches_without_claiming_placeholder_details_match(
        self, org_a, admin_profile, model, visible
    ):
        name = (
            {"name": "Acme"}
            if model is Account
            else {"first_name": "Alice", "last_name": "Smith"}
        )
        criteria = {**name, "email": "no-reply@gmail.com", "phone": "0000000000"}
        record = model.objects.create(org=org_a, **criteria)
        assert find_duplicates(visible(admin_profile), criteria) == [(record, ["name"])]

    @pytest.mark.parametrize(
        "email",
        ["sales@acme.com", "info@gmail.com", "test@acme.com", "no-reply-team@acme.com"],
    )
    def test_real_mailboxes_still_match(
        self, org_a, admin_profile, model, visible, email
    ):
        record = model.objects.create(org=org_a, email=email)
        assert find_duplicates(visible(admin_profile), {"email": email.upper()}) == [
            (record, ["email"])
        ]


class TestNormalisers:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("", ""),
            (None, ""),
            ("https://www.example.com/about?x=1", "example.com"),
            ("HTTP://Example.COM", "example.com"),
            ("example.com/path", "example.com"),
        ],
    )
    def test_normalize_domain(self, raw, expected):
        assert normalize_domain(raw) == expected

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("Acme", ["acme"]),
            ("ACME, Inc.", ["acme"]),
            ("The Acme Co., Ltd.", ["acme"]),
            ("Acme Widgets", ["acme", "widgets"]),
            ("", []),
        ],
    )
    def test_account_name_core(self, raw, expected):
        assert account_name_core(raw) == expected


class TestPhone:
    def test_separators_and_country_code_do_not_matter(self, org_a, admin_profile):
        a = Contact.objects.create(
            org=org_a, first_name="A", last_name="One", phone="555.123.4567"
        )
        b = Contact.objects.create(
            org=org_a, first_name="B", last_name="Two", phone="+1 555 123 4567"
        )
        Contact.objects.create(
            org=org_a, first_name="C", last_name="Three", phone="555-123-4568"
        )
        found = find_duplicates(
            visible_contacts_qs(admin_profile), {"phone": "(555) 123-4567"}
        )
        assert _ids(found) == {a.id, b.id}
        assert all(reasons == ["phone"] for _r, reasons in found)

    def test_a_short_number_must_match_whole(self, org_a, admin_profile):
        whole = Contact.objects.create(
            org=org_a, first_name="A", last_name="One", phone="555-1234"
        )
        Contact.objects.create(
            org=org_a, first_name="B", last_name="Two", phone="1-555-1234"
        )
        found = find_duplicates(
            visible_contacts_qs(admin_profile), {"phone": "5551234"}
        )
        assert _ids(found) == {whole.id}

    def test_too_few_digits_match_nothing(self, org_a, admin_profile):
        Contact.objects.create(org=org_a, first_name="A", last_name="B", phone="12345")
        assert (
            find_duplicates(visible_contacts_qs(admin_profile), {"phone": "12345"})
            == []
        )


class TestContacts:
    def test_email_is_case_insensitive(self, org_a, admin_profile):
        alice = Contact.objects.create(
            org=org_a, first_name="Alice", last_name="Smith", email="alice@x.com"
        )
        found = find_duplicates(
            visible_contacts_qs(admin_profile), {"email": "ALICE@X.COM"}
        )
        assert _ids(found) == {alice.id}
        assert found[0][1] == ["email"]

    def test_name_needs_both_halves(self, org_a, admin_profile):
        alice = Contact.objects.create(org=org_a, first_name="Alice", last_name="Smith")
        Contact.objects.create(org=org_a, first_name="Alice", last_name="Jones")
        visible = visible_contacts_qs(admin_profile)
        assert find_duplicates(visible, {"first_name": "Alice"}) == []
        found = find_duplicates(visible, {"first_name": "alice", "last_name": "SMITH"})
        assert _ids(found) == {alice.id}

    def test_inactive_contacts_are_left_out(self, org_a, admin_profile):
        Contact.objects.create(
            org=org_a, first_name="A", last_name="B", email="a@x.com", is_active=False
        )
        assert (
            find_duplicates(visible_contacts_qs(admin_profile), {"email": "a@x.com"})
            == []
        )

    def test_a_contact_the_caller_cannot_open_is_never_returned(
        self, org_a, admin_user, user_profile
    ):
        Contact.objects.create(
            org=org_a,
            first_name="Hidden",
            last_name="Person",
            email="hidden@x.com",
            created_by=admin_user,
        )
        mine = Contact.objects.create(
            org=org_a,
            first_name="Hidden",
            last_name="Person",
            created_by=user_profile.user,
        )
        found = find_duplicates(
            visible_contacts_qs(user_profile),
            {"email": "hidden@x.com", "first_name": "Hidden", "last_name": "Person"},
        )
        assert _ids(found) == {mine.id}


class TestLeads:
    def test_company_alone_matches_only_exactly_and_only_without_a_name(
        self, org_a, admin_profile
    ):
        acme = Lead.objects.create(org=org_a, company_name="Acme")
        Lead.objects.create(org=org_a, company_name="Acme Widgets")
        visible = _leads(admin_profile)
        found = find_duplicates(visible, {"company_name": "acme"})
        assert _ids(found) == {acme.id}
        assert found[0][1] == ["company"]
        # Two people at one company are two leads.
        assert (
            find_duplicates(
                visible,
                {"company_name": "Acme", "first_name": "Bo", "last_name": "Diddley"},
            )
            == []
        )

    def test_converted_leads_are_left_out(self, org_a, admin_profile):
        Lead.objects.create(
            org=org_a, email="c@x.com", status="converted", first_name="C"
        )
        assert find_duplicates(_leads(admin_profile), {"email": "c@x.com"}) == []

    def test_exclude_id_leaves_the_record_itself_out(self, org_a, admin_profile):
        lead = Lead.objects.create(org=org_a, email="me@x.com")
        assert (
            find_duplicates(_leads(admin_profile), {"email": "me@x.com"}, lead.id) == []
        )

    def test_a_lead_the_caller_cannot_open_is_never_returned(
        self, org_a, admin_user, user_profile
    ):
        Lead.objects.create(org=org_a, email="h@x.com", created_by=admin_user)
        assert find_duplicates(_leads(user_profile), {"email": "h@x.com"}) == []

    def test_results_are_capped(self, org_a, admin_profile):
        for i in range(MAX_RESULTS + 3):
            Lead.objects.create(org=org_a, first_name="Same", last_name="Name")
        found = find_duplicates(
            _leads(admin_profile), {"first_name": "Same", "last_name": "Name"}
        )
        assert len(found) == MAX_RESULTS


class TestAccounts:
    def test_placeholder_matches_do_not_hide_a_real_name_match(
        self, org_a, admin_profile
    ):
        real = Account.objects.create(
            org=org_a, name="Acme", email="no-reply@gmail.com"
        )
        for i in range(MAX_RESULTS + 1):
            Account.objects.create(
                org=org_a, name=f"Other {i}", email="no-reply@gmail.com"
            )
        assert find_duplicates(
            _accounts(admin_profile), {"name": "Acme", "email": "no-reply@gmail.com"}
        ) == [(real, ["name"])]

    def test_legal_suffixes_and_punctuation_are_set_aside(self, org_a, admin_profile):
        inc = Account.objects.create(org=org_a, name="ACME, Inc.")
        the = Account.objects.create(org=org_a, name="The Acme LLC")
        Account.objects.create(org=org_a, name="Acme Widgets")
        found = find_duplicates(_accounts(admin_profile), {"name": "Acme"})
        assert _ids(found) == {inc.id, the.id}
        assert all(reasons == ["name"] for _r, reasons in found)

    def test_a_shared_first_word_is_not_a_duplicate(self, org_a, admin_profile):
        # The old rule matched the first word with istartswith, so every
        # "Global ..." account in the org paired with every other.
        Account.objects.create(org=org_a, name="Global Foods")
        assert find_duplicates(_accounts(admin_profile), {"name": "Global Tech"}) == []

    def test_regex_characters_in_a_name_are_literal(self, org_a, admin_profile):
        Account.objects.create(org=org_a, name="A+B Studio")
        Account.objects.create(org=org_a, name="AAB Studio")
        found = find_duplicates(_accounts(admin_profile), {"name": "a+b studio"})
        assert [r.name for r, _ in found] == ["A+B Studio"]

    def test_website_matches_by_host(self, org_a, admin_profile):
        acme = Account.objects.create(
            org=org_a, name="One", website="http://acme.com/about"
        )
        Account.objects.create(org=org_a, name="Two", website="https://notacme.com")
        found = find_duplicates(
            _accounts(admin_profile), {"website": "https://www.ACME.com"}
        )
        assert _ids(found) == {acme.id}
        assert found[0][1] == ["website"]

    def test_email_and_phone(self, org_a, admin_profile):
        acme = Account.objects.create(
            org=org_a, name="One", email="hi@acme.com", phone="202 555 0147"
        )
        found = find_duplicates(
            _accounts(admin_profile), {"email": "HI@acme.com", "phone": "2025550147"}
        )
        assert _ids(found) == {acme.id}
        assert found[0][1] == ["email", "phone"]

    def test_an_account_the_caller_cannot_open_is_never_returned(
        self, org_a, admin_user, user_profile
    ):
        Account.objects.create(org=org_a, name="Secret", created_by=admin_user)
        assert find_duplicates(_accounts(user_profile), {"name": "Secret"}) == []

    def test_nothing_to_match_on_returns_nothing(self, org_a, admin_profile):
        Account.objects.create(org=org_a, name="Acme")
        assert find_duplicates(_accounts(admin_profile), {}) == []
        assert find_duplicates(_accounts(admin_profile), {"name": "  "}) == []
