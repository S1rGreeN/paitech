from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from cuentas.models import ControlIntentoLogin, EventoSeguridad


class Command(BaseCommand):
    help = "Elimina eventos y controles de acceso con más de 30 días."

    def handle(self, *args, **options):
        limite = timezone.now() - timedelta(days=30)
        eventos, _ = EventoSeguridad.objects.filter(creado_en__lt=limite).delete()
        controles, _ = ControlIntentoLogin.objects.filter(
            ultimo_intento_en__lt=limite
        ).delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Limpieza completada: {eventos} eventos y {controles} controles antiguos."
            )
        )
