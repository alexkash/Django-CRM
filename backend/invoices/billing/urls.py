from django.urls import path

from . import views

urlpatterns = [
    path("legal-entities/", views.LegalEntityListView.as_view()),
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
