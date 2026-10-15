from common.models import Profile, User
from legacy.tests.helpers import make_context, people_tables


def test_existing_user_keeps_password_and_global_rights(org_a, admin_user, tmp_path):
    try:
        from legacy.importer.people import project_people
    except ModuleNotFoundError as exc:
        raise AssertionError("People projector not implemented") from exc
    before = (admin_user.password, admin_user.is_superuser, admin_user.is_staff)
    ctx = make_context(org_a, tmp_path, people_tables(admin_user.email))
    project_people(ctx)
    admin_user.refresh_from_db()
    assert (admin_user.password, admin_user.is_superuser, admin_user.is_staff) == before
    assert ctx.native_id("users", "1") == admin_user.id


def test_new_source_admin_is_org_admin_without_reusable_password(org_a, tmp_path):
    try:
        from legacy.importer.people import project_people
    except ModuleNotFoundError as exc:
        raise AssertionError("People projector not implemented") from exc
    tables = people_tables("source-admin@example.com")
    tables["users"][0]["is_admin"] = 1
    ctx = make_context(org_a, tmp_path, tables)
    project_people(ctx)
    user = User.objects.get(email="source-admin@example.com")
    assert not user.has_usable_password()
    assert not user.is_superuser and not user.is_staff
    assert Profile.objects.get(org=org_a, user=user).role == "ADMIN"
    assert Profile.objects.get(org=org_a, user=user).is_organization_admin is True
