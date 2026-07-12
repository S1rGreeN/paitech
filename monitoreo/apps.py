from django.apps import AppConfig


class MonitoreoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "monitoreo"
    verbose_name = "Monitoreo acuícola"

    def ready(self):
        import monitoreo.signals  # noqa: F401
