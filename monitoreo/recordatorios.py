import calendar
from datetime import date, datetime, time, timedelta

from django.utils import timezone

from .models import CicloProductivo, JornadaRegistro, MedicionAgua, MuestraBiometrica


SIN_CICLO = "SIN_CICLO"
AL_DIA = "AL_DIA"
PENDIENTE = "PENDIENTE"
TOLERANCIA = "TOLERANCIA"
ATRASADO = "ATRASADO"


def _localizar(valor):
    return timezone.localtime(valor) if timezone.is_aware(valor) else valor


def _inicio_dia(fecha):
    zona = timezone.get_current_timezone()
    return timezone.make_aware(datetime.combine(fecha, time.min), zona)


def _fin_dia(fecha):
    return _inicio_dia(fecha + timedelta(days=1)) - timedelta(microseconds=1)


def _sumar_meses(valor, meses=1):
    indice = valor.month - 1 + meses
    anio = valor.year + indice // 12
    mes = indice % 12 + 1
    dia = min(valor.day, calendar.monthrange(anio, mes)[1])
    return valor.replace(year=anio, month=mes, day=dia)


def _estado_plazo(ahora, vence, tolerancia_hasta):
    if ahora <= vence:
        return PENDIENTE
    if ahora <= tolerancia_hasta:
        return TOLERANCIA
    return ATRASADO


def _resultado(tipo, estado, *, vence=None, periodo_inicio=None, periodo_fin=None):
    return {
        "tipo": tipo,
        "estado": estado,
        "vence_en": vence.isoformat() if vence else None,
        "periodo_inicio": periodo_inicio.isoformat() if periodo_inicio else None,
        "periodo_fin": periodo_fin.isoformat() if periodo_fin else None,
    }


def _fechas_agua(ciclo):
    return [
        _localizar(fecha)
        for fecha in MedicionAgua.objects.filter(
            jornada__ciclo=ciclo,
            jornada__estado=JornadaRegistro.Estado.COMPLETA,
        ).values_list("jornada__capturada_en", flat=True)
    ]


def _fechas_biometria(ciclo):
    return [
        _localizar(fecha)
        for fecha in MuestraBiometrica.objects.filter(
            jornada__ciclo=ciclo,
            jornada__estado=JornadaRegistro.Estado.COMPLETA,
        ).values_list("jornada__capturada_en", flat=True)
    ]


def estado_agua(ciclo, *, ahora=None):
    ahora = _localizar(ahora or timezone.now())
    inicio = _localizar(ciclo.iniciado_en)
    fechas = sorted(fecha for fecha in _fechas_agua(ciclo) if fecha >= inicio)
    primer_vencimiento = inicio + timedelta(days=7)
    if not fechas:
        return _resultado(
            "AGUA",
            _estado_plazo(ahora, primer_vencimiento, primer_vencimiento + timedelta(days=2)),
            vence=primer_vencimiento,
            periodo_inicio=inicio,
            periodo_fin=primer_vencimiento,
        )

    primera = fechas[0]
    inicio_semana = _inicio_dia(primera.date() + timedelta(days=7 - primera.weekday()))
    while inicio_semana <= ahora:
        fin_semana = _fin_dia(inicio_semana.date() + timedelta(days=6))
        satisfecha = any(inicio_semana <= fecha <= fin_semana for fecha in fechas)
        if not satisfecha:
            tolerancia = _fin_dia(fin_semana.date() + timedelta(days=2))
            return _resultado(
                "AGUA",
                _estado_plazo(ahora, fin_semana, tolerancia),
                vence=fin_semana,
                periodo_inicio=inicio_semana,
                periodo_fin=fin_semana,
            )
        inicio_semana += timedelta(days=7)
    return _resultado("AGUA", AL_DIA)


def estado_biometria(ciclo, *, ahora=None):
    ahora = _localizar(ahora or timezone.now())
    inicio = _localizar(ciclo.iniciado_en)
    fechas = sorted(fecha for fecha in _fechas_biometria(ciclo) if fecha >= inicio)
    primer_vencimiento = _sumar_meses(inicio)
    if not fechas:
        return _resultado(
            "BIOMETRIA",
            _estado_plazo(ahora, primer_vencimiento, primer_vencimiento + timedelta(days=2)),
            vence=primer_vencimiento,
            periodo_inicio=inicio,
            periodo_fin=primer_vencimiento,
        )

    primera = fechas[0]
    if primera.month == 12:
        mes_inicio = date(primera.year + 1, 1, 1)
    else:
        mes_inicio = date(primera.year, primera.month + 1, 1)
    while _inicio_dia(mes_inicio) <= ahora:
        ultimo_dia = calendar.monthrange(mes_inicio.year, mes_inicio.month)[1]
        inicio_periodo = _inicio_dia(mes_inicio)
        fin_periodo = _fin_dia(date(mes_inicio.year, mes_inicio.month, ultimo_dia))
        satisfecha = any(inicio_periodo <= fecha <= fin_periodo for fecha in fechas)
        if not satisfecha:
            tolerancia = _fin_dia(fin_periodo.date() + timedelta(days=2))
            return _resultado(
                "BIOMETRIA",
                _estado_plazo(ahora, fin_periodo, tolerancia),
                vence=fin_periodo,
                periodo_inicio=inicio_periodo,
                periodo_fin=fin_periodo,
            )
        if mes_inicio.month == 12:
            mes_inicio = date(mes_inicio.year + 1, 1, 1)
        else:
            mes_inicio = date(mes_inicio.year, mes_inicio.month + 1, 1)
    return _resultado("BIOMETRIA", AL_DIA)


def recordatorios_piscina(piscina, *, ahora=None):
    ciclo = (
        CicloProductivo.objects.filter(
            piscina=piscina, estado=CicloProductivo.Estado.ACTIVO
        )
        .select_related("piscina")
        .first()
    )
    if ciclo is None:
        vacio = _resultado("AGUA", SIN_CICLO)
        biometria = _resultado("BIOMETRIA", SIN_CICLO)
        return {"ciclo": None, "agua": vacio, "biometria": biometria}
    return {
        "ciclo": ciclo,
        "agua": estado_agua(ciclo, ahora=ahora),
        "biometria": estado_biometria(ciclo, ahora=ahora),
    }
