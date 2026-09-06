"""Exportaciones XLSX de una unidad productiva, sin archivos temporales ni secretos."""

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from io import BytesIO
import json
import math
from uuid import UUID
from zoneinfo import ZoneInfo

from django.db.models import Q
from django.utils import timezone
import xlsxwriter

from .models import AuditoriaCambio, MovimientoPoblacion, Piscina


ZONA = ZoneInfo("America/Guayaquil")
FORMATO_FECHA = "yyyy-mm-dd hh:mm:ss"
ANCHO_COLUMNAS = (24, 26, 29, 22, 22, 22, 24, 26, 39, 45)
MAX_FILAS = 1_048_576


class ExportacionDemasiadoGrande(ValueError):
    pass


def fecha_local(value):
    if isinstance(value, datetime) and timezone.is_aware(value):
        return value.astimezone(ZONA).replace(tzinfo=None)
    return value


def nombre(perfil):
    if perfil is None:
        return ""
    return perfil.user.get_full_name() or perfil.nickname or perfil.user.email


def correo(perfil):
    return perfil.user.email if perfil else ""


def persona(usuario):
    return (usuario.get_full_name() or usuario.email) if usuario else ""


class Libro:
    def __init__(self, unidad, usuario):
        self.buffer = BytesIO()
        self.wb = xlsxwriter.Workbook(self.buffer, {
            "in_memory": True, "strings_to_formulas": False,
            "strings_to_urls": False, "strings_to_numbers": False,
        })
        self.wb.set_properties({"title": f"Historial de {unidad.codigo}", "author": "PaiPayTech"})
        self.unidad = unidad
        self.usuario = usuario
        self.generado = timezone.now()
        base = {"font_name": "Arial", "font_size": 11, "valign": "top", "text_wrap": True}
        self.formatos = {
            "titulo": self.wb.add_format({**base, "font_size": 20, "bold": True, "font_color": "#254D32"}),
            "nota": self.wb.add_format({**base, "font_color": "#555B61", "italic": True}),
            "seccion": self.wb.add_format({**base, "bold": True, "bg_color": "#E8F0E6", "font_color": "#254D32"}),
            "cabecera": self.wb.add_format({**base, "bold": True, "bg_color": "#355E3B", "font_color": "#FFFFFF", "align": "center", "valign": "vcenter", "right": 1, "right_color": "#FFFFFF"}),
            "etiqueta": self.wb.add_format({**base, "bold": True, "font_color": "#414A42"}),
            "enlace": self.wb.add_format({**base, "font_color": "#246B45", "underline": 1}),
            "alerta": self.wb.add_format({"font_color": "#9C2F27", "bg_color": "#FFF0ED"}),
        }
        for banda in (0, 1):
            for tipo, codigo in (("texto", "@"), ("entero", "#,##0"), ("numero", "#,##0.00####"), ("fecha", FORMATO_FECHA)):
                self.formatos[tipo, banda] = self.wb.add_format({
                    **base, "bg_color": "#F3F6F2" if banda else "#FFFFFF",
                    "num_format": codigo,
                    "align": "right" if tipo in {"numero", "entero"} else "left",
                    "font_size": 10 if tipo == "fecha" else 11,
                    "indent": 0 if tipo == "fecha" else 1,
                    "right": 1, "right_color": "#E3EAE1",
                })
        self.tabla_numero = 0
        self.textos = defaultdict(list)

    def hoja(self, titulo, subtitulo):
        ws = self.wb.add_worksheet(titulo)
        ws.hide_gridlines(2)
        ws.set_zoom(85)
        ws.set_landscape()
        ws.set_paper(9)
        ws.fit_to_pages(1, 0)
        ws.set_margins(0.3, 0.3, 0.45, 0.45)
        ws.set_footer("&LPaiPayTech&RPágina &P de &N")
        for col, ancho in enumerate(ANCHO_COLUMNAS):
            ws.set_column(col, col, ancho)
        ws.set_row(0, 34)
        ws.write_string(0, 0, titulo, self.formatos["titulo"])
        ws.merge_range(1, 0, 1, 9, subtitulo, self.formatos["nota"])
        ws.set_row(1, 32)
        ws.merge_range(2, 0, 2, 9, "Fechas y horas: Ecuador continental (UTC−05:00). Celdas vacías: sin dato registrado.", self.formatos["nota"])
        ws.set_row(2, 24)
        if titulo != "Resumen":
            ws.write_url(3, 0, "internal:'Resumen'!A1", self.formatos["enlace"], "Volver al resumen")
            ws.freeze_panes(4, 0)
            ws.repeat_rows(0, 2)
        return ws

    def celda(self, ws, row, col, value, banda=0):
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        if isinstance(value, UUID):
            value = str(value)
        if isinstance(value, str) and len(value) > 240:
            ref = f"T{len(self.textos[ws.name]) + 1}"
            self.textos[ws.name].append((ref, xlsxwriter.utility.xl_rowcol_to_cell(row, col), value))
            value = value[:120] + f"… [texto completo: {ref}, al final de esta pestaña]"
        if isinstance(value, datetime):
            tipo = "fecha"
        elif isinstance(value, int) and not isinstance(value, bool):
            tipo = "entero"
        elif isinstance(value, (float, Decimal)):
            tipo = "numero"
        else:
            tipo = "texto"
        fmt = self.formatos[tipo, banda]
        value = fecha_local(value)
        if value is None or value == "":
            ws.write_blank(row, col, None, fmt)
        elif isinstance(value, str):
            ws.write_string(row, col, value, fmt)
        else:
            ws.write(row, col, value, fmt)
        if tipo != "texto":
            return 1
        return sum(max(1, math.ceil(len(linea) / max(8, ANCHO_COLUMNAS[col] - 3)))
                   for linea in str(value or "").split("\n"))

    def seccion(self, ws, row, titulo):
        if row >= MAX_FILAS - 4:
            raise ExportacionDemasiadoGrande("El historial supera las filas admitidas por Excel.")
        ws.merge_range(row, 0, row, 9, titulo, self.formatos["seccion"])
        ws.set_row(row, 26)
        return row + 1

    def ficha(self, ws, row, datos):
        # Una pareja etiqueta/valor por fila mantiene visibles las observaciones.
        for etiqueta, valor in datos:
            ws.write_string(row, 0, etiqueta, self.formatos["etiqueta"])
            ws.merge_range(row, 1, row, 9, "")
            self.celda(ws, row, 1, valor, row % 2)
            ws.set_row(row, max(36, 16 * math.ceil(len(etiqueta) / 19)))
            row += 1
        return row + 1

    def tabla(self, ws, row, titulo, cabeceras, filas, vacio="Sin registros."):
        row = self.seccion(ws, row, titulo)
        inicio = row
        ws.set_row(row, 36)
        for col, etiqueta in enumerate(cabeceras):
            ws.write_string(row, col, etiqueta, self.formatos["cabecera"])
        row += 1
        for values in filas:
            if row >= MAX_FILAS - 4:
                raise ExportacionDemasiadoGrande("El historial supera las filas admitidas por Excel.")
            lineas = max(self.celda(ws, row, col, value, (row - inicio) % 2) for col, value in enumerate(values))
            ws.set_row(row, min(150, max(32, 16 * lineas)))
            row += 1
        if row == inicio + 1:
            ws.merge_range(row, 0, row, len(cabeceras) - 1, vacio, self.formatos["nota"])
            ws.set_row(row, 34)
            row += 1
        else:
            self.tabla_numero += 1
            ws.add_table(inicio, 0, row - 1, len(cabeceras) - 1, {
                "name": f"Datos{self.tabla_numero}", "style": None,
                "columns": [{"header": c, "header_format": self.formatos["cabecera"]} for c in cabeceras],
            })
            for col, etiqueta in enumerate(cabeceras):
                if etiqueta in {"Estado", "Calidad"}:
                    for texto in ("Anulad", "Borrador", "Inválida"):
                        ws.conditional_format(inicio + 1, col, row - 1, col, {
                            "type": "text", "criteria": "containing", "value": texto,
                            "format": self.formatos["alerta"],
                        })
        return row + 2

    def terminar_hoja(self, ws, row):
        if self.textos[ws.name]:
            row = self.seccion(ws, row, "Textos completos (fragmentos consecutivos)")
            ws.write_string(row, 0, "Referencia", self.formatos["cabecera"])
            ws.write_string(row, 1, "Celda de origen", self.formatos["cabecera"])
            ws.write_string(row, 2, "Parte / total", self.formatos["cabecera"])
            ws.merge_range(row, 3, row, 9, "Contenido", self.formatos["cabecera"])
            ws.set_row(row, 28)
            row += 1
            for ref, origen, texto in self.textos[ws.name]:
                partes = [texto[i:i + 240] for i in range(0, len(texto), 240)]
                for n, parte in enumerate(partes, 1):
                    if row >= MAX_FILAS - 1:
                        raise ExportacionDemasiadoGrande("El historial supera las filas admitidas por Excel.")
                    fmt = self.formatos["texto", row % 2]
                    ws.write_string(row, 0, ref, fmt)
                    ws.write_string(row, 1, origen, fmt)
                    ws.write_string(row, 2, f"{n} / {len(partes)}", fmt)
                    ws.merge_range(row, 3, row, 9, parte, fmt)
                    ws.set_row(row, max(36, min(400, 16 * (parte.count("\n") + 2))))
                    row += 1
        ws.print_area(0, 0, row, 9)

    def cerrar(self):
        self.wb.close()
        self.buffer.seek(0)
        return self.buffer


