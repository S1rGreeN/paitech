from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from monitoreo.models import Comunidad, Especie, Piscina


class Command(BaseCommand):
    help = "Crea o valida el catálogo real mínimo de Paipayales sin datos demo."

    @transaction.atomic
    def handle(self, *args, **options):
        comunidad, comunidad_creada = Comunidad.objects.get_or_create(
            codigo="paipayales",
            defaults={"nombre": "Paipayales", "activa": True},
        )
        if comunidad.nombre != "Paipayales" or not comunidad.activa:
            raise CommandError(
                "El código paipayales existe con otro nombre o está inactivo; revísalo antes de continuar."
            )

        especie, especie_creada = Especie.objects.get_or_create(
            nombre_comun="Vieja Azul",
            defaults={
                "nombre_cientifico": "Andinoacara rivulatus",
                "activa": True,
            },
        )
        if especie.nombre_cientifico != "Andinoacara rivulatus" or not especie.activa:
            raise CommandError(
                "Vieja Azul existe con otro nombre científico o está inactiva; revísala antes de continuar."
            )

        piscina, piscina_creada = Piscina.objects.get_or_create(
            comunidad=comunidad,
            codigo="P-01",
            defaults={
                "nombre": "Piscina 1 Paipayales",
                "tipo": Piscina.Tipo.PECES,
                "especie": especie,
                "area_m2": None,
                "descripcion": "",
                "activa": True,
            },
        )
        if (
            piscina.nombre != "Piscina 1 Paipayales"
            or piscina.tipo != Piscina.Tipo.PECES
            or piscina.especie_id != especie.id
            or not piscina.activa
        ):
            raise CommandError(
                "P-01 ya existe con nombre, tipo o especie diferentes; no se modificó automáticamente."
            )

        if comunidad_creada:
            self.stdout.write("Comunidad Paipayales creada.")
        if especie_creada:
            self.stdout.write("Especie Vieja Azul creada.")
        if piscina_creada:
            self.stdout.write("Piscina P-01 creada con área vacía.")

        self.stdout.write(
            self.style.SUCCESS(
                "Catálogo real listo: Paipayales, Vieja Azul y P-01. "
                "No se crearon usuarios, jornadas ni LOM-01."
            )
        )
