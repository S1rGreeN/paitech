from django.contrib.auth.models import Group, Permission


GRUPO_ADMINISTRADORES_FUNCIONALES = "Administradores funcionales"

# Lista positiva: cualquier permiso no enumerado queda fuera del rol funcional.
# En particular no se conceden borrados, gestión de grupos/permisos, cambios
# directos de jornadas ni acceso de superusuario.
PERMISOS_ADMINISTRADOR_FUNCIONAL = {
    "cuentas": {
        "add_usuario",
        "change_usuario",
        "view_usuario",
    },
    "monitoreo": {
        "view_comunidad",
        "add_especie",
        "change_especie",
        "view_especie",
        "add_piscina",
        "change_piscina",
        "view_piscina",
        "change_acuicultor",
        "view_acuicultor",
        "view_jornadaregistro",
        "view_medicionagua",
        "view_muestrabiometrica",
        "view_observacionpez",
        "view_movimientopoblacion",
        "view_auditoriacambio",
    },
}


def configurar_grupo_administradores_funcionales():
    """Crea o repara el grupo con una lista cerrada de permisos mínimos."""
    grupo, _ = Group.objects.get_or_create(name=GRUPO_ADMINISTRADORES_FUNCIONALES)
    permisos = Permission.objects.none()
    for app_label, codigos in PERMISOS_ADMINISTRADOR_FUNCIONAL.items():
        permisos = permisos | Permission.objects.filter(
            content_type__app_label=app_label,
            codename__in=codigos,
        )
    grupo.permissions.set(permisos.distinct())
    return grupo
