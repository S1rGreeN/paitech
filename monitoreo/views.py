from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.messages import get_messages
from django.db import transaction
from django.db.models import Avg, Count
from django.http import HttpRequest, HttpResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from .forms import LoginForm, MuestraPezFormSet, RegistroForm
from .models import Acuicultor, MuestraPez, Piscina, Registro


def render_page(request: HttpRequest, template_name: str, context: dict | None = None) -> HttpResponse:
    context = context or {}
    context.update(
        {
            "request": request,
            "user": request.user,
            "messages": list(get_messages(request)),
            "csrf_token": get_token(request),
        }
    )
    return render(request, template_name, context)


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        return redirect("monitoreo:dashboard")

    form = LoginForm(request=request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        siguiente = request.GET.get("next")
        if siguiente and url_has_allowed_host_and_scheme(
            siguiente,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
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
    piscinas = list(
        Piscina.objects.filter(activa=True)
        .annotate(total_registros=Count("registros"))
        .order_by("tipo", "nombre")
    )

    tarjetas = []
    for piscina in piscinas:
        tarjetas.append(
            {
                "piscina": piscina,
                "ultimo_registro": piscina.registros.select_related("acuicultor").first(),
            }
        )

    registros = Registro.objects.select_related("piscina", "acuicultor")
    contexto = {
        "tarjetas": tarjetas,
        "total_piscinas": len(piscinas),
        "total_registros": registros.count(),
        "promedio_ph": registros.aggregate(valor=Avg("ph"))["valor"],
        "ultimos_registros": registros[:5],
    }
    return render_page(request, "monitoreo/dashboard.jinja", contexto)


@login_required
@require_http_methods(["GET"])
def piscina_detalle(request, piscina_id):
    piscina = get_object_or_404(Piscina, pk=piscina_id, activa=True)
    registros = piscina.registros.select_related("acuicultor").prefetch_related("muestras_peces")[:30]
    contexto = {
        "piscina": piscina,
        "registros": registros,
        "promedio_ph": piscina.registros.aggregate(valor=Avg("ph"))["valor"],
    }
    return render_page(request, "monitoreo/piscina_detalle.jinja", contexto)


@login_required
@require_http_methods(["GET", "POST"])
def registro_nuevo(request, piscina_id):
    piscina = get_object_or_404(Piscina, pk=piscina_id, activa=True)
    if piscina.tipo != Piscina.Tipo.PECES:
        messages.info(request, "El registro de la piscina de lombrices se habilitará en el siguiente sprint.")
        return redirect("monitoreo:piscina_detalle", piscina_id=piscina.id)

    form = RegistroForm(request.POST or None)
    formset = MuestraPezFormSet(request.POST or None, prefix="muestras")

    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            perfil, _ = Acuicultor.objects.get_or_create(
                user=request.user,
                defaults={"nickname": request.user.username},
            )
            registro = form.save(commit=False)
            registro.piscina = piscina
            registro.acuicultor = perfil
            registro.save()

            for formulario_muestra in formset:
                if not formulario_muestra.cleaned_data:
                    continue
                muestra = MuestraPez(
                    registro=registro,
                    especie=formulario_muestra.cleaned_data["especie"],
                    peso_gramos=formulario_muestra.cleaned_data["peso_gramos"],
                    talla_centimetros=formulario_muestra.cleaned_data["talla_centimetros"],
                )
                muestra.full_clean()
                muestra.save()

        messages.success(request, "Registro y muestras guardados correctamente.")
        return redirect("monitoreo:registro_detalle", registro_id=registro.id)

    return render_page(
        request,
        "monitoreo/registro_form.jinja",
        {"piscina": piscina, "form": form, "formset": formset},
    )


@login_required
@require_http_methods(["GET"])
def registro_detalle(request, registro_id):
    registro = get_object_or_404(
        Registro.objects.select_related("piscina", "acuicultor").prefetch_related("muestras_peces"),
        pk=registro_id,
    )
    resumen_muestras = registro.muestras_peces.aggregate(
        peso_promedio=Avg("peso_gramos"),
        talla_promedio=Avg("talla_centimetros"),
    )
    return render_page(
        request,
        "monitoreo/registro_detalle.jinja",
        {"registro": registro, "resumen_muestras": resumen_muestras},
    )