def cargar_datos(unidad):
    peces = isinstance(unidad, Piscina)
    relaciones = ["autor_apertura__user", "autor_cierre__user"]
    if peces:
        relaciones += ["especie", "piscina_destino_cierre"]
    ciclos = list(unidad.ciclos.select_related(*relaciones).order_by("numero", "id"))
    registros = defaultdict(list)
    sensores = defaultdict(list)
    movimientos = defaultdict(list)
    audit_ids = defaultdict(set)
    tipo_ciclo = "CICLO" if peces else "CICLO_LOMBRIZ"
    for ciclo in ciclos:
        audit_ids[tipo_ciclo].add(ciclo.pk)
    consulta = unidad.registros.select_related("autor__user", "anulada_por").order_by("capturada_en", "id")
    if peces:
        consulta = consulta.select_related("agua", "muestra_biometrica").prefetch_related("muestra_biometrica__peces")
    for registro in consulta.iterator(chunk_size=500):
        registros[registro.ciclo_id].append(registro)
        audit_ids["JORNADA" if peces else "REGISTRO_LOMBRIZ"].add(registro.pk)
    if peces:
        for lectura in unidad.lecturas_sensor.select_related("dispositivo").order_by("medida_en", "id").iterator(chunk_size=500):
            sensores[lectura.ciclo_id].append(lectura)
        consulta_mov = MovimientoPoblacion.objects.filter(
            Q(piscina_origen=unidad) | Q(piscina_destino=unidad)
        ).select_related("autor__user", "anulado_por", "piscina_origen", "piscina_destino").order_by("ocurrido_en", "id")
        for mov in consulta_mov.iterator(chunk_size=500):
            ciclo_id = mov.ciclo_origen_id if mov.piscina_origen_id == unidad.pk else mov.ciclo_destino_id
            movimientos[ciclo_id].append(mov)
            audit_ids["MOVIMIENTO"].add(mov.pk)
    filtro = Q(pk__in=[])
    for entidad, ids in audit_ids.items():
        if ids:
            filtro |= Q(entidad=entidad, entidad_uuid__in=ids)
    auditorias = defaultdict(list)
    for evento in AuditoriaCambio.objects.filter(filtro).filter(
        Q(comunidad=unidad.comunidad) | Q(comunidad__isnull=True)
    ).select_related("actor").order_by("fecha", "id").iterator(chunk_size=500):
        auditorias[evento.entidad, evento.entidad_uuid].append(evento)
    return ciclos, registros, sensores, movimientos, auditorias


