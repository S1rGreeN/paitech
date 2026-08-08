import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .calidad_agua import (
    validar_amoniaco_total_kit,
    validar_nitrato_kit,
    validar_nitrito_kit,
    validar_ph_kit,
)


class Comunidad(models.Model):
    codigo = models.SlugField(max_length=40, unique=True)
    nombre = models.CharField(max_length=120, unique=True)
    activa = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "comunidad"
        verbose_name_plural = "comunidades"

    def __str__(self):
        return self.nombre


class Especie(models.Model):
    nombre_comun = models.CharField(max_length=120, unique=True)
    nombre_cientifico = models.CharField(max_length=180, blank=True)
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre_comun"]
        verbose_name = "especie"
        verbose_name_plural = "especies"

    def __str__(self):
        if self.nombre_cientifico:
            return f"{self.nombre_comun} ({self.nombre_cientifico})"
        return self.nombre_comun


class Acuicultor(models.Model):
    class Rol(models.TextChoices):
        ACUICULTOR = "ACUICULTOR", "Acuicultor"
        TECNICO = "TECNICO", "Técnico"
        ADMINISTRADOR = "ADMINISTRADOR", "Administrador"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="perfil_acuicultor",
        verbose_name="usuario",
    )
    comunidad = models.ForeignKey(
        Comunidad,
        on_delete=models.PROTECT,
        related_name="miembros",
    )
    nickname = models.CharField(max_length=80, verbose_name="nombre visible")
    fecha_nacimiento = models.DateField(blank=True, null=True)
    rol = models.CharField(max_length=20, choices=Rol.choices, default=Rol.ACUICULTOR)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "acuicultor"
        verbose_name_plural = "acuicultores"
        ordering = ["nickname"]
        constraints = [
            models.UniqueConstraint(
                fields=["comunidad", "nickname"],
                name="uq_acuicultor_nickname_comunidad",
            )
        ]

    def __str__(self):
        return self.nickname

    @property
    def correo(self):
        return self.user.email


class Piscina(models.Model):
    class Tipo(models.TextChoices):
        PECES = "PECES", "Peces"
        LOMBRICES = "LOMBRICES", "Lombrices"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    comunidad = models.ForeignKey(
        Comunidad,
        on_delete=models.PROTECT,
        related_name="piscinas",
    )
    especie = models.ForeignKey(
        Especie,
        on_delete=models.PROTECT,
        related_name="piscinas",
        null=True,
        blank=True,
        help_text="Obligatoria y permanente para piscinas de peces.",
    )
    nombre = models.CharField(max_length=120)
    codigo = models.CharField(max_length=30)
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    descripcion = models.TextField(blank=True)
    area_m2 = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    activa = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["tipo", "nombre"]
        verbose_name = "piscina"
        verbose_name_plural = "piscinas"
        constraints = [
            models.UniqueConstraint(
                fields=["comunidad", "codigo"],
                name="uq_piscina_codigo_comunidad",
            ),
            models.CheckConstraint(
                condition=Q(tipo="LOMBRICES") | Q(especie__isnull=False),
                name="ck_piscina_peces_con_especie",
            ),
        ]

    def clean(self):
        super().clean()
        self.codigo = self.codigo.strip().upper()
        if self.tipo == self.Tipo.PECES and self.especie_id is None:
            raise ValidationError({"especie": "Una piscina de peces requiere especie."})
        if self.tipo == self.Tipo.LOMBRICES and self.especie_id is not None:
            raise ValidationError({"especie": "Lombricultura no usa una especie de pez."})
        if self.pk:
            anterior = type(self).objects.filter(pk=self.pk).values("especie_id").first()
            if anterior and anterior["especie_id"] != self.especie_id:
                raise ValidationError(
                    {"especie": "La especie de una piscina es permanente y no puede cambiarse."}
                )

    def __str__(self):
        return f"{self.codigo} · {self.nombre}"


