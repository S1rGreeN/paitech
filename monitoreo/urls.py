from django.urls import path

from . import views

app_name = "monitoreo"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("", views.dashboard, name="dashboard"),
    path("piscinas/<int:piscina_id>/", views.piscina_detalle, name="piscina_detalle"),
    path("piscinas/<int:piscina_id>/registros/nuevo/", views.registro_nuevo, name="registro_nuevo"),
    path("registros/<int:registro_id>/", views.registro_detalle, name="registro_detalle"),
]
