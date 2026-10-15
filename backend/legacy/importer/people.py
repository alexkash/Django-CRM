"""Reuse user identities without importing passwords or global administrator flags."""

from django.contrib.auth.hashers import make_password

from common.models import Profile, User

from .fields import email, flag
from .identity import stable_id


def project_people(ctx, rows=None):
    for row in rows if rows is not None else ctx.reader.rows("users", True):
        data = row["values"]
        key = row["source_id"]
        address = email(ctx.primary_email("Users", key))
        if not address:
            raise ValueError("Source user has no unambiguous valid primary email")
        found = list(User.objects.filter(email__iexact=address))
        if len(found) > 1:
            raise ValueError("Target user email is ambiguous")
        obj = (
            found[0]
            if found
            else User(
                id=stable_id("users", key),
                email=address,
                name=(
                    " ".join(
                        str(data.get(k) or "") for k in ["first_name", "last_name"]
                    ).strip()
                    or str(data.get("user_name") or address.split("@")[0])
                )[:255],
                password=make_password(None),
                is_active=data.get("status") == "Active",
                is_staff=False,
                is_superuser=False,
            )
        )
        user = ctx.write("users", row, obj, reuse=bool(found))
        profile = Profile.objects.filter(org=ctx.org, user=user).first()
        reused = profile is not None
        if not profile:
            profile = Profile(
                id=stable_id("users", key, "profile"),
                org=ctx.org,
                user=user,
                role="ADMIN"
                if flag(data.get("is_admin")) or user.is_superuser
                else "USER",
                has_sales_access=True,
                has_marketing_access=True,
                is_active=user.is_active,
            )
        if not reused:
            profile.is_organization_admin = profile.role == "ADMIN"
        ctx.write("users", row, profile, role="profile", reuse=reused)
    return ctx.results