class JornadaRegistro(models.Model):
    class Estado(models.TextChoices):
        BORRADOR = "BORRADOR", "Borrador"
        COMPLETA = "COMPLETA", "Completa"
        ANULADA = "ANULADA", "Anulada"

    class Fuente(models.TextChoices):
        WEB = "WEB", "Web"
        ANDROID = "ANDROID", "Android"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    piscina = models.ForeignKey(
        Piscina,
        on_delete=models.PROTECT,
        related_name="registros",
    )
    autor = models.ForeignKey(
        Acuicultor,
        on_delete=models.PROTECT,
        related_name="jornadas_creadas",
    )
    capturada_en = models.DateTimeField(default=timezone.now)
    recibida_en = models.DateTimeField(auto_now_add=True)
    poblacion_estimada = models.PositiveIntegerField()
    observaciones = models.TextField(blank=True)
    fuente = models.CharField(max_length=12, choices=Fuente.choices, default=Fuente.WEB)
    dispositivo_id = models.CharField(max_length=120, blank=True)
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.BORRADOR)
    version = models.PositiveIntegerField(default=1)
    creada_en = models.DateTimeField(auto_now_add=True)
    modificada_en = models.DateTimeField(auto_now=True)
    anulada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="jornadas_anuladas",
        null=True,
        blank=True,
    )
    anulada_en = models.DateTimeField(null=True, blank=True)
    motivo_anulacion = models.TextField(blank=True)

    class Meta:
        ordering = ["-capturada_en", "-creada_en"]
        verbose_name = "jornada de registro"
        verbose_name_plural = "jornadas de registro"
        indexes = [
            models.Index(fields=["piscina", "-capturada_en"], name="ix_jornada_piscina_fecha"),
            models.Index(fields=["autor", "-capturada_en"], name="ix_jornada_autor_fecha"),
            models.Index(fields=["estado"], name="ix_jornada_estado"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(version__gte=1),
                name="ck_jornada_version_positiva",
            )
        ]

    def __str__(self):
        return f"{self.piscina.codigo} · {self.capturada_en:%d/%m/%Y %H:%M}"

    @property
    def fecha(self):
        return self.capturada_en

    @property
    def acuicultor(self):
        return self.autor

    @property
    def esta_anulada(self):
        return self.estado == self.Estado.ANULADA

    def puede_modificar(self, usuario):
        return usuario.is_superuser or self.autor.user_id == usuario.id

    @property
    def ph(self):
        try:
            return self.agua.ph
        except MedicionAgua.DoesNotExist:
            return None

    @property
    def nitrato(self):
        try:
            return self.agua.nitrato
        except MedicionAgua.DoesNotExist:
            return None

    @property
    def nitrito(self):
        try:
            return self.agua.nitrito
        except MedicionAgua.DoesNotExist:
            return None

    @property
    def amoniaco_total(self):
        try:
            return self.agua.amoniaco_total
        except MedicionAgua.DoesNotExist:
            return None

    @property
    def muestras_peces(self):
        try:
            return self.muestra_biometrica.peces
        except MuestraBiometrica.DoesNotExist:
            return ObservacionPez.objects.none()


class MedicionAgua(models.Model):
    jornada = models.OneToOneField(
        JornadaRegistro,
        on_delete=models.CASCADE,
        related_name="agua",
    )
    ph = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(14), validar_ph_kit],
        verbose_name="pH",
        help_text="Valor final de una de las dos escalas de pH del kit; se guarda un solo pH.",
    )
    nitrato = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(0), validar_nitrato_kit],
        help_text="Nitrato (NO₃⁻), en ppm.",
    )
    nitrito = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(0), validar_nitrito_kit],
        help_text="Nitrito (NO₂⁻), en ppm.",
    )
    amoniaco_total = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(0), validar_amoniaco_total_kit],
        verbose_name="amoníaco total",
        help_text="Amoníaco total (NH₃/NH₄⁺), en ppm.",
    )

    class Meta:
        verbose_name = "medición de agua"
        verbose_name_plural = "mediciones de agua"

    def __str__(self):
        return f"Agua · {self.jornada}"


class MuestraBiometrica(models.Model):
    jornada = models.OneToOneField(
        JornadaRegistro,
        on_delete=models.CASCADE,
        related_name="muestra_biometrica",
    )
    metodo = models.CharField(max_length=160, blank=True)

    class Meta:
        verbose_name = "muestra biométrica"
        verbose_name_plural = "muestras biométricas"

    def __str__(self):
        return f"Biometría · {self.jornada}"

    @property
    def tamano(self):
        return self.peces.count()


class ObservacionPez(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    muestra = models.ForeignKey(
        MuestraBiometrica,
        on_delete=models.CASCADE,
        related_name="peces",
    )
    orden = models.PositiveIntegerField()
    peso_gramos = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
    )
    talla_centimetros = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
        help_text="Longitud total del pez.",
    )

    class Meta:
        ordering = ["orden"]
        verbose_name = "observación de pez"
        verbose_name_plural = "observaciones de peces"
        constraints = [
            models.UniqueConstraint(
                fields=["muestra", "orden"],
                name="uq_observacion_orden_muestra",
            )
        ]

    def __str__(self):
        return f"Pez {self.orden} · {self.peso_gramos} g"


