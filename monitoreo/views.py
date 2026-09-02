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

from cuentas.security import (
    estado_bloqueo,
    normalizar_email,
    obtener_ip,
    registrar_login_exitoso,
    registrar_login_fallido,
)

from .forms import (
    CambioClaveInicialForm,
    CicloLombriculturaAperturaForm,
    CicloLombriculturaCierreForm,
    CicloAperturaForm,
    CicloCierreForm,
    JornadaForm,
    LoginForm,
    ObservacionPezFormSet,
    RegistroLombriculturaForm,
)
from .models import (
    CamaLombrices,
    CicloLombricultura,
    CicloProductivo,
    Comunidad,
    JornadaRegistro,
    MedicionAgua,
    Piscina,
    RegistroLombricultura,
)
from .prediccion import calcular_prediccion
from .recordatorios import recordatorios_piscina
from .services import (
    ConflictoVersion,
    cerrar_ciclo,
    cerrar_ciclo_lombricultura,
    crear_ciclo,
    crear_ciclo_lombricultura,
    crear_jornada,
    crear_registro_lombricultura,
)
from .web_scope import (
    ALCANCE_TODAS,
    SESSION_COMUNIDAD_WEB,
    exigir_alcance_escritura,
    filtrar_por_alcance,
    resolver_alcance_web,
)


def render_page(
    request: HttpRequest,
    template_name: str,
    context: dict | None = None,
    *,
    status: int = 200,
) -> HttpResponse:
    context = context or {}
    context.update({"request": request, "user": request.user, "messages": list(get_messages(request)), "csrf_token": get_token(request)})
    if request.user.is_authenticated:
        alcance = resolver_alcance_web(request)
        context.update(
            {
                "alcance_web": alcance,
                "comunidades_web": (
                    Comunidad.objects.filter(activa=True).order_by("nombre")
                    if request.user.is_superuser
                    else ()
                ),
            }
        )
    return render(request, template_name, context, status=status)


