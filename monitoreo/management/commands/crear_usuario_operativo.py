from getpass import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import transaction

from monitoreo.models import Acuicultor, Comunidad
from monitoreo.permisos import configurar_grupo_administradores_funcionales


ROLES = {
    "tecnico": {
        "rol": Acuicultor.Rol.TECNICO,
        "is_staff": True,
        "is_superuser": True,
    },
    "administrador": {
        "rol": Acuicultor.Rol.ADMINISTRADOR,
        "is_staff": True,
        "is_superuser": False,
    },
    "acuicultor": {
        "rol": Acuicultor.Rol.ACUICULTOR,
        "is_staff": False,
        "is_superuser": False,
    },
}


class Command(BaseCommand):
    help = "Crea una cuenta operativa solicitando correo y contraseña de forma interactiva."

    def add_arguments(self, parser):
        parser.add_argument("--rol", required=True, choices=ROLES)

    def handle(self, *args, **options):
        configuracion = ROLES[options["rol"]]
        email = input("Correo: ").strip().lower()
        try:
            validate_email(email)
        except ValidationError as error:
            raise CommandError("El correo no es válido.") from error

        User = get_user_model()
        if User.objects.filter(email__iexact=email).exists():
            raise CommandError("Ya existe un usuario con ese correo.")

        first_name = input("Nombres: ").strip()
        last_name = input("Apellidos: ").strip()
        nombre_sugerido = " ".join(parte for parte in (first_name, last_name) if parte)
        nickname = input(f"Nombre visible [{nombre_sugerido or email.split('@', 1)[0]}]: ").strip()
        nickname = nickname or nombre_sugerido or email.split("@", 1)[0]

        clave = getpass("Contraseña: ")
        confirmacion = getpass("Repita la contraseña: ")
        if clave != confirmacion:
            raise CommandError("Las contraseñas no coinciden.")

        usuario = User(
            email=email,
            first_name=first_name,
            last_name=last_name,
            is_active=True,
            is_staff=configuracion["is_staff"],
            is_superuser=configuracion["is_superuser"],
            debe_cambiar_clave=True,
        )
        try:
            validate_password(clave, user=usuario)
        except ValidationError as error:
            raise CommandError("La contraseña no cumple la política: " + " ".join(error.messages)) from error

        comunidad, _ = Comunidad.objects.get_or_create(
            codigo="paipayales",
            defaults={"nombre": "Paipayales"},
        )
        with transaction.atomic():
            usuario.set_password(clave)
            usuario.save()
            perfil = usuario.perfil_acuicultor
            perfil.comunidad = comunidad
            perfil.nickname = nickname
            perfil.rol = configuracion["rol"]
            perfil.activo = True
            perfil.full_clean()
            perfil.save(update_fields=["comunidad", "nickname", "rol", "activo"])
            if options["rol"] == "administrador":
                grupo = configurar_grupo_administradores_funcionales()
                usuario.groups.add(grupo)

        self.stdout.write(self.style.SUCCESS(f"Usuario {email} creado como {options['rol']}."))
        self.stdout.write("La cuenta deberá cambiar la contraseña temporal en su primer acceso.")
        self.stdout.write("La contraseña no se imprimió ni se guardó en archivos del proyecto.")
