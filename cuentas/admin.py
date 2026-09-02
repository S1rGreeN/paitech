from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from django.utils import timezone

from .models import ControlIntentoLogin, EventoSeguridad, TokenDispositivo, Usuario
from .security import registrar_evento


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    ordering = ("email",)
    readonly_fields = ("last_login", "date_joined", "debe_cambiar_clave")
    list_display = (
        "email",
        "first_name",
        "last_name",
        "is_staff",
        "is_active",
        "debe_cambiar_clave",
    )
    search_fields = ("email", "first_name", "last_name")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Datos personales", {"fields": ("first_name", "last_name", "debe_cambiar_clave")}),
        (
            "Permisos",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Fechas", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "password1",
                    "password2",
                    "first_name",
                    "last_name",
                    "is_staff",
                    "is_active",
                ),
            },
        ),
    )

    fieldsets_funcionales = (
        (None, {"fields": ("email", "password")}),
        ("Datos personales", {"fields": ("first_name", "last_name", "debe_cambiar_clave")}),
        ("Estado", {"fields": ("is_active",)}),
        ("Fechas", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets_funcionales = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "password1",
                    "password2",
                    "first_name",
                    "last_name",
                    "is_active",
                ),
            },
        ),
    )

    def get_queryset(self, request):
        consulta = super().get_queryset(request)
        if request.user.is_superuser:
            return consulta
        try:
            comunidad = request.user.perfil_acuicultor.comunidad
        except Exception:
            return consulta.none()
        # Un administrador funcional solo administra cuentas ordinarias de su
        # propia comunidad; el filtrado también provoca 404 en URL directas.
        return consulta.filter(
            is_staff=False,
            is_superuser=False,
            perfil_acuicultor__comunidad=comunidad,
        )

    def get_fieldsets(self, request, obj=None):
        if request.user.is_superuser:
            return super().get_fieldsets(request, obj)
        return self.add_fieldsets_funcionales if obj is None else self.fieldsets_funcionales

    def save_model(self, request, obj, form, change):
        if not change:
            obj.debe_cambiar_clave = True
        if not request.user.is_superuser:
            # Defensa adicional aunque esos campos no estén en el formulario.
            obj.is_staff = False
            obj.is_superuser = False
        super().save_model(request, obj, form, change)
        if not request.user.is_superuser:
            comunidad = request.user.perfil_acuicultor.comunidad
            perfil = obj.perfil_acuicultor
            perfil.comunidad = comunidad
            perfil.rol = perfil.Rol.ACUICULTOR
            base = obj.get_full_name().strip() or obj.email.split("@", 1)[0]
            candidato = base
            contador = 1
            while type(perfil).objects.filter(
                comunidad=comunidad, nickname=candidato
            ).exclude(pk=perfil.pk).exists():
                contador += 1
                candidato = f"{base}-{contador}"
            perfil.nickname = candidato
            perfil.save(update_fields=["comunidad", "rol", "nickname"])

    def user_change_password(self, request, object_id, form_url=""):
        respuesta = super().user_change_password(request, object_id, form_url)
        if request.method == "POST" and getattr(respuesta, "status_code", None) in {302, 303}:
            objetivo = self.get_queryset(request).filter(pk=object_id).first()
            if objetivo:
                registrar_evento(
                    EventoSeguridad.Tipo.CLAVE_RESTABLECIDA,
                    usuario=objetivo,
                    detalle={"administrado_por_usuario_id": request.user.pk},
                )
        return respuesta

    def has_change_permission(self, request, obj=None):
        if obj is not None and not request.user.is_superuser and (obj.is_staff or obj.is_superuser):
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if not request.user.is_superuser:
            return False
        return super().has_delete_permission(request, obj)


class SoloTecnicoAdmin(admin.ModelAdmin):
    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TokenDispositivo)
class TokenDispositivoAdmin(SoloTecnicoAdmin):
    list_display = (
        "usuario",
        "nombre_dispositivo",
        "dispositivo_id",
        "ultimo_uso_en",
        "expira_en",
        "revocado_en",
    )
    search_fields = ("usuario__email", "nombre_dispositivo", "dispositivo_id")
    readonly_fields = [campo.name for campo in TokenDispositivo._meta.fields]
    actions = ("revocar_seleccionadas",)

    @admin.action(description="Revocar las sesiones seleccionadas")
    def revocar_seleccionadas(self, request, queryset):
        cantidad = queryset.filter(revocado_en__isnull=True).update(revocado_en=timezone.now())
        self.message_user(request, f"Se revocaron {cantidad} sesiones de dispositivo.")


@admin.register(ControlIntentoLogin)
class ControlIntentoLoginAdmin(SoloTecnicoAdmin):
    list_display = (
        "email_normalizado",
        "direccion_ip",
        "fallos",
        "bloqueos_acumulados",
        "bloqueado_hasta",
        "ultimo_intento_en",
    )
    search_fields = ("email_normalizado", "direccion_ip")
    readonly_fields = [campo.name for campo in ControlIntentoLogin._meta.fields]
    actions = ("desbloquear_seleccionados",)

    @admin.action(description="Desbloquear los accesos seleccionados")
    def desbloquear_seleccionados(self, request, queryset):
        objetivos = list(queryset.values_list("email_normalizado", "direccion_ip"))
        cantidad = queryset.count()
        queryset.delete()
        for email, ip in objetivos:
            registrar_evento(
                EventoSeguridad.Tipo.CUENTA_DESBLOQUEADA,
                email=email,
                ip=ip,
                detalle={"administrado_por_usuario_id": request.user.pk},
            )
        self.message_user(request, f"Se desbloquearon {cantidad} controles de acceso.")


@admin.register(EventoSeguridad)
class EventoSeguridadAdmin(SoloTecnicoAdmin):
    list_display = ("tipo", "usuario", "email_normalizado", "direccion_ip", "creado_en")
    list_filter = ("tipo", "creado_en")
    search_fields = ("usuario__email", "email_normalizado", "direccion_ip")
    readonly_fields = [campo.name for campo in EventoSeguridad._meta.fields]

    def has_change_permission(self, request, obj=None):
        return False
