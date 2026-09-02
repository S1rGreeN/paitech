from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from monitoreo.models import CamaLombrices, Comunidad, Especie, Piscina


class Command(BaseCommand):
    help = "Crea o valida el catálogo real multi-comunidad sin datos operativos."

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

        cama, cama_creada = CamaLombrices.objects.get_or_create(
            comunidad=comunidad,
            codigo="C-01",
            defaults={
                "nombre": "Cama 1 Paipayales",
                "area_m2": None,
                "descripcion": "",
                "activa": True,
            },
        )
        if cama.nombre != "Cama 1 Paipayales" or not cama.activa:
            raise CommandError(
                "C-01 ya existe con nombre o estado diferentes; no se modificó automáticamente."
            )

        galo, galo_creada = Comunidad.objects.get_or_create(
            codigo="colegio-galo-plaza-lasso",
            defaults={"nombre": "Colegio Galo Plaza Lasso", "activa": True},
        )
        if galo.nombre != "Colegio Galo Plaza Lasso" or not galo.activa:
            raise CommandError(
                "La comunidad Colegio Galo Plaza Lasso existe con datos incompatibles."
            )
        tilapia, tilapia_creada = Especie.objects.get_or_create(
            nombre_comun="Tilapia",
            defaults={"nombre_cientifico": "", "activa": True},
        )
        if tilapia.nombre_cientifico or not tilapia.activa:
            raise CommandError(
                "Tilapia existe con un nombre científico o estado no confirmados."
            )
        piscina_galo, piscina_galo_creada = Piscina.objects.get_or_create(
            comunidad=galo,
            codigo="P-01",
            defaults={
                "nombre": "Piscina 1 Colegio Galo Plaza Lasso",
                "tipo": Piscina.Tipo.PECES,
                "especie": tilapia,
                "area_m2": None,
                "descripcion": "",
                "activa": True,
            },
        )
        if (
            piscina_galo.nombre != "Piscina 1 Colegio Galo Plaza Lasso"
            or piscina_galo.especie_id != tilapia.id
            or not piscina_galo.activa
        ):
            raise CommandError(
                "P-01 de Colegio Galo Plaza Lasso tiene datos incompatibles."
            )

        if comunidad_creada:
            self.stdout.write("Comunidad Paipayales creada.")
        if especie_creada:
            self.stdout.write("Especie Vieja Azul creada.")
        if piscina_creada:
            self.stdout.write("Piscina P-01 creada con área vacía.")
        if cama_creada:
            self.stdout.write("Cama C-01 de Paipayales creada con área vacía.")
        if galo_creada:
            self.stdout.write("Comunidad Colegio Galo Plaza Lasso creada.")
        if tilapia_creada:
            self.stdout.write("Especie Tilapia creada sin nombre científico confirmado.")
        if piscina_galo_creada:
            self.stdout.write("Piscina P-01 de Colegio Galo Plaza Lasso creada.")

        self.stdout.write(
            self.style.SUCCESS(
                "Catálogo real listo: Paipayales (P-01 y C-01) y Colegio Galo "
                "Plaza Lasso (P-01). No se crearon usuarios ni registros operativos."
            )
        )
