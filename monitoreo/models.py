import uuid
import hashlib
import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

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


class CicloProductivo(models.Model):
    class Estado(models.TextChoices):
        ACTIVO = "ACTIVO", "Activo"
        CERRADO = "CERRADO", "Cerrado"
        ANULADO = "ANULADO", "Anulado"

    class DestinoCierre(models.TextChoices):
        VENTA = "VENTA", "Venta"
        CONSUMO = "CONSUMO", "Consumo"
        TRASLADO = "TRASLADO", "Traslado"
        MORTALIDAD_TOTAL = "MORTALIDAD_TOTAL", "Mortalidad total"
        OTRO = "OTRO", "Otro"

    class Fuente(models.TextChoices):
        WEB = "WEB", "Web"
        ANDROID = "ANDROID", "Android"

    class ConfianzaPrediccion(models.TextChoices):
        SIN_DATOS = "SIN_DATOS", "Sin datos"
        MUY_BAJA = "MUY_BAJA", "Muy baja"
        BAJA = "BAJA", "Baja"
        MEDIA = "MEDIA", "Media"

    class OrigenPrediccion(models.TextChoices):
        SERVIDOR = "SERVIDOR", "Servidor"
        CACHE_ANDROID = "CACHE_ANDROID", "Caché Android"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    piscina = models.ForeignKey(
        Piscina, on_delete=models.PROTECT, related_name="ciclos"
    )
    especie = models.ForeignKey(
        Especie,
        on_delete=models.PROTECT,
        related_name="ciclos_productivos",
        help_text="Instantánea histórica de la especie permanente de la piscina.",
    )
    numero = models.PositiveIntegerField()
    estado = models.CharField(
        max_length=10, choices=Estado.choices, default=Estado.ACTIVO
    )
    iniciado_en = models.DateTimeField()
    poblacion_inicial = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    duracion_estimada_meses = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(60)],
    )
    observaciones_apertura = models.TextField(blank=True)
    autor_apertura = models.ForeignKey(
        Acuicultor,
        on_delete=models.PROTECT,
        related_name="ciclos_abiertos",
    )
    fuente = models.CharField(max_length=12, choices=Fuente.choices, default=Fuente.WEB)
    dispositivo_id = models.CharField(max_length=120, blank=True)

    cerrado_en = models.DateTimeField(null=True, blank=True)
    destino_cierre = models.CharField(
        max_length=20, choices=DestinoCierre.choices, blank=True
    )
    poblacion_final = models.PositiveIntegerField(null=True, blank=True)
    peso_total_cosechado_kg = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    observaciones_cierre = models.TextField(blank=True)
    piscina_destino_cierre = models.ForeignKey(
        Piscina,
        on_delete=models.PROTECT,
        related_name="ciclos_recibidos_al_cierre",
        null=True,
        blank=True,
    )
    autor_cierre = models.ForeignKey(
        Acuicultor,
        on_delete=models.PROTECT,
        related_name="ciclos_cerrados",
        null=True,
        blank=True,
    )

    prediccion_poblacion_final = models.PositiveIntegerField(null=True, blank=True)
    prediccion_min = models.PositiveIntegerField(null=True, blank=True)
    prediccion_max = models.PositiveIntegerField(null=True, blank=True)
    prediccion_tasa = models.DecimalField(
        max_digits=8, decimal_places=6, null=True, blank=True
    )
    prediccion_ciclos_usados = models.PositiveSmallIntegerField(default=0)
    prediccion_confianza = models.CharField(
        max_length=12,
        choices=ConfianzaPrediccion.choices,
        default=ConfianzaPrediccion.SIN_DATOS,
    )
    prediccion_metodo_version = models.CharField(max_length=80, blank=True)
    prediccion_calculada_en = models.DateTimeField(null=True, blank=True)
    prediccion_datos_hasta = models.DateTimeField(null=True, blank=True)
    prediccion_origen = models.CharField(
        max_length=16,
        choices=OrigenPrediccion.choices,
        default=OrigenPrediccion.SERVIDOR,
    )

    version = models.PositiveIntegerField(default=1)
    creado_en = models.DateTimeField(auto_now_add=True)
    modificado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-iniciado_en", "-numero"]
        verbose_name = "ciclo productivo"
        verbose_name_plural = "ciclos productivos"
        constraints = [
            models.UniqueConstraint(
                fields=["piscina", "numero"], name="uq_ciclo_numero_piscina"
            ),
            models.UniqueConstraint(
                fields=["piscina"],
                condition=Q(estado="ACTIVO"),
                name="uq_ciclo_activo_piscina",
            ),
            models.CheckConstraint(
                condition=Q(version__gte=1), name="ck_ciclo_version_positiva"
            ),
            models.CheckConstraint(
                condition=(
                    Q(estado="ACTIVO", cerrado_en__isnull=True, autor_cierre__isnull=True,
                      poblacion_final__isnull=True, destino_cierre="")
                    | Q(estado="ANULADO")
                    | Q(estado="CERRADO", cerrado_en__isnull=False,
                        autor_cierre__isnull=False, poblacion_final__isnull=False)
                ),
                name="ck_ciclo_campos_cierre_estado",
            ),
        ]
        indexes = [
            models.Index(fields=["piscina", "estado"], name="ix_ciclo_piscina_estado"),
            models.Index(fields=["piscina", "-iniciado_en"], name="ix_ciclo_piscina_inicio"),
        ]

    def clean(self):
        super().clean()
        if self.piscina_id and self.especie_id != self.piscina.especie_id:
            raise ValidationError({"especie": "El ciclo debe conservar la especie de la piscina."})
        if self.estado == self.Estado.CERRADO:
            faltantes = []
            for campo in ("cerrado_en", "destino_cierre", "poblacion_final", "autor_cierre"):
                if getattr(self, campo) in (None, ""):
                    faltantes.append(campo)
            if faltantes:
                raise ValidationError({campo: "Este campo es obligatorio al cerrar." for campo in faltantes})
            if self.cerrado_en and self.cerrado_en < self.iniciado_en:
                raise ValidationError({"cerrado_en": "El cierre no puede ser anterior a la apertura."})
            if (
                self.destino_cierre == self.DestinoCierre.MORTALIDAD_TOTAL
                and self.poblacion_final != 0
            ):
                raise ValidationError(
                    {"poblacion_final": "La mortalidad total requiere población final cero."}
                )
        if (
            self.piscina_destino_cierre_id
            and self.piscina_destino_cierre_id == self.piscina_id
        ):
            raise ValidationError(
                {"piscina_destino_cierre": "La piscina destino debe ser diferente."}
            )
        if self.piscina_destino_cierre_id:
            if self.destino_cierre != self.DestinoCierre.TRASLADO:
                raise ValidationError(
                    {"piscina_destino_cierre": "Solo se indica para un cierre por traslado."}
                )
            if self.piscina_destino_cierre.especie_id != self.especie_id:
                raise ValidationError(
                    {"piscina_destino_cierre": "El traslado requiere la misma especie."}
                )

    def __str__(self):
        return f"{self.piscina.codigo} · ciclo {self.numero}"


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
    ciclo = models.ForeignKey(
        CicloProductivo,
        on_delete=models.PROTECT,
        related_name="jornadas",
        null=True,
        blank=True,
        help_text="Temporalmente nullable para migrar datos de desarrollo anteriores a 1.5.",
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
        validators=[MinValueValidator(0), MaxValueValidator(14)],
        verbose_name="pH",
        help_text="Valor numérico final; se guarda un solo pH aunque se usen ambas escalas del kit.",
    )
    nitrato = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(0)],
        help_text="Nitrato (NO₃⁻), en ppm.",
    )
    nitrito = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(0)],
        help_text="Nitrito (NO₂⁻), en ppm.",
    )
    amoniaco_total = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(0)],
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
    ciclo_origen = models.ForeignKey(
        CicloProductivo,
        on_delete=models.PROTECT,
        related_name="movimientos_salida",
        null=True,
        blank=True,
    )
    ciclo_destino = models.ForeignKey(
        CicloProductivo,
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

        if self.ciclo_origen_id and self.ciclo_origen.piscina_id != self.piscina_origen_id:
            raise ValidationError({"ciclo_origen": "El ciclo no pertenece a la piscina de origen."})
        if self.ciclo_destino_id and self.ciclo_destino.piscina_id != self.piscina_destino_id:
            raise ValidationError({"ciclo_destino": "El ciclo no pertenece a la piscina de destino."})
        if origen and self.tipo != self.Tipo.SIEMBRA and not self.ciclo_origen_id:
            raise ValidationError({"ciclo_origen": "El movimiento requiere ciclo de origen."})
        if destino and self.tipo != self.Tipo.SIEMBRA and not self.ciclo_destino_id:
            raise ValidationError({"ciclo_destino": "El movimiento requiere ciclo de destino."})

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
        CICLO = "CICLO", "Ciclo"

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


class DispositivoSensor(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    piscina = models.ForeignKey(
        Piscina, on_delete=models.PROTECT, related_name="dispositivos_sensor"
    )
    codigo = models.CharField(max_length=80, unique=True)
    nombre = models.CharField(max_length=160)
    selector = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    secreto_hash = models.CharField(max_length=64, blank=True, editable=False)
    activo = models.BooleanField(
        default=False,
        help_text="Debe permanecer desactivado hasta habilitar formalmente la telemetría.",
    )
    instalado_en = models.DateTimeField(null=True, blank=True)
    ultimo_uso_en = models.DateTimeField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["piscina", "codigo"]
        verbose_name = "dispositivo sensor"
        verbose_name_plural = "dispositivos sensores"

    @staticmethod
    def hash_secreto(secreto):
        return hashlib.sha256(secreto.encode("utf-8")).hexdigest()

    def emitir_credencial(self):
        secreto = secrets.token_urlsafe(24)
        self.secreto_hash = self.hash_secreto(secreto)
        self.save(update_fields=["secreto_hash"])
        return f"{self.selector}.{secreto}"

    def __str__(self):
        return f"{self.codigo} · {self.piscina.codigo}"


class LecturaSensor(models.Model):
    class Calidad(models.TextChoices):
        COMPLETA = "COMPLETA", "Completa"
        PARCIAL = "PARCIAL", "Parcial"
        INVALIDA = "INVALIDA", "Inválida"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dispositivo = models.ForeignKey(
        DispositivoSensor, on_delete=models.PROTECT, related_name="lecturas"
    )
    piscina = models.ForeignKey(
        Piscina, on_delete=models.PROTECT, related_name="lecturas_sensor"
    )
    ciclo = models.ForeignKey(
        CicloProductivo,
        on_delete=models.PROTECT,
        related_name="lecturas_sensor",
        null=True,
        blank=True,
    )
    medida_en = models.DateTimeField()
    recibida_en = models.DateTimeField(auto_now_add=True)
    oxigeno_disuelto_mg_l = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(50)],
    )
    temperatura_c = models.DecimalField(
        max_digits=7,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[MinValueValidator(-10), MaxValueValidator(60)],
    )
    turbidez_ntu = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100000)],
    )
    calidad = models.CharField(max_length=10, choices=Calidad.choices)
    detalle_calidad = models.CharField(max_length=500, blank=True)
    metadatos = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-medida_en", "-recibida_en"]
        verbose_name = "lectura de sensor"
        verbose_name_plural = "lecturas de sensores"
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(oxigeno_disuelto_mg_l__isnull=False)
                    | Q(temperatura_c__isnull=False)
                    | Q(turbidez_ntu__isnull=False)
                ),
                name="ck_lectura_al_menos_un_valor",
            )
        ]
        indexes = [
            models.Index(fields=["piscina", "-medida_en"], name="ix_lectura_piscina_fecha"),
            models.Index(fields=["dispositivo", "-medida_en"], name="ix_lectura_dispositivo_fecha"),
        ]

    def clean(self):
        super().clean()
        valores = (
            self.oxigeno_disuelto_mg_l,
            self.temperatura_c,
            self.turbidez_ntu,
        )
        presentes = sum(valor is not None for valor in valores)
        if presentes == 0:
            raise ValidationError("Una lectura requiere al menos un valor.")
        if self.dispositivo_id and self.piscina_id != self.dispositivo.piscina_id:
            raise ValidationError({"piscina": "La lectura no pertenece a la piscina del dispositivo."})
        if self.ciclo_id and self.ciclo.piscina_id != self.piscina_id:
            raise ValidationError({"ciclo": "El ciclo no pertenece a la piscina de la lectura."})
        if self.calidad != self.Calidad.INVALIDA:
            esperada = self.Calidad.COMPLETA if presentes == 3 else self.Calidad.PARCIAL
            if self.calidad != esperada:
                raise ValidationError({"calidad": f"La calidad calculada debe ser {esperada}."})

    def __str__(self):
        return f"{self.dispositivo.codigo} · {self.medida_en:%d/%m/%Y %H:%M}"