def error_400(request, exception=None):
    return render_page(
        request,
        "monitoreo/error_400.jinja",
        {"request_id": getattr(request, "request_id", "no-disponible")},
        status=400,
    )


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        return redirect("monitoreo:dashboard")
    email = normalizar_email(request.POST.get("username", ""))
    ip = obtener_ip(request)
    form = LoginForm(request=request, data=request.POST or None)
    if request.method == "POST" and estado_bloqueo(email, ip):
        form.add_error(None, "No fue posible iniciar sesión. Intenta nuevamente más tarde.")
        return render_page(request, "monitoreo/login.jinja", {"form": form}, status=429)
    if request.method == "POST" and form.is_valid():
        usuario = form.get_user()
        registrar_login_exitoso(usuario, ip, canal="web")
        login(request, usuario)
        if usuario.is_superuser:
            request.session[SESSION_COMUNIDAD_WEB] = ALCANCE_TODAS
        else:
            request.session.pop(SESSION_COMUNIDAD_WEB, None)
        if usuario.debe_cambiar_clave:
            return redirect("monitoreo:cambiar_clave_inicial")
        siguiente = request.GET.get("next")
        if siguiente and url_has_allowed_host_and_scheme(siguiente, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
            return redirect(siguiente)
        return redirect("monitoreo:dashboard")
    if request.method == "POST":
        registrar_login_fallido(email, ip)
    return render_page(request, "monitoreo/login.jinja", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def cambiar_clave_inicial(request):
    form = CambioClaveInicialForm(user=request.user, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        usuario = form.save(commit=False)
        usuario.debe_cambiar_clave = False
        usuario._cambio_clave_confirmado = True
        usuario.save(update_fields=["password", "debe_cambiar_clave"])
        logout(request)
        messages.success(request, "Contraseña actualizada. Inicia sesión nuevamente.")
        return redirect("monitoreo:login")
    return render_page(
        request,
        "monitoreo/cambiar_clave_inicial.jinja",
        {"form": form},
    )


@require_POST
def logout_view(request):
    logout(request)
    messages.success(request, "Tu sesión se cerró correctamente.")
    return redirect("monitoreo:login")


@login_required
@require_http_methods(["GET"])
def dashboard(request):
    alcance = resolver_alcance_web(request, actualizar_desde_query=True)
    piscinas_base = filtrar_por_alcance(
        Piscina.objects.all(), alcance, lookup="comunidad"
    )
    piscinas = list(
        piscinas_base.filter(
            activa=True,
            tipo=Piscina.Tipo.PECES,
        )
        .select_related("especie", "comunidad")
        .annotate(total_registros=Count("registros", filter=Q(registros__estado=JornadaRegistro.Estado.COMPLETA)))
        .order_by("comunidad__nombre", "tipo", "nombre")
    )
    tarjetas = []
    for piscina in piscinas:
        ultimo = piscina.registros.filter(estado=JornadaRegistro.Estado.COMPLETA).select_related("autor", "autor__user", "agua").first()
        ciclo = piscina.ciclos.filter(estado=CicloProductivo.Estado.ACTIVO).first()
        tarjetas.append({
            "piscina": piscina,
            "ultimo_registro": ultimo,
            "ciclo_activo": ciclo,
            "recordatorios": recordatorios_piscina(piscina),
        })
    registros = filtrar_por_alcance(
        JornadaRegistro.objects.all(), alcance, lookup="piscina__comunidad"
    ).filter(estado=JornadaRegistro.Estado.COMPLETA).select_related(
        "piscina", "piscina__comunidad", "autor", "autor__user", "agua"
    )
    camas_base = filtrar_por_alcance(
        CamaLombrices.objects.all(), alcance, lookup="comunidad"
    )
    camas = list(
        camas_base.filter(activa=True)
        .select_related("comunidad")
        .annotate(
            total_registros=Count(
                "registros",
                filter=Q(registros__estado=RegistroLombricultura.Estado.COMPLETO),
            )
        )
        .order_by("comunidad__nombre", "nombre")
    )
    tarjetas_camas = [
        {
            "cama": cama,
            "ciclo_activo": cama.ciclos.filter(
                estado=CicloLombricultura.Estado.ACTIVO
            ).first(),
            "ultimo_registro": cama.registros.filter(
                estado=RegistroLombricultura.Estado.COMPLETO
            ).first(),
        }
        for cama in camas
    ]
    contexto = {
        "tarjetas": tarjetas,
        "tarjetas_camas": tarjetas_camas,
        "total_piscinas": len(piscinas),
        "total_camas": len(camas),
        "total_registros": registros.count(),
        "promedio_ph": MedicionAgua.objects.filter(jornada__in=registros).aggregate(valor=Avg("ph"))["valor"],
        "ultimos_registros": registros[:5],
    }
    return render_page(request, "monitoreo/dashboard.jinja", contexto)


@login_required
@require_http_methods(["GET"])
def piscina_detalle(request, piscina_id):
    alcance = resolver_alcance_web(request)
    piscinas = filtrar_por_alcance(
        Piscina.objects.select_related("comunidad", "especie"),
        alcance,
        lookup="comunidad",
    )
    piscina = get_object_or_404(piscinas, pk=piscina_id, activa=True)
    registros = piscina.registros.filter(estado=JornadaRegistro.Estado.COMPLETA).select_related("autor", "autor__user", "agua").prefetch_related("muestra_biometrica__peces")[:30]
    promedio_ph = MedicionAgua.objects.filter(jornada__piscina=piscina, jornada__estado=JornadaRegistro.Estado.COMPLETA).aggregate(valor=Avg("ph"))["valor"]
    ciclo_activo = piscina.ciclos.filter(estado=CicloProductivo.Estado.ACTIVO).select_related("autor_apertura", "autor_apertura__user").first()
    ciclos = piscina.ciclos.select_related("autor_apertura", "autor_cierre")[:20]
    return render_page(request, "monitoreo/piscina_detalle.jinja", {
        "piscina": piscina,
        "registros": registros,
        "promedio_ph": promedio_ph,
        "ciclo_activo": ciclo_activo,
        "ciclos": ciclos,
        "recordatorios": recordatorios_piscina(piscina),
    })


@login_required
@require_http_methods(["GET", "POST"])
def registro_nuevo(request, piscina_id):
    alcance = exigir_alcance_escritura(request)
    piscina = get_object_or_404(
        Piscina, pk=piscina_id, comunidad=alcance.comunidad, activa=True
    )
    if piscina.tipo != Piscina.Tipo.PECES:
        messages.info(request, "Lombricultura está planificada como Próximamente.")
        return redirect("monitoreo:piscina_detalle", piscina_id=piscina.id)
    ciclo = piscina.ciclos.filter(estado=CicloProductivo.Estado.ACTIVO).first()
    if ciclo is None:
        messages.info(request, "Primero debes iniciar un ciclo productivo para esta piscina.")
        return redirect("monitoreo:ciclo_abrir", piscina_id=piscina.id)

    form = JornadaForm(request.POST or None)
    formset = ObservacionPezFormSet(request.POST or None, prefix="muestras")
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        datos = form.cleaned_data
        jornada, _ = crear_jornada(
            actor=request.user,
            piscina=piscina,
            ciclo=ciclo,
            capturada_en=datos["capturada_en"],
            poblacion_estimada=datos["poblacion_estimada"],
            observaciones=datos["observaciones"],
            fuente=JornadaRegistro.Fuente.WEB,
            agua=form.datos_agua(),
            peces=formset.peces_limpios() if datos["registrar_biometria"] else [],
        )
        messages.success(request, "Jornada guardada correctamente.")
        return redirect("monitoreo:registro_detalle", registro_id=jornada.id)
    return render_page(request, "monitoreo/registro_form.jinja", {"piscina": piscina, "ciclo": ciclo, "form": form, "formset": formset})


@login_required
@require_http_methods(["GET", "POST"])
def ciclo_abrir(request, piscina_id):
    alcance = exigir_alcance_escritura(request)
    piscina = get_object_or_404(
        Piscina,
        pk=piscina_id,
        comunidad=alcance.comunidad,
        activa=True,
        tipo=Piscina.Tipo.PECES,
    )
    activo = piscina.ciclos.filter(estado=CicloProductivo.Estado.ACTIVO).first()
    if activo:
        messages.info(request, f"La piscina ya tiene activo el ciclo {activo.numero}.")
        return redirect("monitoreo:piscina_detalle", piscina_id=piscina.id)
    form = CicloAperturaForm(request.POST or None)
    prediccion = None
    if request.method == "POST" and form.is_valid():
        prediccion = calcular_prediccion(piscina, form.cleaned_data["poblacion_inicial"])
        if "confirmar" in request.POST:
            try:
                ciclo, _ = crear_ciclo(
                    actor=request.user,
                    piscina=piscina,
                    fuente=CicloProductivo.Fuente.WEB,
                    **form.cleaned_data,
                )
            except ConflictoVersion as error:
                form.add_error(None, str(error))
            else:
                messages.success(request, f"Ciclo {ciclo.numero} iniciado correctamente.")
                return redirect("monitoreo:piscina_detalle", piscina_id=piscina.id)
    return render_page(
        request,
        "monitoreo/ciclo_abrir.jinja",
        {"piscina": piscina, "form": form, "prediccion": prediccion},
    )


@login_required
@require_http_methods(["GET", "POST"])
def ciclo_cerrar(request, ciclo_id):
    alcance = exigir_alcance_escritura(request)
    ciclo = get_object_or_404(
        CicloProductivo.objects.select_related("piscina", "especie"),
        pk=ciclo_id,
        piscina__comunidad=alcance.comunidad,
        estado=CicloProductivo.Estado.ACTIVO,
    )
    form = CicloCierreForm(request.POST or None, ciclo=ciclo)
    if request.method == "POST" and form.is_valid():
        try:
            ciclo, _ = cerrar_ciclo(
                ciclo=ciclo,
                actor=request.user,
                version_esperada=ciclo.version,
                **form.cleaned_data,
            )
        except ConflictoVersion as error:
            form.add_error(None, str(error))
        else:
            messages.success(request, f"Ciclo {ciclo.numero} cerrado correctamente.")
            return redirect("monitoreo:piscina_detalle", piscina_id=ciclo.piscina_id)
    return render_page(
        request,
        "monitoreo/ciclo_cerrar.jinja",
        {"ciclo": ciclo, "piscina": ciclo.piscina, "form": form},
    )


@login_required
@require_http_methods(["GET"])
def registro_detalle(request, registro_id):
    alcance = resolver_alcance_web(request)
    registros = filtrar_por_alcance(
        JornadaRegistro.objects.all(), alcance, lookup="piscina__comunidad"
    )
    registro = get_object_or_404(
        registros.select_related("piscina", "piscina__comunidad", "piscina__especie", "autor", "autor__user", "agua").prefetch_related("muestra_biometrica__peces"),
        pk=registro_id,
    )
    resumen = registro.muestras_peces.aggregate(peso_promedio=Avg("peso_gramos"), talla_promedio=Avg("talla_centimetros"))
    return render_page(request, "monitoreo/registro_detalle.jinja", {"registro": registro, "resumen_muestras": resumen})


@login_required
@require_http_methods(["GET"])
def cama_detalle(request, cama_id):
    alcance = resolver_alcance_web(request)
    camas = filtrar_por_alcance(
        CamaLombrices.objects.select_related("comunidad"),
        alcance,
        lookup="comunidad",
    )
    cama = get_object_or_404(
        camas, pk=cama_id, activa=True
    )
    registros = (
        cama.registros.filter(estado=RegistroLombricultura.Estado.COMPLETO)
        .select_related("autor", "autor__user", "ciclo")[:30]
    )
    ciclo_activo = cama.ciclos.filter(
        estado=CicloLombricultura.Estado.ACTIVO
    ).select_related("autor_apertura", "autor_apertura__user").first()
    ciclos = cama.ciclos.select_related("autor_apertura", "autor_cierre")[:20]
    promedio_ph = registros.aggregate(valor=Avg("ph_suelo"))["valor"]
    return render_page(
        request,
        "monitoreo/cama_detalle.jinja",
        {
            "cama": cama,
            "registros": registros,
            "ciclo_activo": ciclo_activo,
            "ciclos": ciclos,
            "promedio_ph": promedio_ph,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def ciclo_lombricultura_abrir(request, cama_id):
    alcance = exigir_alcance_escritura(request)
    cama = get_object_or_404(
        CamaLombrices, pk=cama_id, comunidad=alcance.comunidad, activa=True
    )
    activo = cama.ciclos.filter(estado=CicloLombricultura.Estado.ACTIVO).first()
    if activo:
        messages.info(request, f"La cama ya tiene activo el ciclo {activo.numero}.")
        return redirect("monitoreo:cama_detalle", cama_id=cama.id)
    form = CicloLombriculturaAperturaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            ciclo, _ = crear_ciclo_lombricultura(
                actor=request.user,
                cama=cama,
                fuente=CicloLombricultura.Fuente.WEB,
                **form.cleaned_data,
            )
        except ConflictoVersion as error:
            form.add_error(None, str(error))
        else:
            messages.success(request, f"Ciclo {ciclo.numero} iniciado correctamente.")
            return redirect("monitoreo:cama_detalle", cama_id=cama.id)
    return render_page(
        request,
        "monitoreo/ciclo_lombricultura_abrir.jinja",
        {"cama": cama, "form": form},
    )


@login_required
@require_http_methods(["GET", "POST"])
def ciclo_lombricultura_cerrar(request, ciclo_id):
    alcance = exigir_alcance_escritura(request)
    ciclo = get_object_or_404(
        CicloLombricultura.objects.select_related("cama"),
        pk=ciclo_id,
        cama__comunidad=alcance.comunidad,
        estado=CicloLombricultura.Estado.ACTIVO,
    )
    form = CicloLombriculturaCierreForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            ciclo, _ = cerrar_ciclo_lombricultura(
                ciclo=ciclo,
                actor=request.user,
                version_esperada=ciclo.version,
                **form.cleaned_data,
            )
        except ConflictoVersion as error:
            form.add_error(None, str(error))
        else:
            messages.success(request, f"Ciclo {ciclo.numero} cerrado correctamente.")
            return redirect("monitoreo:cama_detalle", cama_id=ciclo.cama_id)
    return render_page(
        request,
        "monitoreo/ciclo_lombricultura_cerrar.jinja",
        {"cama": ciclo.cama, "ciclo": ciclo, "form": form},
    )


@login_required
@require_http_methods(["GET", "POST"])
def registro_lombricultura_nuevo(request, cama_id):
    alcance = exigir_alcance_escritura(request)
    cama = get_object_or_404(
        CamaLombrices, pk=cama_id, comunidad=alcance.comunidad, activa=True
    )
    ciclo = cama.ciclos.filter(estado=CicloLombricultura.Estado.ACTIVO).first()
    if ciclo is None:
        messages.info(request, "Primero debes iniciar un ciclo de lombricultura.")
        return redirect("monitoreo:ciclo_lombricultura_abrir", cama_id=cama.id)
    form = RegistroLombriculturaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        registro, _ = crear_registro_lombricultura(
            actor=request.user,
            cama=cama,
            ciclo=ciclo,
            fuente=RegistroLombricultura.Fuente.WEB,
            **form.cleaned_data,
        )
        messages.success(request, "Registro de lombricultura guardado correctamente.")
        return redirect(
            "monitoreo:registro_lombricultura_detalle", registro_id=registro.id
        )
    return render_page(
        request,
        "monitoreo/registro_lombricultura_form.jinja",
        {"cama": cama, "ciclo": ciclo, "form": form},
    )


@login_required
@require_http_methods(["GET"])
def registro_lombricultura_detalle(request, registro_id):
    alcance = resolver_alcance_web(request)
    registros = filtrar_por_alcance(
        RegistroLombricultura.objects.all(), alcance, lookup="cama__comunidad"
    )
    registro = get_object_or_404(
        registros.select_related("cama", "cama__comunidad", "ciclo", "autor", "autor__user"),
        pk=registro_id,
    )
    return render_page(
        request,
        "monitoreo/registro_lombricultura_detalle.jinja",
        {"registro": registro},
    )