class MovimientoPoblacion(models.Model):
    class Tipo(models.TextChoices):
        SIEMBRA = "SIEMBRA", "Siembra"
        MORTALIDAD = "MORTALIDAD", "Mortalidad"
        COSECHA_VENTA = "COSECHA_VENTA", "Cosecha o venta"
        TRASLADO = "TRASLADO", "Traslado"
        ESCAPE = "ESCAPE", "Escape"
        AJUSTE = "AJUSTE", "Ajuste"

    class Estado(models.TextChoices):
        ACTIVO = "ACTIVO", "Activo"
        ANULADO = "ANULADO", "Anulado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    cantidad = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    piscina_origen = models.ForeignKey(
        Piscina,
        on_delete=models.PROTECT,
        related_name="movimientos_salida",
        null=True,
        blank=True,
    )
    piscina_destino = models.ForeignKey(
        Piscina,
        on_delete=models.PROTECT,
        related_name="movimientos_entrada",
        null=True,
        blank=True,
    )
    autor = models.ForeignKey(
        Acuicultor,
        on_delete=models.PROTECT,
        related_name="movimientos_creados",
    )
    ocurrido_en = models.DateTimeField(default=timezone.now)
    observaciones = models.TextField(blank=True)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.ACTIVO)
    version = models.PositiveIntegerField(default=1)
    creado_en = models.DateTimeField(auto_now_add=True)
    modificado_en = models.DateTimeField(auto_now=True)
    anulado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="movimientos_anulados",
        null=True,
        blank=True,
    )
    anulado_en = models.DateTimeField(null=True, blank=True)
    motivo_anulacion = models.TextField(blank=True)

    class Meta:
        ordering = ["-ocurrido_en", "-creado_en"]
        verbose_name = "movimiento de población"
        verbose_name_plural = "movimientos de población"
        constraints = [
            models.CheckConstraint(
                condition=Q(piscina_origen__isnull=False) | Q(piscina_destino__isnull=False),
                name="ck_movimiento_con_piscina",
            ),
            models.CheckConstraint(
                condition=Q(version__gte=1),
                name="ck_movimiento_version_positiva",
            ),
        ]

    def clean(self):
        super().clean()
        origen = self.piscina_origen_id is not None
        destino = self.piscina_destino_id is not None

        if origen and destino and self.piscina_origen_id == self.piscina_destino_id:
            raise ValidationError("La piscina de origen y destino deben ser distintas.")
        if self.tipo == self.Tipo.SIEMBRA and (origen or not destino):
            raise ValidationError("La siembra requiere solo piscina de destino.")
        if self.tipo in {self.Tipo.MORTALIDAD, self.Tipo.COSECHA_VENTA, self.Tipo.ESCAPE}:
            if not origen or destino:
                raise ValidationError("Este movimiento requiere solo piscina de origen.")
        if self.tipo == self.Tipo.TRASLADO:
            if not origen or not destino:
                raise ValidationError("El traslado requiere origen y destino.")
            if self.piscina_origen.especie_id != self.piscina_destino.especie_id:
                raise ValidationError("Un traslado requiere piscinas de la misma especie.")
        if self.tipo == self.Tipo.AJUSTE and origen == destino:
            raise ValidationError("El ajuste requiere exactamente una piscina afectada.")

    def puede_modificar(self, usuario):
        return usuario.is_superuser or self.autor.user_id == usuario.id

    def __str__(self):
        return f"{self.get_tipo_display()} · {self.cantidad}"


class AuditoriaCambio(models.Model):
    class Entidad(models.TextChoices):
        JORNADA = "JORNADA", "Jornada"
        MOVIMIENTO = "MOVIMIENTO", "Movimiento"

    class Accion(models.TextChoices):
        CREAR = "CREAR", "Crear"
        CORREGIR = "CORREGIR", "Corregir"
        ANULAR = "ANULAR", "Anular"

    entidad = models.CharField(max_length=20, choices=Entidad.choices)
    entidad_uuid = models.UUIDField()
    accion = models.CharField(max_length=12, choices=Accion.choices)
    version_anterior = models.PositiveIntegerField(null=True, blank=True)
    version_nueva = models.PositiveIntegerField()
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="acciones_auditoria",
    )
    fecha = models.DateTimeField(auto_now_add=True)
    motivo = models.TextField(blank=True)
    datos_anteriores = models.JSONField(null=True, blank=True)
    datos_nuevos = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["-fecha", "-id"]
        verbose_name = "evento de auditoría"
        verbose_name_plural = "eventos de auditoría"
        indexes = [
            models.Index(fields=["entidad", "entidad_uuid", "-fecha"], name="ix_auditoria_entidad")
        ]

    def __str__(self):
        return f"{self.entidad} · {self.accion} · v{self.version_nueva}"
