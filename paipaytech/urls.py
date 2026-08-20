from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("monitoreo.urls")),
]

handler400 = "monitoreo.views.error_400"
