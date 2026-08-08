import os

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from monitoreo.models import Comunidad, Especie, JornadaRegistro, Piscina
from monitoreo.services import crear_jornada


class Command(BaseCommand):
    help = "Crea usuarios, catálogos y una jornada de demostración sin duplicarlos."

    def handle(self, *args, **options):
        comunidad, _ = Comunidad.objects.get_or_create(codigo="paipayales", defaults={"nombre": "Paipayales"})
        especie, _ = Especie.objects.get_or_create(
            nombre_comun="Vieja Azul",
            defaults={"nombre_cientifico": "Andinoacara rivulatus"},
        )
        User = get_user_model()
        acuicultor, creado = User.objects.get_or_create(
            email="acuicultor@paipay.local",
            defaults={"first_name": "María", "last_name": "Acuicultora"},
        )
        if creado:
            acuicultor.set_password(os.environ["PAIPAY_ACUICULTOR_PASSWORD"])
            acuicultor.save(update_fields=["password"])
        admin, admin_creado = User.objects.get_or_create(
            email="admin@paipay.local",
            defaults={"first_name": "Administrador", "is_staff": True, "is_superuser": True},
        )
        if admin_creado:
            admin.set_password(os.environ["PAIPAY_ADMIN_PASSWORD"])
            admin.save(update_fields=["password"])
        for usuario in (acuicultor, admin):
            usuario.perfil_acuicultor.comunidad = comunidad
            usuario.perfil_acuicultor.save(update_fields=["comunidad"])

        piscina_peces, _ = Piscina.objects.get_or_create(
            comunidad=comunidad,
            codigo="P-01",
            defaults={
                "nombre": "Piscina 1 Paipayales",
                "tipo": Piscina.Tipo.PECES,
                "especie": especie,
                "area_m2": Decimal("120.00"),
                "descripcion": "Calidad del agua, población y biometría de Vieja Azul.",
            },
        )
        Piscina.objects.get_or_create(
            comunidad=comunidad,
            codigo="LOM-01",
            defaults={
                "nombre": "Lecho de Lombricultura 1",
                "tipo": Piscina.Tipo.LOMBRICES,
                "area_m2": Decimal("12.00"),
                "descripcion": "Módulo visible como Próximamente.",
            },
        )
        if not piscina_peces.registros.exists():
            crear_jornada(
                actor=acuicultor,
                piscina=piscina_peces,
                capturada_en=timezone.now(),
                poblacion_estimada=1250,
                observaciones="Actividad normal durante la alimentación.",
                fuente=JornadaRegistro.Fuente.WEB,
                agua={"ph": Decimal("7.20"), "nitrato": Decimal("20"), "nitrito": Decimal("0.25"), "amoniaco_total": Decimal("0.25")},
                peces=[
                    {"peso_gramos": Decimal("315.40"), "talla_centimetros": Decimal("23.80")},
                    {"peso_gramos": Decimal("328.10"), "talla_centimetros": Decimal("24.20")},
                    {"peso_gramos": Decimal("309.90"), "talla_centimetros": Decimal("23.50")},
                ],
            )
        self.stdout.write(self.style.SUCCESS("Datos demo listos."))
        self.stdout.write("Acuicultor: acuicultor@paipay.local / ${PAIPAY_ACUICULTOR_PASSWORD}")
        self.stdout.write("Admin: admin@paipay.local / ${PAIPAY_ADMIN_PASSWORD}")
