from django.contrib import admin
from django.urls import include, path

from cuentas.cron import mantenimiento

urlpatterns = [
    path("api/internal/cron/mantenimiento/", mantenimiento, name="cron_mantenimiento"),
    path("admin/", admin.site.urls),
    path("", include("monitoreo.urls")),
]

handler400 = "monitoreo.views.error_400"
