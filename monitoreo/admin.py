from django.contrib import admin

from .models import Acuicultor, MuestraPez, Piscina, Registro


@admin.register(Acuicultor)
class AcuicultorAdmin(admin.ModelAdmin):
    list_display = ("nickname", "correo_usuario", "fecha_nacimiento", "fecha_creacion")
    search_fields = ("nickname", "user__username", "user__email")

    @admin.display(description="Correo")
    def correo_usuario(self, obj):
        return obj.user.email


@admin.register(Piscina)
class PiscinaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "tipo", "activa", "fecha_creacion")
    list_filter = ("tipo", "activa")
    search_fields = ("codigo", "nombre")
    filter_horizontal = ("acuicultores",)


class MuestraPezInline(admin.TabularInline):
    model = MuestraPez
    extra = 1


@admin.register(Registro)
class RegistroAdmin(admin.ModelAdmin):
    list_display = ("id", "piscina", "fecha", "ph", "poblacion_estimada", "acuicultor")
    list_filter = ("piscina", "fecha")
    search_fields = ("piscina__nombre", "acuicultor__nickname")
    date_hierarchy = "fecha"
    inlines = [MuestraPezInline]


@admin.register(MuestraPez)
class MuestraPezAdmin(admin.ModelAdmin):
    list_display = ("registro", "especie", "peso_gramos", "talla_centimetros")
    search_fields = ("especie", "registro__piscina__nombre")
