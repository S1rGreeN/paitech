from datetime import datetime, timezone as datetime_timezone
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .exportaciones import exportar_unidad
from .models import (
    AuditoriaCambio, CamaLombrices, CicloLombricultura, CicloProductivo,
    Comunidad, DispositivoSensor, JornadaRegistro, LecturaSensor, MedicionAgua,
    MovimientoPoblacion, MuestraBiometrica, ObservacionPez, Piscina, RegistroLombricultura,
)
from .web_scope import SESSION_COMUNIDAD_WEB


NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


class LeerXlsx:
    """Lee el archivo entregado, sin agregar una dependencia de lectura a producción."""

    def __init__(self, contenido):
        self.zip = ZipFile(BytesIO(contenido))
        assert self.zip.testzip() is None
        cadenas = ET.fromstring(self.zip.read("xl/sharedStrings.xml"))
        self.strings = ["".join(n.itertext()) for n in cadenas]
        relaciones = ET.fromstring(self.zip.read("xl/_rels/workbook.xml.rels"))
        rutas = {r.attrib["Id"]: r.attrib["Target"] for r in relaciones}
        workbook = ET.fromstring(self.zip.read("xl/workbook.xml"))
        self.sheets = {}
        for hoja in workbook.find("x:sheets", NS):
            rid = hoja.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
            self.sheets[hoja.attrib["name"]] = ET.fromstring(self.zip.read("xl/" + rutas[rid]))

    def value(self, celda):
        valor = celda.find("x:v", NS)
        if valor is None:
            return None
        if celda.get("t") == "s":
            return self.strings[int(valor.text)]
        return float(valor.text)

    def rows(self, hoja):
        for row in self.sheets[hoja].findall("x:sheetData/x:row", NS):
            yield {c.attrib["r"].rstrip("0123456789"): self.value(c) for c in row}

    def table(self, hoja, titulo):
        filas = list(self.rows(hoja))
        i = next(i for i, r in enumerate(filas) if r.get("A") == titulo)
        headers = filas[i + 1]
        salida = []
        for row in filas[i + 2:]:
            if not any(v is not None for v in row.values()):
                break
            if row.get("A") == "Sin registros.":
                break
            # Las filas vacías no siempre se serializan; una banda es una sola celda.
            if len([v for v in row.values() if v is not None]) == 1:
                break
            salida.append({label: row.get(col) for col, label in headers.items() if label})
        return salida


class ExportacionesExcelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Usuario = get_user_model()
        cls.ana = Usuario.objects.create_user(
            email="ana.export@example.com", password="ClaveLocal123!", first_name="Ana", last_name="Prueba"
        )
        cls.luis = Usuario.objects.create_user(
            email="luis.export@example.com", password="ClaveLocal123!", first_name="Luis", last_name="Prueba"
        )
        cls.tecnico = Usuario.objects.create_superuser(email="tecnico.export@example.com", password="ClaveLocal123!")
        cls.comunidad = cls.ana.perfil_acuicultor.comunidad
        cls.galo = Comunidad.objects.get(codigo="colegio-galo-plaza-lasso")
        cls.piscina = Piscina.objects.get(comunidad=cls.comunidad, codigo="P-01")
        cls.ajena = Piscina.objects.get(comunidad=cls.galo, codigo="P-01")
        cls.cama = CamaLombrices.objects.get(comunidad=cls.comunidad, codigo="C-01")
        cls.cama_ajena = CamaLombrices.objects.create(comunidad=cls.galo, codigo="C-99", nombre="Cama ajena")
        inicio = datetime(2026, 1, 1, 12, tzinfo=datetime_timezone.utc)
        cierre = datetime(2026, 7, 1, tzinfo=datetime_timezone.utc)
        cls.captura = datetime(2026, 6, 30, 2, 3, 4, tzinfo=datetime_timezone.utc)
        cls.ciclo1 = CicloProductivo.objects.create(
            piscina=cls.piscina, especie=cls.piscina.especie, numero=1, estado="CERRADO",
            iniciado_en=inicio, poblacion_inicial=200, autor_apertura=cls.ana.perfil_acuicultor,
            cerrado_en=cierre, poblacion_final=180, autor_cierre=cls.luis.perfil_acuicultor,
            destino_cierre="VENTA", peso_total_cosechado_kg=Decimal("12.345"),
            observaciones_apertura="Inicio de la cohorte", observaciones_cierre="Cosecha completa",
        )
        cls.ciclo2 = CicloProductivo.objects.create(
            piscina=cls.piscina, especie=cls.piscina.especie, numero=2, iniciado_en=cierre,
            poblacion_inicial=220, autor_apertura=cls.luis.perfil_acuicultor,
        )
        cls.jornada = JornadaRegistro.objects.create(
            piscina=cls.piscina, ciclo=cls.ciclo1, autor=cls.ana.perfil_acuicultor,
            capturada_en=cls.captura, poblacion_estimada=190, estado="COMPLETA",
            observaciones="Agua y biometría de la misma jornada", fuente="ANDROID", dispositivo_id="telefono-local",
        )
        MedicionAgua.objects.create(jornada=cls.jornada, ph="7.25", nitrato="12.125", nitrito="0.000", amoniaco_total="0.125")
        muestra = MuestraBiometrica.objects.create(jornada=cls.jornada, metodo="Muestreo aleatorio")
        cls.pez = ObservacionPez.objects.create(muestra=muestra, orden=1, peso_gramos="125.25", talla_centimetros="18.50")
        ObservacionPez.objects.create(muestra=muestra, orden=2, peso_gramos="130.75", talla_centimetros="19.25")
        cls.anulada = JornadaRegistro.objects.create(
            piscina=cls.piscina, ciclo=cls.ciclo2, autor=cls.luis.perfil_acuicultor,
            capturada_en=cierre, poblacion_estimada=0, estado="ANULADA", version=2,
            anulada_por=cls.luis, anulada_en=cierre, motivo_anulacion="Duplicado confirmado",
        )
        cls.legada = JornadaRegistro.objects.create(
            piscina=cls.piscina, ciclo=None, autor=cls.ana.perfil_acuicultor,
            capturada_en=inicio, poblacion_estimada=50, estado="BORRADOR",
        )
        cls.dispositivo = DispositivoSensor.objects.create(
            piscina=cls.piscina, codigo="SENSOR-PRUEBA", nombre="Sensor de oxígeno", secreto_hash="NO-EXPORTAR-ESTE-SECRETO",
        )
        cls.lectura = LecturaSensor.objects.create(
            piscina=cls.piscina, ciclo=cls.ciclo1, dispositivo=cls.dispositivo, medida_en=cls.captura,
            oxigeno_disuelto_mg_l=0, calidad="PARCIAL", detalle_calidad="Temperatura y turbidez no disponibles",
            metadatos={"bateria": 90, "unidad": "porcentaje"},
        )
        LecturaSensor.objects.create(
            piscina=cls.piscina, ciclo=None, dispositivo=cls.dispositivo, medida_en=inicio,
            temperatura_c="26.125", calidad="INVALIDA", detalle_calidad="Pendiente de calibración",
        )
        cls.movimiento = MovimientoPoblacion.objects.create(
            piscina_origen=cls.piscina, ciclo_origen=cls.ciclo1, tipo="MORTALIDAD", cantidad=10,
            autor=cls.luis.perfil_acuicultor, ocurrido_en=cls.captura, observaciones="Inspección diaria",
        )
        AuditoriaCambio.objects.create(
            entidad="JORNADA", entidad_uuid=cls.jornada.id, comunidad=cls.comunidad, accion="CORREGIR",
            actor=cls.luis, version_anterior=1, version_nueva=2, motivo="Ajuste del conteo",
            datos_anteriores={"poblacion_estimada": 191}, datos_nuevos={"poblacion_estimada": 190},
        )
        cls.ciclo_cama = CicloLombricultura.objects.create(
            cama=cls.cama, numero=1, iniciado_en=inicio, conteo_inicial=100,
            autor_apertura=cls.ana.perfil_acuicultor,
        )
        cls.registro_cama = RegistroLombricultura.objects.create(
            cama=cls.cama, ciclo=cls.ciclo_cama, autor=cls.luis.perfil_acuicultor,
            capturada_en=cls.captura, conteo_lombrices=125, ph_suelo="6.75", observaciones="Sustrato húmedo",
        )

    def descargar(self, unidad=None):
        unidad = unidad or self.piscina
        ruta = "monitoreo:piscina_excel" if isinstance(unidad, Piscina) else "monitoreo:cama_excel"
        return self.client.get(reverse(ruta, args=[unidad.pk]))

    def libro(self, unidad=None):
        self.client.force_login(self.ana)
        response = self.descargar(unidad)
        self.assertEqual(response.status_code, 200)
        contenido = b"".join(response.streaming_content)
        response.close()
        return LeerXlsx(contenido)

    def test_descarga_requiere_login_y_respeta_comunidad_en_ambos_tipos(self):
        for unidad in (self.piscina, self.cama):
            self.assertEqual(self.descargar(unidad).status_code, 302)
        self.client.force_login(self.ana)
        for unidad in (self.ajena, self.cama_ajena):
            self.assertEqual(self.descargar(unidad).status_code, 404)
        url = reverse("monitoreo:piscina_excel", args=[self.ajena.pk])
        self.assertEqual(self.client.get(url, {"comunidad": str(self.galo.id_publico)}).status_code, 404)

    def test_superusuario_descarga_en_vista_global_y_respeta_el_filtro_elegido(self):
        self.client.force_login(self.tecnico)
        self.assertEqual(self.descargar(self.ajena).status_code, 200)
        session = self.client.session
        session[SESSION_COMUNIDAD_WEB] = str(self.comunidad.id_publico)
        session.save()
        self.assertEqual(self.descargar(self.ajena).status_code, 404)

    def test_cabeceras_de_descarga_y_boton_web(self):
        self.client.force_login(self.ana)
        for unidad, detalle, ruta in (
            (self.piscina, "piscina_detalle", "piscina_excel"), (self.cama, "cama_detalle", "cama_excel"),
        ):
            response = self.descargar(unidad)
            self.assertIn("attachment;", response["Content-Disposition"])
            self.assertIn(".xlsx", response["Content-Disposition"])
            self.assertEqual(response["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.assertIn("no-store", response["Cache-Control"])
            page = self.client.get(reverse("monitoreo:" + detalle, args=[unidad.pk]))
            self.assertContains(page, reverse("monitoreo:" + ruta, args=[unidad.pk]))
            self.assertContains(page, "Descargar Excel")

    def test_pestanas_ciclos_tipos_numericos_horas_y_responsables(self):
        libro = self.libro()
        self.assertEqual(list(libro.sheets), ["Resumen", "Ciclo 1", "Ciclo 2", "Sin ciclo"])
        agua = libro.table("Ciclo 1", "Calidad de agua")[0]
        self.assertEqual(agua["pH"], 7.25)
        self.assertEqual(agua["Nitrato (ppm)"], 12.125)
        self.assertEqual(agua["Nitrito (ppm)"], 0)
        self.assertEqual(agua["Responsable"], "Ana Prueba")
        self.assertEqual(agua["Correo"], self.ana.email)
        esperado = (datetime(2026, 6, 29, 21, 3, 4) - datetime(1899, 12, 30)).total_seconds() / 86400
        self.assertAlmostEqual(agua["Fecha y hora de captura"], esperado, places=7)
        peces = libro.table("Ciclo 1", "Biometría individual")
        self.assertEqual(len(peces), 2)
        self.assertEqual(peces[0]["Peso (g)"], 125.25)
        self.assertEqual(peces[1]["Longitud total (cm)"], 19.25)
        self.assertEqual(peces[0]["ID de observación"], str(self.pez.pk))
        self.assertIn("Muestreo aleatorio", libro.strings)

    def test_sensores_conservan_ceros_nulos_calidad_y_dispositivo_sin_secretos(self):
        libro = self.libro()
        sensores = libro.table("Ciclo 1", "Sensores (registro automático; no se registra responsable humano)")
        self.assertEqual(sensores[0]["Oxígeno disuelto (mg/L)"], 0)
        self.assertIsNone(sensores[0]["Temperatura (°C)"])
        self.assertEqual(sensores[0]["Calidad"], "Parcial")
        self.assertIn("SENSOR-PRUEBA", sensores[0]["Sensor"])
        self.assertNotIn(self.dispositivo.secreto_hash, libro.strings)
        self.assertNotIn(str(self.dispositivo.selector), libro.strings)
        self.assertIn("Inválida", libro.strings)

    def test_muestra_en_borrador_sin_peces_conserva_metodo_sin_inventar_peso(self):
        MuestraBiometrica.objects.create(jornada=self.legada, metodo="Muestreo pendiente")
        fila = self.libro().table("Sin ciclo", "Biometría individual")[0]
        self.assertEqual(fila["Método"], "Muestreo pendiente")
        self.assertEqual(fila["Estado"], "Borrador")
        self.assertIsNone(fila["Peso (g)"])
        self.assertIsNone(fila["Longitud total (cm)"])

    def test_incluye_anulados_legados_movimientos_y_auditoria(self):
        libro = self.libro()
        self.assertEqual(libro.table("Ciclo 2", "Jornadas de registro")[0]["Estado"], "Anulada")
        self.assertEqual(libro.table("Sin ciclo", "Jornadas de registro")[0]["Estado"], "Borrador")
        movimientos = libro.table("Ciclo 1", "Movimientos de población")
        self.assertEqual(movimientos[0]["Cantidad"], 10)
        self.assertEqual(movimientos[0]["Responsable"], "Luis Prueba")
        self.assertIn("Duplicado confirmado", libro.strings)
        auditoria = libro.table("Ciclo 1", "Historial de cambios")[0]
        self.assertEqual(auditoria["Responsable del cambio"], "Luis Prueba")
        self.assertIn('"poblacion_estimada": 191', auditoria["Datos anteriores y nuevos"])

    def test_cama_exporta_conteo_y_suelo_sin_inventar_mediciones(self):
        libro = self.libro(self.cama)
        self.assertEqual(list(libro.sheets), ["Resumen", "Ciclo 1"])
        fila = libro.table("Ciclo 1", "Lombricultura: conteo y pH del suelo")[0]
        self.assertEqual(fila["Lombrices observadas"], 125)
        self.assertEqual(fila["pH del suelo"], 6.75)
        self.assertEqual(fila["Responsable"], "Luis Prueba")
        self.assertNotIn("Oxígeno disuelto (mg/L)", libro.strings)
        self.assertNotIn("Calidad de agua", libro.strings)
        self.assertNotIn("Lecturas de sensores", libro.strings)

    def test_no_limita_la_descarga_a_los_30_registros_ni_20_ciclos_de_la_web(self):
        JornadaRegistro.objects.bulk_create([
            JornadaRegistro(piscina=self.piscina, ciclo=self.ciclo2, autor=self.ana.perfil_acuicultor,
                            poblacion_estimada=n, estado="COMPLETA", capturada_en=self.captura)
            for n in range(40)
        ])
        CicloProductivo.objects.bulk_create([
            CicloProductivo(piscina=self.piscina, especie=self.piscina.especie, numero=n, estado="ANULADO",
                            iniciado_en=self.captura, poblacion_inicial=100, autor_apertura=self.ana.perfil_acuicultor)
            for n in range(3, 24)
        ])
        libro = self.libro()
        self.assertIn("Ciclo 23", libro.sheets)
        self.assertEqual(len(libro.table("Ciclo 2", "Jornadas de registro")), 41)

    def test_unidad_sin_ciclos_entrega_archivo_valido(self):
        vacia = Piscina.objects.create(comunidad=self.comunidad, especie=self.piscina.especie, codigo="P-99", nombre="Sin registros")
        libro = self.libro(vacia)
        self.assertEqual(list(libro.sheets), ["Resumen"])
        self.assertIn("Esta unidad todavía no tiene ciclos ni registros.", libro.strings)

    def test_textos_no_se_ejecutan_como_formulas_y_notas_largas_se_conservan(self):
        texto = "Nota larga con acentos: áéíóú. " * 1500
        self.jornada.observaciones = texto
        self.jornada.save(update_fields=["observaciones"])
        self.piscina.nombre = '=HYPERLINK("https://ejemplo.invalid","abrir")'
        self.piscina.save(update_fields=["nombre"])
        libro = self.libro()
        self.assertIn(self.piscina.nombre, libro.strings)
        self.assertFalse(any(s.findall(".//x:f", NS) for s in libro.sheets.values()))
        partes = [r["D"] for r in libro.rows("Ciclo 1") if r.get("A") == "T1" and r.get("D")]
        self.assertEqual("".join(partes), texto)
        self.assertFalse(any("externalLinks" in path for path in libro.zip.namelist()))

    def test_limite_de_excel_no_entrega_archivo_parcial(self):
        self.client.force_login(self.ana)
        with patch("monitoreo.exportaciones.MAX_FILAS", 20):
            respuesta = self.descargar()
        self.assertEqual(respuesta.status_code, 422)
        self.assertContains(respuesta, "No se generó un archivo parcial", status_code=422)

    def test_consultas_no_crecen_por_cada_pez_o_registro(self):
        with self.assertNumQueries(7):
            exportar_unidad(self.piscina, self.ana)
