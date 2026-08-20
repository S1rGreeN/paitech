"""Compatibilidad con la migración histórica 0002.

La captura actual acepta valores numéricos continuos. Estas funciones deben
permanecer importables porque Django las referencia al reconstruir migraciones
antiguas desde cero; ningún modelo, formulario ni serializer vigente las usa.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError


# Valores que aparecen impresos en el API Freshwater Master Test Kit usado en
# Paipayales. El pH es la unión de las escalas normal y alta, pero se almacena
# como un único resultado final y no se registra qué escala produjo la lectura.
PH_VALORES = tuple(
    Decimal(valor)
    for valor in (
        "6.0",
        "6.4",
        "6.6",
        "6.8",
        "7.0",
        "7.2",
        "7.4",
        "7.6",
        "7.8",
        "8.0",
        "8.2",
        "8.4",
        "8.8",
    )
)
NITRATO_VALORES = tuple(Decimal(valor) for valor in ("0", "5", "10", "20", "40", "80", "160"))
NITRITO_VALORES = tuple(Decimal(valor) for valor in ("0", "0.25", "0.50", "1.0", "2.0", "5.0"))
AMONIACO_TOTAL_VALORES = tuple(
    Decimal(valor) for valor in ("0", "0.25", "0.50", "1.0", "2.0", "4.0", "8.0")
)


def _validar_valor(valor, permitidos, nombre):
    if Decimal(valor) not in permitidos:
        opciones = ", ".join(format(opcion, "f") for opcion in permitidos)
        raise ValidationError(
            f"{nombre} debe ser uno de los valores observables del kit: {opciones}.",
            code="valor_fuera_kit",
        )


def validar_ph_kit(valor):
    _validar_valor(valor, PH_VALORES, "El pH")


def validar_nitrato_kit(valor):
    _validar_valor(valor, NITRATO_VALORES, "El nitrato")


def validar_nitrito_kit(valor):
    _validar_valor(valor, NITRITO_VALORES, "El nitrito")


def validar_amoniaco_total_kit(valor):
    _validar_valor(valor, AMONIACO_TOTAL_VALORES, "El amoníaco total")


def opciones_formulario(valores):
    return tuple((format(valor, "f"), format(valor, "f")) for valor in valores)
