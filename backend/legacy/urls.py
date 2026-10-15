from django.urls import path

from .views import (
    BatchReport,
    EntityHistory,
    FileDownload,
    FileList,
    RecordDetail,
    RecordList,
)

app_name = "legacy"
urlpatterns = [
    path("records/", RecordList.as_view()),
    path("records/<uid:pk>/", RecordDetail.as_view()),
    path("files/", FileList.as_view()),
    path("files/<uid:pk>/download/", FileDownload.as_view()),
    path("entities/<str:model>/<uid:pk>/history/", EntityHistory.as_view()),
    path("batches/<uid:pk>/report/", BatchReport.as_view()),
]
