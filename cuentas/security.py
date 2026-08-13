import ipaddress
from datetime import timedelta

from django.conf import settings
from django.contrib.sessions.models import Session
from django.db import transaction
from django.utils import timezone

from .models import ControlIntentoLogin, EventoSeguridad, TokenDispositivo


VENTANA_FALLOS = timedelta(minutes=15)
PRIMER_BLOQUEO = timedelta(minutes=15)
BLOQUEO_REINCIDENTE = timedelta(hours=1)
RETENCION_EVENTOS = timedelta(days=30)
MAX_FALLOS = 5


def normalizar_email(valor):
    return (valor or "").strip().lower()[:254]


def obtener_ip(request):
    valor = request.META.get("REMOTE_ADDR", "")
    if getattr(settings, "TRUST_X_FORWARDED_FOR", False):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            valor = forwarded.split(",", 1)[0].strip()
    try:
        return str(ipaddress.ip_address(valor))
    except ValueError:
        return "desconocida"


def registrar_evento(tipo, *, usuario=None, email="", ip="", detalle=None):
    ahora = timezone.now()
    EventoSeguridad.objects.filter(creado_en__lt=ahora - RETENCION_EVENTOS).delete()
    return EventoSeguridad.objects.create(
        tipo=tipo,
        usuario=usuario,
        email_normalizado=normalizar_email(email or (usuario.email if usuario else "")),
        direccion_ip=ip,
        detalle=detalle or {},
    )


def estado_bloqueo(email, ip):
    control = ControlIntentoLogin.objects.filter(
        email_normalizado=normalizar_email(email), direccion_ip=ip
    ).first()
    ahora = timezone.now()
    if control and control.bloqueado_hasta and control.bloqueado_hasta > ahora:
        return control.bloqueado_hasta
    return None


@transaction.atomic
def registrar_login_fallido(email, ip):
    ahora = timezone.now()
    email = normalizar_email(email)
    control, _ = ControlIntentoLogin.objects.select_for_update().get_or_create(
        email_normalizado=email,
        direccion_ip=ip,
        defaults={"ventana_iniciada_en": ahora},
    )
    if control.bloqueado_hasta and control.bloqueado_hasta > ahora:
        registrar_evento(
            EventoSeguridad.Tipo.LOGIN_BLOQUEADO,
            email=email,
            ip=ip,
            detalle={"motivo": "bloqueo_vigente"},
        )
        return control.bloqueado_hasta

    if control.ventana_iniciada_en <= ahora - VENTANA_FALLOS:
        control.ventana_iniciada_en = ahora
        control.fallos = 0
    control.fallos += 1
    bloqueo = None
    if control.fallos >= MAX_FALLOS:
        duracion = PRIMER_BLOQUEO if control.bloqueos_acumulados == 0 else BLOQUEO_REINCIDENTE
        control.bloqueos_acumulados += 1
        control.fallos = 0
        control.ventana_iniciada_en = ahora
        control.bloqueado_hasta = ahora + duracion
        bloqueo = control.bloqueado_hasta
    control.save()
    registrar_evento(
        EventoSeguridad.Tipo.LOGIN_BLOQUEADO if bloqueo else EventoSeguridad.Tipo.LOGIN_FALLIDO,
        email=email,
        ip=ip,
        detalle={"bloqueo_aplicado": bool(bloqueo)},
    )
    return bloqueo


def registrar_login_exitoso(usuario, ip, *, canal, dispositivo_id=""):
    ControlIntentoLogin.objects.filter(
        email_normalizado=normalizar_email(usuario.email), direccion_ip=ip
    ).delete()
    registrar_evento(
        EventoSeguridad.Tipo.LOGIN_EXITOSO,
        usuario=usuario,
        ip=ip,
        detalle={"canal": canal, "dispositivo_id": dispositivo_id},
    )


def revocar_tokens_moviles(usuario, *, motivo):
    ahora = timezone.now()
    cantidad = TokenDispositivo.objects.filter(
        usuario=usuario, revocado_en__isnull=True
    ).update(revocado_en=ahora)
    if cantidad:
        registrar_evento(
            EventoSeguridad.Tipo.SESIONES_REVOCADAS,
            usuario=usuario,
            detalle={"motivo": motivo, "tokens_moviles": cantidad},
        )
    return cantidad


def revocar_sesiones_web(usuario):
    eliminadas = 0
    for sesion in Session.objects.filter(expire_date__gt=timezone.now()).iterator():
        try:
            usuario_id = sesion.get_decoded().get("_auth_user_id")
        except Exception:
            continue
        if str(usuario_id) == str(usuario.pk):
            sesion.delete()
            eliminadas += 1
    return eliminadas


def revocar_todas_las_sesiones(usuario, *, motivo):
    moviles = revocar_tokens_moviles(usuario, motivo=motivo)
    web = revocar_sesiones_web(usuario)
    return {"tokens_moviles": moviles, "sesiones_web": web}
