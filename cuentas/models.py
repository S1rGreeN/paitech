import hashlib
import secrets
import uuid
from datetime import timedelta

from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


VIGENCIA_TOKEN_DISPOSITIVO = timedelta(days=30)


class UsuarioManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("El correo electrónico es obligatorio.")
        email = self.normalize_email(email).lower()
        usuario = self.model(email=email, **extra_fields)
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Un superusuario debe tener is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Un superusuario debe tener is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


class Usuario(AbstractUser):
    username = None
    debe_cambiar_clave = models.BooleanField(
        "debe cambiar la contraseña",
        default=False,
        help_text="Obliga a reemplazar la contraseña temporal en el siguiente acceso.",
    )
    email = models.EmailField("correo electrónico", unique=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UsuarioManager()

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"
        ordering = ["email"]

    def __str__(self):
        return self.get_full_name() or self.email


class TokenDispositivo(models.Model):
    """Sesión móvil revocable; el secreto original nunca se guarda."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name="tokens_dispositivo")
    dispositivo_id = models.CharField(max_length=128)
    nombre_dispositivo = models.CharField(max_length=160, blank=True)
    secreto_hash = models.CharField(max_length=64, editable=False)
    creado_en = models.DateTimeField(auto_now_add=True)
    ultimo_uso_en = models.DateTimeField(default=timezone.now)
    expira_en = models.DateTimeField()
    revocado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "sesión de dispositivo"
        verbose_name_plural = "sesiones de dispositivos"
        ordering = ["-ultimo_uso_en"]
        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "dispositivo_id"],
                name="cuentas_token_usuario_dispositivo_unico",
            )
        ]
        indexes = [
            models.Index(fields=["expira_en"], name="token_expira_idx"),
            models.Index(fields=["revocado_en"], name="token_revocado_idx"),
        ]

    @staticmethod
    def hash_secreto(secreto):
        return hashlib.sha256(secreto.encode("utf-8")).hexdigest()

    @classmethod
    def emitir(cls, *, usuario, dispositivo_id, nombre_dispositivo=""):
        secreto = secrets.token_urlsafe(32)
        ahora = timezone.now()
        token, _ = cls.objects.update_or_create(
            usuario=usuario,
            dispositivo_id=dispositivo_id,
            defaults={
                "nombre_dispositivo": nombre_dispositivo,
                "secreto_hash": cls.hash_secreto(secreto),
                "ultimo_uso_en": ahora,
                "expira_en": ahora + VIGENCIA_TOKEN_DISPOSITIVO,
                "revocado_en": None,
            },
        )
        return token, f"{token.id}.{secreto}"

    @property
    def esta_vigente(self):
        return self.revocado_en is None and self.expira_en > timezone.now() and self.usuario.is_active

    def revocar(self, *, momento=None):
        if self.revocado_en is None:
            self.revocado_en = momento or timezone.now()
            self.save(update_fields=["revocado_en"])

    def __str__(self):
        return f"{self.usuario.email} · {self.nombre_dispositivo or self.dispositivo_id}"


class ControlIntentoLogin(models.Model):
    email_normalizado = models.CharField(max_length=254)
    direccion_ip = models.CharField(max_length=45)
    ventana_iniciada_en = models.DateTimeField(default=timezone.now)
    fallos = models.PositiveSmallIntegerField(default=0)
    bloqueos_acumulados = models.PositiveSmallIntegerField(default=0)
    bloqueado_hasta = models.DateTimeField(null=True, blank=True)
    ultimo_intento_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "control de intentos de acceso"
        verbose_name_plural = "controles de intentos de acceso"
        constraints = [
            models.UniqueConstraint(
                fields=["email_normalizado", "direccion_ip"],
                name="cuentas_login_email_ip_unico",
            )
        ]
        indexes = [
            models.Index(fields=["bloqueado_hasta"], name="login_bloqueo_idx"),
            models.Index(fields=["ultimo_intento_en"], name="login_ultimo_idx"),
        ]

    def __str__(self):
        return f"{self.email_normalizado} · {self.direccion_ip}"


class EventoSeguridad(models.Model):
    class Tipo(models.TextChoices):
        LOGIN_EXITOSO = "login_exitoso", "Inicio de sesión exitoso"
        LOGIN_FALLIDO = "login_fallido", "Inicio de sesión fallido"
        LOGIN_BLOQUEADO = "login_bloqueado", "Inicio de sesión bloqueado"
        LOGOUT = "logout", "Cierre de sesión"
        CLAVE_CAMBIADA = "clave_cambiada", "Contraseña cambiada"
        CLAVE_RESTABLECIDA = "clave_restablecida", "Contraseña restablecida por administración"
        SESIONES_REVOCADAS = "sesiones_revocadas", "Sesiones revocadas"
        CUENTA_DESACTIVADA = "cuenta_desactivada", "Cuenta desactivada"
        CUENTA_DESBLOQUEADA = "cuenta_desbloqueada", "Cuenta desbloqueada"

    tipo = models.CharField(max_length=40, choices=Tipo.choices)
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eventos_seguridad",
    )
    email_normalizado = models.CharField(max_length=254, blank=True)
    direccion_ip = models.CharField(max_length=45, blank=True)
    detalle = models.JSONField(default=dict, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "evento de seguridad"
        verbose_name_plural = "eventos de seguridad"
        ordering = ["-creado_en"]

    def __str__(self):
        return f"{self.get_tipo_display()} · {self.creado_en:%Y-%m-%d %H:%M}"