def ficha_ciclo(ciclo, peces):
    campos = [
        ("Estado", ciclo.get_estado_display()), ("Inicio", ciclo.iniciado_en),
        ("Responsable de apertura", nombre(ciclo.autor_apertura)),
        ("Correo de apertura", correo(ciclo.autor_apertura)),
        ("Población inicial" if peces else "Conteo inicial", ciclo.poblacion_inicial if peces else ciclo.conteo_inicial),
        ("Observaciones de apertura", ciclo.observaciones_apertura),
        ("Cierre", ciclo.cerrado_en), ("Responsable de cierre", nombre(ciclo.autor_cierre)),
        ("Correo de cierre", correo(ciclo.autor_cierre)),
        ("Población final" if peces else "Conteo final", ciclo.poblacion_final if peces else ciclo.conteo_final),
        ("Observaciones de cierre", ciclo.observaciones_cierre),
    ]
    if peces:
        campos += [
            ("Especie", str(ciclo.especie)),
            ("Duración estimada (meses)", ciclo.duracion_estimada_meses),
            ("Destino del cierre", ciclo.get_destino_cierre_display()),
            ("Piscina destino", str(ciclo.piscina_destino_cierre) if ciclo.piscina_destino_cierre else ""),
            ("Peso cosechado (kg)", ciclo.peso_total_cosechado_kg),
        ]
    return campos


