from dataclasses import dataclass

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404

from .models import Acuicultor, Comunidad
from .services import perfil_de


SESSION_COMUNIDAD_WEB = "monitoreo_comunidad_web"
ALCANCE_TODAS = "todas"


@dataclass(frozen=True)
class AlcanceWeb:
    perfil: Acuicultor
    comunidad: Comunidad | None
    es_global: bool
    puede_escribir: bool


def resolver_alcance_web(request, *, actualizar_desde_query=False):
    """Resuelve el tenant visible sin aceptar un alcance global de usuarios ordinarios."""
    if not actualizar_desde_query and hasattr(request, "alcance_web"):
        return request.alcance_web

    perfil = perfil_de(request.user)
    if not request.user.is_superuser:
        alcance = AlcanceWeb(
            perfil=perfil,
            comunidad=perfil.comunidad,
            es_global=False,
            puede_escribir=True,
        )
        request.alcance_web = alcance
        return alcance

    if actualizar_desde_query and "comunidad" in request.GET:
        seleccion = request.GET.get("comunidad", "").strip().lower()
        if seleccion == ALCANCE_TODAS:
            request.session[SESSION_COMUNIDAD_WEB] = ALCANCE_TODAS
        else:
            try:
                comunidad = Comunidad.objects.get(id_publico=seleccion, activa=True)
            except (Comunidad.DoesNotExist, ValidationError, ValueError) as error:
                raise Http404("La comunidad seleccionada no existe o está inactiva.") from error
            request.session[SESSION_COMUNIDAD_WEB] = str(comunidad.id_publico)

    seleccion = request.session.get(SESSION_COMUNIDAD_WEB, ALCANCE_TODAS)
    if seleccion == ALCANCE_TODAS:
        alcance = AlcanceWeb(
            perfil=perfil,
            comunidad=None,
            es_global=True,
            puede_escribir=False,
        )
    else:
        try:
            comunidad = Comunidad.objects.get(id_publico=seleccion, activa=True)
        except (Comunidad.DoesNotExist, ValidationError, ValueError):
            request.session[SESSION_COMUNIDAD_WEB] = ALCANCE_TODAS
            alcance = AlcanceWeb(
                perfil=perfil,
                comunidad=None,
                es_global=True,
                puede_escribir=False,
            )
        else:
            alcance = AlcanceWeb(
                perfil=perfil,
                comunidad=comunidad,
                es_global=False,
                # Un perfil operativo no firma datos pertenecientes a otro tenant.
                puede_escribir=comunidad.pk == perfil.comunidad_id,
            )

    request.alcance_web = alcance
    return alcance


def filtrar_por_alcance(queryset, alcance, *, lookup="comunidad"):
    if alcance.es_global:
        return queryset.filter(**{f"{lookup}__activa": True})
    return queryset.filter(**{lookup: alcance.comunidad})


def exigir_alcance_escritura(request):
    alcance = resolver_alcance_web(request)
    if not alcance.puede_escribir:
        raise PermissionDenied(
            "La vista global y las comunidades ajenas son de solo lectura. "
            "Usa una cuenta operativa asignada a la comunidad para registrar datos."
        )
    return alcance
