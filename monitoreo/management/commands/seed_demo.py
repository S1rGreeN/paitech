import secrets
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from monitoreo.models import Acuicultor, Comunidad, Especie, JornadaRegistro, Piscina
from monitoreo.services import crear_jornada


def generar_clave_demo(longitud=10):
    """Genera una clave local breve sin depender de valores escritos en el código."""
    if longitud < 8:
        raise ValueError("La clave demo debe tener al menos 8 caracteres.")
    minusculas = "abcdefghijkmnopqrstuvwxyz"
    mayusculas = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    numeros = "23456789"
    simbolos = "!@#%"
    grupos = (minusculas, mayusculas, numeros, simbolos)
    caracteres = [secrets.choice(grupo) for grupo in grupos]
    alfabeto = "".join(grupos)
    caracteres.extend(secrets.choice(alfabeto) for _ in range(longitud - len(grupos)))
    secrets.SystemRandom().shuffle(caracteres)
    return "".join(caracteres)


class Command(BaseCommand):
    help = "Crea datos de demostración exclusivamente en SQLite con DEBUG=True."

    def add_arguments(self, parser):
        parser.add_argument(
            "--rotar-claves",
            action="store_true",
            help="Asigna nuevas claves aleatorias a las dos cuentas demo existentes.",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo está bloqueado cuando DEBUG=False.")
        if settings.DATABASES["default"]["ENGINE"] != "django.db.backends.sqlite3":
            raise CommandError("seed_demo solo puede ejecutarse sobre SQLite local; nunca sobre Neon/PostgreSQL.")

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
        clave_acuicultor = generar_clave_demo() if creado or options["rotar_claves"] else None
        if clave_acuicultor:
            acuicultor.set_password(clave_acuicultor)
        acuicultor.is_active = True
        acuicultor.is_staff = False
        acuicultor.is_superuser = False
        acuicultor.save()
        admin, admin_creado = User.objects.get_or_create(
            email="admin@paipay.local",
            defaults={"first_name": "Administrador", "is_staff": True, "is_superuser": True},
        )
        clave_admin = generar_clave_demo() if admin_creado or options["rotar_claves"] else None
        if clave_admin:
            admin.set_password(clave_admin)
        admin.is_active = True
        admin.is_staff = True
        admin.is_superuser = True
        admin.save()
        for usuario, rol in (
            (acuicultor, Acuicultor.Rol.ACUICULTOR),
            (admin, Acuicultor.Rol.ADMINISTRADOR),
        ):
            usuario.perfil_acuicultor.comunidad = comunidad
            usuario.perfil_acuicultor.rol = rol
            usuario.perfil_acuicultor.activo = True
            usuario.perfil_acuicultor.save(update_fields=["comunidad", "rol", "activo"])

        piscina_peces, _ = Piscina.objects.get_or_create(
            comunidad=comunidad,
            codigo="P-01",
            defaults={
                "nombre": "Piscina 1 Paipayales",
                "tipo": Piscina.Tipo.PECES,
                "especie": especie,
                "area_m2": None,
                "descripcion": "Calidad del agua, población y biometría de Vieja Azul.",
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
        if clave_acuicultor and clave_admin:
            self.stdout.write("Credenciales locales generadas; cópialas ahora:")
            self.stdout.write(f"Acuicultor: acuicultor@paipay.local / {clave_acuicultor}")
            self.stdout.write(f"Admin: admin@paipay.local / {clave_admin}")
        else:
            self.stdout.write(
                "Las cuentas demo ya existían. Usa --rotar-claves para generar claves nuevas."
            )
