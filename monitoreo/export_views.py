from django.contrib.auth.decorators import login_required
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .exportaciones import ExportacionDemasiadoGrande, exportar_unidad
from .models import CamaLombrices, Piscina
from .views import render_page
from .web_scope import filtrar_por_alcance, resolver_alcance_web


def descargar(request, modelo, unidad_id):
    alcance = resolver_alcance_web(request)
    unidades = filtrar_por_alcance(modelo.objects.select_related("comunidad"), alcance)
    unidad = get_object_or_404(unidades, pk=unidad_id, activa=True)
    try:
        archivo = exportar_unidad(unidad, request.user)
    except ExportacionDemasiadoGrande:
        return render_page(request, "monitoreo/exportacion_limite.jinja", status=422)
    tipo = "piscina" if modelo is Piscina else "cama"
    codigo = slugify(unidad.codigo)[:60] or str(unidad.pk)[:8]
    fecha = timezone.localtime().strftime("%Y%m%d-%H%M%S")
    return FileResponse(
        archivo, as_attachment=True,
        filename=f"paipaytech-{tipo}-{codigo}-{fecha}.xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@login_required
@never_cache
@require_GET
def piscina_excel(request, piscina_id):
    return descargar(request, Piscina, piscina_id)


@login_required
@never_cache
@require_GET
def cama_excel(request, cama_id):
    return descargar(request, CamaLombrices, cama_id)