def tabla_jornadas(libro, ws, row, registros):
    row = libro.tabla(ws, row, "Jornadas de registro", [
        "Fecha y hora de captura", "Responsable", "Correo", "Población estimada", "Estado",
        "Fuente", "Dispositivo", "Versión", "ID de jornada", "Observaciones",
    ], ((r.capturada_en, nombre(r.autor), correo(r.autor), r.poblacion_estimada, r.get_estado_display(),
         r.get_fuente_display(), r.dispositivo_id, r.version, r.id, r.observaciones) for r in registros))
    row = libro.tabla(ws, row, "Calidad de agua", [
        "Fecha y hora de captura", "Responsable", "Correo", "pH", "Nitrato (ppm)", "Nitrito (ppm)",
        "Amoníaco total (ppm)", "Estado", "ID de jornada",
    ], ((r.capturada_en, nombre(r.autor), correo(r.autor), r.agua.ph, r.agua.nitrato, r.agua.nitrito,
         r.agua.amoniaco_total, r.get_estado_display(), r.id) for r in registros if hasattr(r, "agua")))
    row = libro.tabla(ws, row, "Biometría individual", [
        "Fecha y hora de captura", "Responsable", "Correo", "Pez en la muestra", "Peso (g)",
        "Longitud total (cm)", "Método", "Estado", "ID de jornada", "ID de observación",
    ], ((r.capturada_en, nombre(r.autor), correo(r.autor), p.orden if p else None,
         p.peso_gramos if p else None, p.talla_centimetros if p else None,
         r.muestra_biometrica.metodo, r.get_estado_display(), r.id, p.id if p else None)
        for r in registros if hasattr(r, "muestra_biometrica")
        for p in (list(r.muestra_biometrica.peces.all()) or [None])))
    return row


def tabla_sensores(libro, ws, row, lecturas):
    row = libro.tabla(ws, row, "Sensores (registro automático; no se registra responsable humano)", [
        "Fecha y hora de medición", "Sensor", "Oxígeno disuelto (mg/L)", "Temperatura (°C)",
        "Turbidez (NTU)", "Calidad", "Detalle de calidad", "Recibida en servidor", "ID de lectura", "Metadatos",
    ], ((r.medida_en, f"{r.dispositivo.codigo} · {r.dispositivo.nombre}", r.oxigeno_disuelto_mg_l,
         r.temperatura_c, r.turbidez_ntu, r.get_calidad_display(), r.detalle_calidad, r.recibida_en, r.id, r.metadatos)
        for r in lecturas))
    dispositivos = {r.dispositivo_id: r.dispositivo for r in lecturas}
    if dispositivos:
        row = libro.tabla(ws, row, "Dispositivos de las lecturas", [
            "Código", "Nombre", "Instalado en", "Último uso", "Creado en", "Activo", "ID del dispositivo",
        ], ((d.codigo, d.nombre, d.instalado_en, d.ultimo_uso_en, d.creado_en, "Sí" if d.activo else "No", d.id)
            for d in dispositivos.values()))
    return row


def tabla_cama(libro, ws, row, registros):
    return libro.tabla(ws, row, "Lombricultura: conteo y pH del suelo", [
        "Fecha y hora de captura", "Responsable", "Correo", "Lombrices observadas", "pH del suelo",
        "Estado", "Fuente", "Versión", "ID de registro", "Observaciones",
    ], ((r.capturada_en, nombre(r.autor), correo(r.autor), r.conteo_lombrices, r.ph_suelo,
         r.get_estado_display(), r.get_fuente_display(), r.version, r.id, r.observaciones) for r in registros))


