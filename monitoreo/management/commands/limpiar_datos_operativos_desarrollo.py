import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from monitoreo.models import (
    AuditoriaCambio,
    CicloProductivo,
    DispositivoSensor,
    JornadaRegistro,
    LecturaSensor,
    MovimientoPoblacion,
)


CONFIRMACION = "BORRAR-DATOS-DESARROLLO"


class Command(BaseCommand):
    help = "Elimina datos operativos ficticios solo en un entorno de desarrollo verificado."

    def add_arguments(self, parser):
        parser.add_argument("--ejecutar", action="store_true")
        parser.add_argument("--confirmar", default="")

    def handle(self, *args, **options):
        entorno = (
            os.getenv("RAILWAY_ENVIRONMENT_NAME")
            or os.getenv("PAIPAY_ENVIRONMENT")
            or ""
        ).strip().lower()
        permitido = settings.DEBUG or entorno in {"development", "dev", "local", "test"}
        if not permitido:
            raise CommandError(
                "Operación rechazada: el entorno no está identificado como desarrollo."
            )

        modelos = (
            ("auditorías operativas", AuditoriaCambio),
            ("lecturas de sensores", LecturaSensor),
            ("movimientos", MovimientoPoblacion),
            ("jornadas", JornadaRegistro),
            ("ciclos", CicloProductivo),
            ("dispositivos sensores de prueba", DispositivoSensor),
        )
        self.stdout.write("Conteos operativos actuales:")
        for etiqueta, modelo in modelos:
            self.stdout.write(f"- {etiqueta}: {modelo.objects.count()}")

        if not options["ejecutar"]:
            self.stdout.write(
                self.style.WARNING(
                    "Vista previa: no se eliminó nada. Usa --ejecutar "
                    f"--confirmar {CONFIRMACION} después de revisar los conteos."
                )
            )
            return
        if options["confirmar"] != CONFIRMACION:
            raise CommandError("La frase de confirmación no coincide; no se eliminó nada.")

        with transaction.atomic():
            for _, modelo in modelos:
                modelo.objects.all().delete()

        self.stdout.write(self.style.SUCCESS("Limpieza operativa completada."))
        for etiqueta, modelo in modelos:
            self.stdout.write(f"- {etiqueta}: {modelo.objects.count()}")
        self.stdout.write(
            "Se conservaron usuarios, perfiles, comunidades, especies y piscinas."
        )
