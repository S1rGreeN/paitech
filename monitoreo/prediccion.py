from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Q
from django.utils import timezone

from .models import CicloProductivo, MovimientoPoblacion


METODO_VERSION = "mediana_supervivencia_v1"


def _mediana(valores):
    ordenados = sorted(valores)
    centro = len(ordenados) // 2
    if len(ordenados) % 2:
        return ordenados[centro]
    return (ordenados[centro - 1] + ordenados[centro]) / Decimal("2")


def _confianza(cantidad):
    if cantidad == 0:
        return CicloProductivo.ConfianzaPrediccion.SIN_DATOS
    if cantidad <= 2:
        return CicloProductivo.ConfianzaPrediccion.MUY_BAJA
    if cantidad <= 4:
        return CicloProductivo.ConfianzaPrediccion.BAJA
    return CicloProductivo.ConfianzaPrediccion.MEDIA


def _redondear_poblacion(valor):
    return int(valor.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def calcular_prediccion(piscina, poblacion_inicial, *, datos_hasta=None):
    """Calcula la línea base reproducible usando solo ciclos de la misma piscina."""
    datos_hasta = datos_hasta or timezone.now()
    ciclos = (
        CicloProductivo.objects.filter(
            piscina=piscina,
            estado=CicloProductivo.Estado.CERRADO,
            cerrado_en__lte=datos_hasta,
            poblacion_final__isnull=False,
            poblacion_inicial__gt=0,
        )
        .exclude(
            Q(
                movimientos_salida__estado=MovimientoPoblacion.Estado.ACTIVO,
                movimientos_salida__tipo__in=(
                    MovimientoPoblacion.Tipo.TRASLADO,
                    MovimientoPoblacion.Tipo.AJUSTE,
                ),
            )
            | Q(
                movimientos_entrada__estado=MovimientoPoblacion.Estado.ACTIVO,
                movimientos_entrada__tipo__in=(
                    MovimientoPoblacion.Tipo.TRASLADO,
                    MovimientoPoblacion.Tipo.AJUSTE,
                ),
            )
        )
        .distinct()
    )
    tasas = [
        Decimal(ciclo.poblacion_final) / Decimal(ciclo.poblacion_inicial)
        for ciclo in ciclos
    ]
    cantidad = len(tasas)
    base = {
        "prediccion_poblacion_final": None,
        "prediccion_min": None,
        "prediccion_max": None,
        "prediccion_tasa": None,
        "prediccion_ciclos_usados": cantidad,
        "prediccion_confianza": _confianza(cantidad),
        "prediccion_metodo_version": METODO_VERSION,
        "prediccion_calculada_en": timezone.now(),
        "prediccion_datos_hasta": datos_hasta,
        "prediccion_origen": CicloProductivo.OrigenPrediccion.SERVIDOR,
    }
    if not tasas:
        return base

    tasa = _mediana(tasas)
    poblacion = Decimal(poblacion_inicial)
    base.update(
        {
            "prediccion_poblacion_final": _redondear_poblacion(poblacion * tasa),
            "prediccion_min": _redondear_poblacion(poblacion * min(tasas)),
            "prediccion_max": _redondear_poblacion(poblacion * max(tasas)),
            "prediccion_tasa": tasa.quantize(Decimal("0.000001")),
        }
    )
    return base


def validar_prediccion_cache(datos):
    """Valida la instantánea que Android mostró offline antes de conservarla."""
    if not datos:
        return None
    cantidad = datos.get("prediccion_ciclos_usados", 0)
    estimacion = datos.get("prediccion_poblacion_final")
    minimo = datos.get("prediccion_min")
    maximo = datos.get("prediccion_max")
    tasa = datos.get("prediccion_tasa")
    if cantidad < 1 or None in (estimacion, minimo, maximo, tasa):
        raise ValueError("La predicción cacheada debe estar completa y usar al menos un ciclo.")
    if min(estimacion, minimo, maximo) < 0 or not minimo <= estimacion <= maximo:
        raise ValueError("El rango de la predicción cacheada no es coherente.")
    if Decimal(tasa) < 0:
        raise ValueError("La tasa de predicción no puede ser negativa.")
    return {
        "prediccion_poblacion_final": estimacion,
        "prediccion_min": minimo,
        "prediccion_max": maximo,
        "prediccion_tasa": Decimal(tasa),
        "prediccion_ciclos_usados": cantidad,
        "prediccion_confianza": datos["prediccion_confianza"],
        "prediccion_metodo_version": datos.get("prediccion_metodo_version", METODO_VERSION),
        "prediccion_calculada_en": datos["prediccion_calculada_en"],
        "prediccion_datos_hasta": datos["prediccion_datos_hasta"],
        "prediccion_origen": CicloProductivo.OrigenPrediccion.CACHE_ANDROID,
    }