def trazabilidad(libro, ws, row, registros):
    row = libro.tabla(ws, row, "Recepción, modificaciones y anulaciones", [
        "ID de registro", "Recibido en servidor", "Creado en servidor", "Última modificación",
        "Anulado en", "Anulado por", "Correo de anulación", "Dispositivo", "Motivo de anulación",
    ], ((r.id, r.recibida_en, r.creada_en, r.modificada_en, r.anulada_en, persona(r.anulada_por),
         r.anulada_por.email if r.anulada_por else "", r.dispositivo_id, r.motivo_anulacion) for r in registros))
    return row


def tabla_movimientos(libro, ws, row, movimientos):
    row = libro.tabla(ws, row, "Movimientos de población", [
        "Fecha y hora", "Responsable", "Correo", "Tipo", "Cantidad", "Piscina origen", "Piscina destino",
        "Estado", "ID de movimiento", "Observaciones",
    ], ((m.ocurrido_en, nombre(m.autor), correo(m.autor), m.get_tipo_display(), m.cantidad,
         str(m.piscina_origen) if m.piscina_origen else "", str(m.piscina_destino) if m.piscina_destino else "",
         m.get_estado_display(), m.id, m.observaciones) for m in movimientos))
    if movimientos:
        row = libro.tabla(ws, row, "Trazabilidad de movimientos", [
            "ID de movimiento", "Creado en", "Modificado en", "Versión", "Anulado en", "Anulado por",
            "Correo de anulación", "ID ciclo origen", "ID ciclo destino", "Motivo de anulación",
        ], ((m.id, m.creado_en, m.modificado_en, m.version, m.anulado_en, persona(m.anulado_por),
             m.anulado_por.email if m.anulado_por else "", m.ciclo_origen_id, m.ciclo_destino_id, m.motivo_anulacion)
            for m in movimientos))
    return row


