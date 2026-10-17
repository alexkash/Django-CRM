from rest_framework.response import Response

from invoices.permissions import visible_invoices_qs

from .models import ServiceAct


def visible_acts_qs(profile):
    return ServiceAct.objects.filter(
        org=profile.org, invoice__in=visible_invoices_qs(profile)
    ).select_related("invoice")


def get_act_or_error(request, pk, *, for_update=False):
    rows = visible_acts_qs(request.profile)
    if for_update:
        rows = rows.select_for_update(of=("self",))
    act = rows.filter(pk=pk).first()
    if act is None:
        return None, Response({"error": True, "message": "Act not found"}, status=404)
    return act, None
