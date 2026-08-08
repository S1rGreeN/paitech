from django.contrib import admin

from .models import (
    Acuicultor,
    AuditoriaCambio,
    Comunidad,
    Especie,
    JornadaRegistro,
    MedicionAgua,
    MovimientoPoblacion,
    MuestraBiometrica,
    ObservacionPez,
    Piscina,
)


@admin.register(Comunidad)
class ComunidadAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "activa")
    search_fields = ("codigo", "nombre")


@admin.register(Especie)
class EspecieAdmin(admin.ModelAdmin):
    list_display = ("nombre_comun", "nombre_cientifico", "activa")
    search_fields = ("nombre_comun", "nombre_cientifico")


@admin.register(Acuicultor)
class AcuicultorAdmin(admin.ModelAdmin):
    list_display = ("nickname", "correo", "comunidad", "rol", "activo")
    list_filter = ("comunidad", "rol", "activo")
    search_fields = ("nickname", "user__email")


@admin.register(Piscina)
class PiscinaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "comunidad", "tipo", "especie", "activa")
    list_filter = ("comunidad", "tipo", "activa")
    search_fields = ("codigo", "nombre")


class MedicionAguaInline(admin.StackedInline):
    model = MedicionAgua
    extra = 0
    max_num = 1


@admin.register(JornadaRegistro)
class JornadaRegistroAdmin(admin.ModelAdmin):
    list_display = ("id", "piscina", "capturada_en", "poblacion_estimada", "autor", "estado", "version", "fuente")
    list_filter = ("estado", "fuente", "piscina")
    search_fields = ("piscina__nombre", "piscina__codigo", "autor__nickname", "autor__user__email")
    date_hierarchy = "capturada_en"
    readonly_fields = ("version", "recibida_en", "creada_en", "modificada_en", "anulada_en")
    inlines = [MedicionAguaInline]


@admin.register(MuestraBiometrica)
class MuestraBiometricaAdmin(admin.ModelAdmin):
    list_display = ("jornada", "tamano", "metodo")


@admin.register(ObservacionPez)
class ObservacionPezAdmin(admin.ModelAdmin):
    list_display = ("muestra", "orden", "peso_gramos", "talla_centimetros")
    search_fields = ("muestra__jornada__piscina__codigo",)


@admin.register(MovimientoPoblacion)
class MovimientoPoblacionAdmin(admin.ModelAdmin):
    list_display = ("tipo", "cantidad", "piscina_origen", "piscina_destino", "ocurrido_en", "autor", "estado", "version")
    list_filter = ("tipo", "estado")
    readonly_fields = ("version", "creado_en", "modificado_en", "anulado_en")


@admin.register(AuditoriaCambio)
class AuditoriaCambioAdmin(admin.ModelAdmin):
    list_display = ("entidad", "entidad_uuid", "accion", "version_nueva", "actor", "fecha")
    list_filter = ("entidad", "accion")
    search_fields = ("entidad_uuid", "actor__email")
    readonly_fields = tuple(campo.name for campo in AuditoriaCambio._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