def exportar_unidad(unidad, usuario):
    """El llamador debe resolver la unidad con los permisos de la vista web."""
    peces = isinstance(unidad, Piscina)
    ciclos, registros, sensores, movimientos, auditorias = cargar_datos(unidad)
    libro = Libro(unidad, usuario)
    tipo = "Piscina" if peces else "Cama"
    contexto = f"{tipo} {unidad.codigo} · {unidad.nombre} · {unidad.comunidad.nombre}"
    resumen = libro.hoja("Resumen", contexto)
    row = libro.ficha(resumen, 4, [
        ("Generado en", libro.generado), ("Solicitado por", persona(usuario)),
    ])
    datos_unidad = [("Correo del solicitante", usuario.email), ("Comunidad", unidad.comunidad.nombre),
        ("Código de comunidad", unidad.comunidad.codigo), ("ID de comunidad", unidad.comunidad.id_publico),
        ("Código", unidad.codigo), ("Nombre", unidad.nombre), ("ID de la unidad", unidad.id),
        ("Área (m²)", unidad.area_m2), ("Descripción", unidad.descripcion),
        ("Activa", "Sí" if unidad.activa else "No"), ("Creada en", unidad.fecha_creacion),
        ("Alcance", "Todos los ciclos y registros, incluidos borradores y anulados. Los anulados no representan mediciones vigentes."),
    ]
    if not peces:
        datos_unidad += [("Datos disponibles", "Conteo observado de lombrices y pH del suelo. Las camas no tienen registros de calidad de agua ni sensores en el sistema actual.")]
    entradas = [(f"Ciclo {c.numero}", c) for c in ciclos]
    if registros[None] or sensores[None] or movimientos[None]:
        entradas.append(("Sin ciclo", None))
    columnas_indice = ["Pestaña", "Estado", "Inicio", "Cierre", "Registros"]
    if peces:
        columnas_indice += ["Lecturas de sensores", "Movimientos"]
    filas_indice = []
    for titulo, ciclo in entradas:
        ciclo_id = ciclo.pk if ciclo else None
        fila = [titulo, ciclo.get_estado_display() if ciclo else "Sin asignar",
                ciclo.iniciado_en if ciclo else None, ciclo.cerrado_en if ciclo else None,
                len(registros[ciclo_id])]
        if peces:
            fila += [len(sensores[ciclo_id]), len(movimientos[ciclo_id])]
        filas_indice.append(fila)
    row = libro.tabla(resumen, row, "Índice de ciclos", columnas_indice, filas_indice,
                      vacio="Esta unidad todavía no tiene ciclos ni registros.")
    # El índice conserva números y fechas reales; solo el nombre es un enlace.
    inicio_indice = row - len(entradas) - 2
    for index, (titulo, ciclo) in enumerate(entradas):
        resumen.write_url(inicio_indice + index, 0, f"internal:'{titulo}'!A1", libro.formatos["enlace"], titulo)
        ws = libro.hoja(titulo, contexto)
        regs = registros[ciclo.pk if ciclo else None]
        lects = sensores[ciclo.pk if ciclo else None]
        movs = movimientos[ciclo.pk if ciclo else None]
        if ciclo:
            r = libro.ficha(ws, 5, [
                ("Estado", ciclo.get_estado_display()), ("Inicio", ciclo.iniciado_en),
                ("Cierre", ciclo.cerrado_en),
            ])
        else:
            r = libro.ficha(ws, 5, [("Asignación", "Registros históricos sin ciclo asociado. Se conservan sin asignarles un ciclo por fecha.")])
        r = tabla_jornadas(libro, ws, r, regs) if peces else tabla_cama(libro, ws, r, regs)
        if peces:
            r = tabla_sensores(libro, ws, r, lects)
            r = tabla_movimientos(libro, ws, r, movs)
        r = trazabilidad(libro, ws, r, regs)
        if ciclo:
            r = libro.seccion(ws, r, "Datos del ciclo y trazabilidad")
            datos = ficha_ciclo(ciclo, peces) + [("ID de ciclo", ciclo.id), ("Versión", ciclo.version), ("Fuente", ciclo.get_fuente_display()),
                     ("Dispositivo de apertura", ciclo.dispositivo_id), ("Creado en", ciclo.creado_en), ("Modificado en", ciclo.modificado_en)]
            if peces:
                datos += [(etiqueta, getattr(ciclo, campo)) for etiqueta, campo in [
                    ("Predicción de población final", "prediccion_poblacion_final"), ("Predicción mínima", "prediccion_min"),
                    ("Predicción máxima", "prediccion_max"), ("Tasa de supervivencia (fracción)", "prediccion_tasa"),
                    ("Ciclos históricos usados", "prediccion_ciclos_usados"), ("Confianza", "prediccion_confianza"),
                    ("Versión del método", "prediccion_metodo_version"), ("Predicción calculada en", "prediccion_calculada_en"),
                    ("Datos de predicción hasta", "prediccion_datos_hasta"), ("Origen de predicción", "prediccion_origen"),
                ]]
            r = libro.ficha(ws, r, datos)
        claves = [("JORNADA" if peces else "REGISTRO_LOMBRIZ", reg.pk) for reg in regs]
        claves += [("MOVIMIENTO", mov.pk) for mov in movs]
        if ciclo:
            claves.append(("CICLO" if peces else "CICLO_LOMBRIZ", ciclo.pk))
        eventos = sorted((a for clave in claves for a in auditorias[clave]), key=lambda a: (a.fecha, a.pk))
        r = libro.tabla(ws, r, "Historial de cambios", [
            "Fecha y hora", "Responsable del cambio", "Correo", "Entidad", "Acción", "Versión anterior",
            "Versión nueva", "ID del registro", "Motivo", "Datos anteriores y nuevos",
        ], ((a.fecha, persona(a.actor), a.actor.email, a.get_entidad_display(), a.get_accion_display(),
             a.version_anterior, a.version_nueva, a.entidad_uuid, a.motivo,
             {"anteriores": a.datos_anteriores, "nuevos": a.datos_nuevos}) for a in eventos))
        libro.terminar_hoja(ws, r)
    row = libro.seccion(resumen, row, "Unidad y alcance de la descarga")
    row = libro.ficha(resumen, row, datos_unidad)
    libro.terminar_hoja(resumen, row)
    return libro.cerrar()
