from django.urls import path

from . import views

urlpatterns = [
    path("acts/", views.ServiceActListView.as_view()),
    path("acts/<uid:pk>/", views.ServiceActDetailView.as_view()),
    path(
        "acts/<uid:pk>/issue/",
        views.ServiceActActionView.as_view(),
        {"action": "issue"},
    ),
    path(
        "acts/<uid:pk>/cancel/",
        views.ServiceActActionView.as_view(),
        {"action": "cancel"},
    ),
    path("acts/<uid:pk>/pdf/", views.ServiceActPDFView.as_view()),
    path("legal-entities/", views.LegalEntityListView.as_view()),
    path(
        "legal-entities/<uid:pk>/scans/logo/",
        views.ScanView.as_view(),
        {"kind": "logo"},
    ),
    path("legal-entities/<uid:pk>/", views.LegalEntityDetailView.as_view()),
    path("legal-entities/<uid:pk>/bank-accounts/", views.BankAccountListView.as_view()),
    path(
        "legal-entities/<uid:pk>/bank-accounts/<uid:bank_id>/",
        views.BankAccountDetailView.as_view(),
    ),
    path(
        "legal-entities/<uid:pk>/scans/signature/",
        views.ScanView.as_view(),
        {"kind": "signature"},
    ),
    path(
        "legal-entities/<uid:pk>/scans/stamp/",
        views.ScanView.as_view(),
        {"kind": "stamp"},
    ),
]
