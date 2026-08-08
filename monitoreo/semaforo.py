from decimal import Decimal


PRIORIDAD = {"VERDE": 0, "AMARILLO": 1, "ROJO": 2}


def _lectura(parametro, valor, unidad, estado, diagnostico, recomendacion):
    return {
        "parametro": parametro,
        "valor": str(valor),
        "unidad": unidad,
        "estado": estado,
        "diagnostico": diagnostico,
        "recomendacion": recomendacion,
    }


def evaluar_agua(agua):
    """Replica los umbrales de Android v1.3 sin inferir mortalidad."""
    ph = Decimal(agua.ph)
    nitrito = Decimal(agua.nitrito)
    amoniaco_total = Decimal(agua.amoniaco_total)
    nitrato = Decimal(agua.nitrato)
    lecturas = []

    if ph < Decimal("6.0"):
        lecturas.append(_lectura("pH", ph, "", "ROJO", "Agua demasiado ácida.", "Encalar, hacer un recambio parcial y avisar al técnico."))
    elif ph > Decimal("9.0"):
        lecturas.append(_lectura("pH", ph, "", "ROJO", "Agua demasiado alcalina.", "Recambiar agua y suspender la alimentación del día."))
    elif ph < Decimal("6.5") or ph > Decimal("8.5"):
        lecturas.append(_lectura("pH", ph, "", "AMARILLO", "pH fuera del rango ideal.", "Revisar el manejo y volver a medir en 24 horas."))
    else:
        lecturas.append(_lectura("pH", ph, "", "VERDE", "pH dentro del rango provisional.", "Mantener el manejo actual."))

    parametros = (
        ("Nitrito", nitrito, Decimal("0.5"), Decimal("1.0")),
        ("Amoníaco total", amoniaco_total, Decimal("0.5"), Decimal("1.0")),
        ("Nitrato", nitrato, Decimal("50"), Decimal("100")),
    )
    for nombre, valor, precaucion, critico in parametros:
        if valor > critico:
            estado, diagnostico, recomendacion = "ROJO", f"{nombre} en nivel crítico.", "Aplicar el protocolo técnico y repetir la medición."
        elif valor >= precaucion:
            estado, diagnostico, recomendacion = "AMARILLO", f"{nombre} por encima del rango deseable.", "Revisar el manejo y repetir la medición."
        else:
            estado, diagnostico, recomendacion = "VERDE", f"{nombre} en nivel seguro provisional.", "Mantener el manejo actual."
        lecturas.append(_lectura(nombre, valor, "ppm", estado, diagnostico, recomendacion))

    nh3 = float(amoniaco_total) / (1 + 10 ** (9.25 - float(ph)))
    if nh3 > 0.05:
        estado_nh3 = "ROJO"
    elif nh3 > 0.02:
        estado_nh3 = "AMARILLO"
    else:
        estado_nh3 = "VERDE"
    lecturas.append(
        _lectura(
            "Amoníaco no ionizado estimado",
            f"{nh3:.5f}",
            "ppm",
            estado_nh3,
            "Estimación provisional de la fracción tóxica según pH.",
            "Estimación provisional con pKa 9.25 (~25 °C); confirmar con temperatura y protocolo técnico.",
        )
    )

    if amoniaco_total >= Decimal("0.5") and nitrito >= Decimal("0.5"):
        lecturas.append(_lectura("Ciclo del nitrógeno", nitrito, "ppm", "ROJO", "Amoníaco total y nitrito altos simultáneamente.", "Suspender alimentación, recambiar agua y avisar al técnico."))
    elif amoniaco_total >= Decimal("0.5") and nitrito < Decimal("0.5"):
        lecturas.append(_lectura("Ciclo del nitrógeno", amoniaco_total, "ppm", "AMARILLO", "Amoníaco total alto con nitrito bajo.", "Alimentar poco y medir con mayor frecuencia."))

    estado = max(lecturas, key=lambda item: PRIORIDAD[item["estado"]])["estado"]
    return {"estado": estado, "lecturas": lecturas, "umbrales_provisionales": True}
