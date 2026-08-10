from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    ordering = ("email",)
    list_display = ("email", "first_name", "last_name", "is_staff", "is_active")
    search_fields = ("email", "first_name", "last_name")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Datos personales", {"fields": ("first_name", "last_name")}),
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
        ("Datos personales", {"fields": ("first_name", "last_name")}),
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
        # Un administrador funcional solo administra cuentas ordinarias.
        return consulta.filter(is_staff=False, is_superuser=False)

    def get_fieldsets(self, request, obj=None):
        if request.user.is_superuser:
            return super().get_fieldsets(request, obj)
        return self.add_fieldsets_funcionales if obj is None else self.fieldsets_funcionales

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser:
            # Defensa adicional aunque esos campos no estén en el formulario.
            obj.is_staff = False
            obj.is_superuser = False
        super().save_model(request, obj, form, change)

    def has_change_permission(self, request, obj=None):
        if obj is not None and not request.user.is_superuser and (obj.is_staff or obj.is_superuser):
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if not request.user.is_superuser:
            return False
        return super().has_delete_permission(request, obj)
