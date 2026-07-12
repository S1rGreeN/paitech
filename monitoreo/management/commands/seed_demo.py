import os

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from monitoreo.models import MuestraPez, Piscina, Registro


class Command(BaseCommand):
    help = "Crea usuarios, piscinas y registros de demostración sin duplicarlos."

    def handle(self, *args, **options):
        User = get_user_model()

        acuicultor, creado = User.objects.get_or_create(
            username="acuicultor",
            defaults={
                "email": "acuicultor@paipay.local",
                "first_name": "María",
                "last_name": "Acuicultora",
            },
        )
        if creado:
            acuicultor.set_password(os.environ["PAIPAY_ACUICULTOR_PASSWORD"])
            acuicultor.save(update_fields=["password"])

        admin, admin_creado = User.objects.get_or_create(
            username="admin",
            defaults={
                "email": "admin@paipay.local",
                "first_name": "Administrador",
                "is_staff": True,
                "is_superuser": True,
            },
        )
        if admin_creado:
            admin.set_password(os.environ["PAIPAY_ADMIN_PASSWORD"])
            admin.save(update_fields=["password"])

        piscina_peces, _ = Piscina.objects.get_or_create(
            codigo="PZ-001",
            defaults={
                "nombre": "Piscina principal de peces",
                "tipo": Piscina.Tipo.PECES,
                "descripcion": "Monitoreo de calidad del agua, población y muestras biométricas.",
            },
        )
        piscina_lombrices, _ = Piscina.objects.get_or_create(
            codigo="LB-001",
            defaults={
                "nombre": "Piscina de lombrices",
                "tipo": Piscina.Tipo.LOMBRICES,
                "descripcion": "Módulo reservado para el siguiente sprint.",
            },
        )

        perfiles = [acuicultor.perfil_acuicultor, admin.perfil_acuicultor]
        piscina_peces.acuicultores.add(*perfiles)
        piscina_lombrices.acuicultores.add(*perfiles)

        if not piscina_peces.registros.exists():
            registro = Registro.objects.create(
                piscina=piscina_peces,
                acuicultor=acuicultor.perfil_acuicultor,
                fecha=timezone.now(),
                ph=Decimal("7.20"),
                nitrato=Decimal("18.50"),
                amonio=Decimal("0.12"),
                nitrito=Decimal("0.08"),
                poblacion_estimada=1250,
                observaciones="Actividad normal y buena respuesta durante la alimentación.",
            )
            MuestraPez.objects.bulk_create(
                [
                    MuestraPez(
                        registro=registro,
                        especie="Tilapia roja",
                        peso_gramos=Decimal("315.40"),
                        talla_centimetros=Decimal("23.80"),
                    ),
                    MuestraPez(
                        registro=registro,
                        especie="Tilapia roja",
                        peso_gramos=Decimal("328.10"),
                        talla_centimetros=Decimal("24.20"),
                    ),
                    MuestraPez(
                        registro=registro,
                        especie="Tilapia roja",
                        peso_gramos=Decimal("309.90"),
                        talla_centimetros=Decimal("23.50"),
                    ),
                ]
            )

        self.stdout.write(self.style.SUCCESS("Datos demo listos."))
        self.stdout.write("Usuario: acuicultor / ${PAIPAY_ACUICULTOR_PASSWORD}")
        self.stdout.write("Admin: admin / ${PAIPAY_ADMIN_PASSWORD}")
