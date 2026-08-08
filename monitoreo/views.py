from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.messages import get_messages
from django.db.models import Avg, Count, Q
from django.http import HttpRequest, HttpResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from .forms import JornadaForm, LoginForm, ObservacionPezFormSet
from .models import JornadaRegistro, MedicionAgua, Piscina
from .services import crear_jornada, perfil_de


def render_page(request: HttpRequest, template_name: str, context: dict | None = None) -> HttpResponse:
    context = context or {}
    context.update({"request": request, "user": request.user, "messages": list(get_messages(request)), "csrf_token": get_token(request)})
    return render(request, template_name, context)


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        return redirect("monitoreo:dashboard")
    form = LoginForm(request=request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        siguiente = request.GET.get("next")
        if siguiente and url_has_allowed_host_and_scheme(siguiente, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
            return redirect(siguiente)
        return redirect("monitoreo:dashboard")
    return render_page(request, "monitoreo/login.jinja", {"form": form})


@require_POST
def logout_view(request):
    logout(request)
    messages.success(request, "Tu sesión se cerró correctamente.")
    return redirect("monitoreo:login")


@login_required
@require_http_methods(["GET"])
def dashboard(request):
    perfil = perfil_de(request.user)
    piscinas = list(
        Piscina.objects.filter(comunidad=perfil.comunidad, activa=True)
        .select_related("especie")
        .annotate(total_registros=Count("registros", filter=Q(registros__estado=JornadaRegistro.Estado.COMPLETA)))
        .order_by("tipo", "nombre")
    )
    tarjetas = []
    for piscina in piscinas:
        ultimo = piscina.registros.filter(estado=JornadaRegistro.Estado.COMPLETA).select_related("autor", "autor__user", "agua").first()
        tarjetas.append({"piscina": piscina, "ultimo_registro": ultimo})
    registros = JornadaRegistro.objects.filter(piscina__comunidad=perfil.comunidad, estado=JornadaRegistro.Estado.COMPLETA).select_related("piscina", "autor", "autor__user", "agua")
    contexto = {
        "tarjetas": tarjetas,
        "total_piscinas": len(piscinas),
        "total_registros": registros.count(),
        "promedio_ph": MedicionAgua.objects.filter(jornada__in=registros).aggregate(valor=Avg("ph"))["valor"],
        "ultimos_registros": registros[:5],
    }
    return render_page(request, "monitoreo/dashboard.jinja", contexto)


@login_required
@require_http_methods(["GET"])
def piscina_detalle(request, piscina_id):
    perfil = perfil_de(request.user)
    piscina = get_object_or_404(Piscina, pk=piscina_id, comunidad=perfil.comunidad, activa=True)
    registros = piscina.registros.filter(estado=JornadaRegistro.Estado.COMPLETA).select_related("autor", "autor__user", "agua").prefetch_related("muestra_biometrica__peces")[:30]
    promedio_ph = MedicionAgua.objects.filter(jornada__piscina=piscina, jornada__estado=JornadaRegistro.Estado.COMPLETA).aggregate(valor=Avg("ph"))["valor"]
    return render_page(request, "monitoreo/piscina_detalle.jinja", {"piscina": piscina, "registros": registros, "promedio_ph": promedio_ph})


@login_required
@require_http_methods(["GET", "POST"])
def registro_nuevo(request, piscina_id):
    perfil = perfil_de(request.user)
    piscina = get_object_or_404(Piscina, pk=piscina_id, comunidad=perfil.comunidad, activa=True)
    if piscina.tipo != Piscina.Tipo.PECES:
        messages.info(request, "Lombricultura está planificada como Próximamente.")
        return redirect("monitoreo:piscina_detalle", piscina_id=piscina.id)

    form = JornadaForm(request.POST or None)
    formset = ObservacionPezFormSet(request.POST or None, prefix="muestras")
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        datos = form.cleaned_data
        jornada, _ = crear_jornada(
            actor=request.user,
            piscina=piscina,
            capturada_en=datos["capturada_en"],
            poblacion_estimada=datos["poblacion_estimada"],
            observaciones=datos["observaciones"],
            fuente=JornadaRegistro.Fuente.WEB,
            agua=form.datos_agua(),
            peces=formset.peces_limpios() if datos["registrar_biometria"] else [],
        )
        messages.success(request, "Jornada guardada correctamente.")
        return redirect("monitoreo:registro_detalle", registro_id=jornada.id)
    return render_page(request, "monitoreo/registro_form.jinja", {"piscina": piscina, "form": form, "formset": formset})


@login_required
@require_http_methods(["GET"])
def registro_detalle(request, registro_id):
    perfil = perfil_de(request.user)
    registro = get_object_or_404(
        JornadaRegistro.objects.filter(piscina__comunidad=perfil.comunidad).select_related("piscina", "piscina__especie", "autor", "autor__user", "agua").prefetch_related("muestra_biometrica__peces"),
        pk=registro_id,
    )
    resumen = registro.muestras_peces.aggregate(peso_promedio=Avg("peso_gramos"), talla_promedio=Avg("talla_centimetros"))
    return render_page(request, "monitoreo/registro_detalle.jinja", {"registro": registro, "resumen_muestras": resumen})
