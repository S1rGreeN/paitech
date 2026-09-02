from django.contrib import admin
from django.contrib.auth import get_user_model

from .models import (
    Acuicultor,
    AuditoriaCambio,
    CamaLombrices,
    CicloLombricultura,
    CicloProductivo,
    Comunidad,
    DispositivoSensor,
    Especie,
    JornadaRegistro,
    LecturaSensor,
    MedicionAgua,
    MovimientoPoblacion,
    MuestraBiometrica,
    ObservacionPez,
    PerfilSemaforoEspecie,
    Piscina,
    RegistroLombricultura,
)


def comunidad_usuario(request):
    if request.user.is_superuser:
        return None
    try:
        return request.user.perfil_acuicultor.comunidad
    except Acuicultor.DoesNotExist:
        return None


class TenantAdminMixin:
    """Filtra todo queryset del admin funcional por su única comunidad."""

    tenant_lookup = "comunidad"

    def get_queryset(self, request):
        consulta = super().get_queryset(request)
        comunidad = comunidad_usuario(request)
        if request.user.is_superuser:
            return consulta
        if comunidad is None:
            return consulta.none()
        return consulta.filter(**{self.tenant_lookup: comunidad})

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        comunidad = comunidad_usuario(request)
        if comunidad is not None:
            if db_field.name == "comunidad":
                kwargs["queryset"] = Comunidad.objects.filter(pk=comunidad.pk)
            elif db_field.name in {"piscina", "piscina_origen", "piscina_destino", "piscina_destino_cierre"}:
                kwargs["queryset"] = Piscina.objects.filter(comunidad=comunidad)
            elif db_field.name == "cama":
                kwargs["queryset"] = CamaLombrices.objects.filter(comunidad=comunidad)
            elif db_field.name in {"autor", "autor_apertura", "autor_cierre"}:
                kwargs["queryset"] = Acuicultor.objects.filter(comunidad=comunidad)
            elif db_field.name in {"ciclo", "ciclo_origen", "ciclo_destino"}:
                modelo = db_field.remote_field.model
                if modelo is CicloProductivo:
                    kwargs["queryset"] = CicloProductivo.objects.filter(
                        piscina__comunidad=comunidad
                    )
                elif modelo is CicloLombricultura:
                    kwargs["queryset"] = CicloLombricultura.objects.filter(
                        cama__comunidad=comunidad
                    )
            elif db_field.name == "jornada":
                kwargs["queryset"] = JornadaRegistro.objects.filter(
                    piscina__comunidad=comunidad
                )
            elif db_field.name == "muestra":
                kwargs["queryset"] = MuestraBiometrica.objects.filter(
                    jornada__piscina__comunidad=comunidad
                )
            elif db_field.name == "dispositivo":
                kwargs["queryset"] = DispositivoSensor.objects.filter(
                    piscina__comunidad=comunidad
                )
            elif db_field.name == "anulada_por":
                kwargs["queryset"] = get_user_model().objects.filter(
                    perfil_acuicultor__comunidad=comunidad
                )
            elif db_field.name == "especie":
                kwargs["queryset"] = Especie.objects.filter(
                    piscinas__comunidad=comunidad
                ).distinct()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Comunidad)
class ComunidadAdmin(TenantAdminMixin, admin.ModelAdmin):
    tenant_lookup = "pk"
    list_display = ("codigo", "nombre", "id_publico", "activa")
    search_fields = ("codigo", "nombre", "id_publico")
    readonly_fields = ("id_publico",)

    def get_queryset(self, request):
        consulta = admin.ModelAdmin.get_queryset(self, request)
        comunidad = comunidad_usuario(request)
        return consulta if request.user.is_superuser else consulta.filter(pk=getattr(comunidad, "pk", None))

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(Especie)
class EspecieAdmin(admin.ModelAdmin):
    list_display = ("nombre_comun", "nombre_cientifico", "activa")
    search_fields = ("nombre_comun", "nombre_cientifico")

    def get_queryset(self, request):
        consulta = super().get_queryset(request)
        comunidad = comunidad_usuario(request)
        if request.user.is_superuser:
            return consulta
        return consulta.filter(piscinas__comunidad=comunidad).distinct() if comunidad else consulta.none()

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(PerfilSemaforoEspecie)
class PerfilSemaforoEspecieAdmin(admin.ModelAdmin):
    list_display = ("especie", "version", "provisional", "actualizado_en")
    readonly_fields = ("actualizado_en",)

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(Acuicultor)
class AcuicultorAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ("nickname", "correo", "comunidad", "rol", "activo")
    list_filter = ("rol", "activo")
    search_fields = ("nickname", "user__email")

    def get_readonly_fields(self, request, obj=None):
        return () if request.user.is_superuser else ("user", "comunidad", "rol")

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(Piscina)
class PiscinaAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ("codigo", "nombre", "comunidad", "especie", "activa")
    list_filter = ("activa",)
    search_fields = ("codigo", "nombre")

    def get_readonly_fields(self, request, obj=None):
        return ("tipo", "especie") if obj and not request.user.is_superuser else ("tipo",)

    def save_model(self, request, obj, form, change):
        comunidad = comunidad_usuario(request)
        if comunidad is not None:
            obj.comunidad = comunidad
        super().save_model(request, obj, form, change)

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(CamaLombrices)
class CamaLombricesAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ("codigo", "nombre", "comunidad", "activa")
    list_filter = ("activa",)
    search_fields = ("codigo", "nombre")

    def save_model(self, request, obj, form, change):
        comunidad = comunidad_usuario(request)
        if comunidad is not None:
            obj.comunidad = comunidad
        super().save_model(request, obj, form, change)

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


