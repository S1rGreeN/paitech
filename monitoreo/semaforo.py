from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist


PRIORIDAD = {"VERDE": 0, "AMARILLO": 1, "ROJO": 2}

# Conserva exactamente el comportamiento histórico de Vieja Azul cuando aún
# no existe un perfil en la base de datos.
PERFIL_RESPALDO = {
    "version": "vieja-azul-legado-1.3",
    "provisional": True,
    "ph_critico_bajo": Decimal("6.00"),
    "ph_ideal_bajo": Decimal("6.50"),
    "ph_ideal_alto": Decimal("8.50"),
    "ph_critico_alto": Decimal("9.00"),
    "nitrito_amarillo_desde": Decimal("0.500"),
    "nitrito_rojo_desde": Decimal("1.001"),
    "nitrato_amarillo_desde": Decimal("50.000"),
    "nitrato_rojo_desde": Decimal("100.001"),
    "amoniaco_total_amarillo_desde": Decimal("0.500"),
    "amoniaco_total_rojo_desde": Decimal("1.001"),
    "nh3_amarillo_desde": Decimal("0.02001"),
    "nh3_rojo_desde": Decimal("0.05001"),
}


def _lectura(parametro, valor, unidad, estado, diagnostico, recomendacion):
    return {
        "parametro": parametro,
        "valor": str(valor),
        "unidad": unidad,
        "estado": estado,
        "diagnostico": diagnostico,
        "recomendacion": recomendacion,
    }


def _perfil_para(agua, especie=None):
    if especie is None:
        try:
            especie = agua.jornada.piscina.especie
        except (AttributeError, ObjectDoesNotExist):
            especie = None
    if especie is None:
        return PERFIL_RESPALDO, None
    try:
        perfil = especie.perfil_semaforo
    except ObjectDoesNotExist:
        return PERFIL_RESPALDO, especie
    campos = {
        nombre: getattr(perfil, nombre)
        for nombre in PERFIL_RESPALDO
        if nombre not in {"version", "provisional"}
    }
    campos.update({"version": perfil.version, "provisional": perfil.provisional})
    return campos, especie


def evaluar_agua(agua, especie=None):
    """Evalúa agua con el perfil versionado de la especie de la piscina."""
    perfil, especie = _perfil_para(agua, especie)
    ph = Decimal(agua.ph)
    nitrito = Decimal(agua.nitrito)
    amoniaco_total = Decimal(agua.amoniaco_total)
    nitrato = Decimal(agua.nitrato)
    lecturas = []

    if ph < perfil["ph_critico_bajo"]:
        estado = "ROJO"
        diagnostico = "Agua demasiado ácida para el perfil de la especie."
        recomendacion = "Aplicar el protocolo técnico, verificar el valor y considerar un recambio parcial."
    elif ph > perfil["ph_critico_alto"]:
        estado = "ROJO"
        diagnostico = "Agua demasiado alcalina para el perfil de la especie."
        recomendacion = "Aplicar el protocolo técnico, verificar el valor y considerar un recambio parcial."
    elif ph < perfil["ph_ideal_bajo"] or ph > perfil["ph_ideal_alto"]:
        estado = "AMARILLO"
        diagnostico = "pH fuera del rango ideal de la especie."
        recomendacion = "Revisar el manejo y volver a medir en 24 horas."
    else:
        estado = "VERDE"
        diagnostico = "pH dentro del rango provisional de la especie."
        recomendacion = "Mantener el manejo actual."
    lecturas.append(_lectura("pH", ph, "", estado, diagnostico, recomendacion))

    parametros = (
        ("Nitrito", nitrito, perfil["nitrito_amarillo_desde"], perfil["nitrito_rojo_desde"]),
        (
            "Amoníaco total",
            amoniaco_total,
            perfil["amoniaco_total_amarillo_desde"],
            perfil["amoniaco_total_rojo_desde"],
        ),
        ("Nitrato", nitrato, perfil["nitrato_amarillo_desde"], perfil["nitrato_rojo_desde"]),
    )
    for nombre, valor, precaucion, critico in parametros:
        if valor >= critico:
            estado, diagnostico, recomendacion = (
                "ROJO",
                f"{nombre} en nivel crítico para la especie.",
                "Aplicar el protocolo técnico y repetir la medición.",
            )
        elif valor >= precaucion:
            estado, diagnostico, recomendacion = (
                "AMARILLO",
                f"{nombre} por encima del rango deseable para la especie.",
                "Revisar el manejo y repetir la medición.",
            )
        else:
            estado, diagnostico, recomendacion = (
                "VERDE",
                f"{nombre} en nivel seguro provisional para la especie.",
                "Mantener el manejo actual.",
            )
        lecturas.append(_lectura(nombre, valor, "ppm", estado, diagnostico, recomendacion))

    # Estimación provisional hasta que el sensor aporte temperatura. Se
    # conserva pKa=9.25 (~25 °C), igual que en la app original.
    nh3 = Decimal(str(float(amoniaco_total) / (1 + 10 ** (9.25 - float(ph)))))
    if nh3 >= perfil["nh3_rojo_desde"]:
        estado_nh3 = "ROJO"
    elif nh3 >= perfil["nh3_amarillo_desde"]:
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
            "Confirmar con temperatura y protocolo técnico cuando los sensores estén activos.",
        )
    )

    estado = max(lecturas, key=lambda item: PRIORIDAD[item["estado"]])["estado"]
    return {
        "estado": estado,
        "lecturas": lecturas,
        "umbrales_provisionales": perfil["provisional"],
        "perfil_version": perfil["version"],
        "especie": especie.nombre_comun if especie else None,
    }
