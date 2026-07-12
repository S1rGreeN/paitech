from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class Acuicultor(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="perfil_acuicultor",
        verbose_name="usuario",
    )
    nickname = models.CharField(max_length=80, unique=True, verbose_name="nombre visible")
    fecha_nacimiento = models.DateField(blank=True, null=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "acuicultor"
        verbose_name_plural = "acuicultores"
        ordering = ["nickname"]

    def __str__(self):
        return self.nickname

    @property
    def correo(self):
        return self.user.email


class Piscina(models.Model):
    class Tipo(models.TextChoices):
        PECES = "peces", "Peces"
        LOMBRICES = "lombrices", "Lombrices"

    nombre = models.CharField(max_length=120)
    codigo = models.CharField(max_length=30, unique=True)
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    descripcion = models.TextField(blank=True)
    acuicultores = models.ManyToManyField(
        Acuicultor,
        related_name="piscinas",
        blank=True,
    )
    activa = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["tipo", "nombre"]
        verbose_name = "piscina"
        verbose_name_plural = "piscinas"

    def __str__(self):
        return f"{self.nombre} ({self.get_tipo_display()})"


class Registro(models.Model):
    piscina = models.ForeignKey(
        Piscina,
        on_delete=models.CASCADE,
        related_name="registros",
    )
    acuicultor = models.ForeignKey(
        Acuicultor,
        on_delete=models.SET_NULL,
        related_name="registros_creados",
        null=True,
        blank=True,
    )
    fecha = models.DateTimeField(default=timezone.now)
    ph = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(14)],
        verbose_name="pH",
    )
    nitrato = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="mg/L",
    )
    amonio = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="mg/L",
    )
    nitrito = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="mg/L",
    )
    poblacion_estimada = models.PositiveIntegerField()
    observaciones = models.TextField(blank=True)

    class Meta:
        ordering = ["-fecha", "-id"]
        verbose_name = "registro"
        verbose_name_plural = "registros"

    def __str__(self):
        return f"Registro {self.id} · {self.piscina.codigo} · {self.fecha:%d/%m/%Y}"


class MuestraPez(models.Model):
    registro = models.ForeignKey(
        Registro,
        on_delete=models.CASCADE,
        related_name="muestras_peces",
    )
    especie = models.CharField(max_length=100)
    peso_gramos = models.DecimalField(
        max_digits=9,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
        verbose_name="peso (g)",
    )
    talla_centimetros = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
        verbose_name="talla (cm)",
    )

    class Meta:
        ordering = ["id"]
        verbose_name = "muestra de pez"
        verbose_name_plural = "muestras de peces"

    def __str__(self):
        return f"{self.especie} · {self.peso_gramos} g"