class MedicionAguaInline(admin.StackedInline):
    model = MedicionAgua
    extra = 0
    max_num = 1


@admin.register(JornadaRegistro)
class JornadaRegistroAdmin(TenantAdminMixin, admin.ModelAdmin):
    tenant_lookup = "piscina__comunidad"
    list_display = ("id", "piscina", "ciclo", "capturada_en", "poblacion_estimada", "autor", "estado", "version", "fuente")
    list_filter = ("estado", "fuente", "piscina")
    search_fields = ("piscina__nombre", "piscina__codigo", "autor__nickname", "autor__user__email")
    date_hierarchy = "capturada_en"
    readonly_fields = ("version", "recibida_en", "creada_en", "modificada_en", "anulada_en")
    inlines = [MedicionAguaInline]


@admin.register(MuestraBiometrica)
class MuestraBiometricaAdmin(TenantAdminMixin, admin.ModelAdmin):
    tenant_lookup = "jornada__piscina__comunidad"
    list_display = ("jornada", "tamano", "metodo")


@admin.register(ObservacionPez)
class ObservacionPezAdmin(TenantAdminMixin, admin.ModelAdmin):
    tenant_lookup = "muestra__jornada__piscina__comunidad"
    list_display = ("muestra", "orden", "peso_gramos", "talla_centimetros")
    search_fields = ("muestra__jornada__piscina__codigo",)


@admin.register(MovimientoPoblacion)
class MovimientoPoblacionAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ("tipo", "cantidad", "piscina_origen", "piscina_destino", "ocurrido_en", "autor", "estado", "version")
    list_filter = ("tipo", "estado")
    readonly_fields = ("version", "creado_en", "modificado_en", "anulado_en")

    def get_queryset(self, request):
        from django.db.models import Q

        consulta = super().get_queryset(request)
        comunidad = comunidad_usuario(request)
        if request.user.is_superuser:
            return consulta
        return consulta.filter(
            Q(piscina_origen__comunidad=comunidad) | Q(piscina_destino__comunidad=comunidad)
        ) if comunidad else consulta.none()


@admin.register(CicloProductivo)
class CicloProductivoAdmin(TenantAdminMixin, admin.ModelAdmin):
    tenant_lookup = "piscina__comunidad"
    list_display = ("piscina", "numero", "estado", "iniciado_en", "poblacion_inicial", "cerrado_en", "poblacion_final", "version")
    list_filter = ("estado", "piscina", "destino_cierre", "fuente")
    search_fields = ("piscina__codigo", "piscina__nombre")
    readonly_fields = (
        "especie", "numero", "version", "creado_en", "modificado_en",
        "prediccion_poblacion_final", "prediccion_min", "prediccion_max",
        "prediccion_tasa", "prediccion_ciclos_usados", "prediccion_confianza",
        "prediccion_metodo_version", "prediccion_calculada_en",
        "prediccion_datos_hasta", "prediccion_origen",
    )


@admin.register(CicloLombricultura)
class CicloLombriculturaAdmin(TenantAdminMixin, admin.ModelAdmin):
    tenant_lookup = "cama__comunidad"
    list_display = ("cama", "numero", "estado", "iniciado_en", "conteo_inicial", "cerrado_en", "conteo_final", "version")
    list_filter = ("estado", "cama", "fuente")
    readonly_fields = ("numero", "version", "creado_en", "modificado_en")


@admin.register(RegistroLombricultura)
class RegistroLombriculturaAdmin(TenantAdminMixin, admin.ModelAdmin):
    tenant_lookup = "cama__comunidad"
    list_display = ("cama", "ciclo", "capturada_en", "ph_suelo", "conteo_lombrices", "autor", "estado", "version")
    list_filter = ("estado", "fuente", "cama")
    search_fields = ("cama__codigo", "cama__nombre", "autor__user__email")
    readonly_fields = ("version", "recibida_en", "creada_en", "modificada_en", "anulada_en")


@admin.register(DispositivoSensor)
class DispositivoSensorAdmin(TenantAdminMixin, admin.ModelAdmin):
    tenant_lookup = "piscina__comunidad"
    list_display = ("codigo", "nombre", "piscina", "activo", "instalado_en", "ultimo_uso_en")
    list_filter = ("activo", "piscina")
    search_fields = ("codigo", "nombre", "piscina__codigo")
    readonly_fields = ("selector", "secreto_hash", "ultimo_uso_en", "creado_en")


@admin.register(LecturaSensor)
class LecturaSensorAdmin(TenantAdminMixin, admin.ModelAdmin):
    tenant_lookup = "piscina__comunidad"
    list_display = ("dispositivo", "piscina", "ciclo", "medida_en", "calidad")
    list_filter = ("calidad", "piscina", "dispositivo")
    date_hierarchy = "medida_en"
    readonly_fields = tuple(campo.name for campo in LecturaSensor._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AuditoriaCambio)
class AuditoriaCambioAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ("entidad", "entidad_uuid", "accion", "version_nueva", "actor", "comunidad", "fecha")
    list_filter = ("entidad", "accion")
    search_fields = ("entidad_uuid", "actor__email")
    readonly_fields = tuple(campo.name for campo in AuditoriaCambio._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
