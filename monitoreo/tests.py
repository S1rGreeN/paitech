import uuid
import os
from io import StringIO
from unittest.mock import patch
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from .models import (
    AuditoriaCambio,
    CicloProductivo,
    Comunidad,
    DispositivoSensor,
    Especie,
    JornadaRegistro,
    LecturaSensor,
    MedicionAgua,
    MovimientoPoblacion,
    Piscina,
)
from .management.commands.seed_demo import generar_clave_demo
from .semaforo import evaluar_agua
from .prediccion import calcular_prediccion
from .recordatorios import ATRASADO, TOLERANCIA, estado_agua
from .services import (
    calcular_poblacion_teorica,
    cerrar_ciclo,
    crear_ciclo,
    crear_jornada,
    crear_movimiento,
)


class BasePaiPayTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(email="ana@example.com", password="ClaveSegura123!", first_name="Ana")
        self.otro = User.objects.create_user(email="luis@example.com", password="ClaveSegura123!", first_name="Luis")
        self.comunidad = self.user.perfil_acuicultor.comunidad
        self.especie = Especie.objects.create(nombre_comun="Vieja Azul", nombre_cientifico="Andinoacara rivulatus")
        self.piscina = Piscina.objects.create(
            comunidad=self.comunidad,
            especie=self.especie,
            nombre="Piscina 1",
            codigo="P-01",
            tipo=Piscina.Tipo.PECES,
        )
        self.ciclo = CicloProductivo.objects.create(
            piscina=self.piscina,
            especie=self.especie,
            numero=1,
            iniciado_en=timezone.now() - timedelta(days=30),
            poblacion_inicial=200,
            autor_apertura=self.user.perfil_acuicultor,
        )
        self.api = APIClient()

    def autenticar(self, usuario=None):
        self.api.force_authenticate(user=usuario or self.user)

    def payload_jornada(self, **cambios):
        datos = {
            "id": str(uuid.uuid4()),
            "piscina": str(self.piscina.id),
            "capturada_en": timezone.now().isoformat(),
            "poblacion_estimada": 200,
            "observaciones": "Sin novedades",
            "dispositivo_id": "telefono-prueba",
            "agua": {"ph": "7.20", "nitrato": "10.000", "nitrito": "0.250", "amoniaco_total": "0.250"},
            "peces": [],
        }
        datos.update(cambios)
        return datos


class AutenticacionYWebTests(BasePaiPayTest):
    def test_clave_demo_es_breve_aleatoria_y_combina_tipos_de_caracter(self):
        clave = generar_clave_demo()

        self.assertEqual(len(clave), 10)
        self.assertTrue(any(caracter.islower() for caracter in clave))
        self.assertTrue(any(caracter.isupper() for caracter in clave))
        self.assertTrue(any(caracter.isdigit() for caracter in clave))
        self.assertTrue(any(caracter in "!@#%" for caracter in clave))

    def test_login_web_y_api_usan_correo(self):
        self.assertTrue(self.client.login(username="ana@example.com", password="ClaveSegura123!"))
        respuesta = self.api.post(
            reverse("monitoreo:api_login"),
            {
                "email": "ANA@example.com",
                "password": "ClaveSegura123!",
                "dispositivo_id": "telefono-prueba-001",
                "nombre_dispositivo": "Emulador",
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("token", respuesta.data)

    def test_login_web_no_publica_credenciales_demo(self):
        respuesta = self.client.get(reverse("monitoreo:login"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, "Acceso de demostración")
        self.assertNotContains(respuesta, "pH 7.20")
        self.assertContains(respuesta, "Datos reales tras iniciar sesión")
        self.assertContains(respuesta, "No compartas tu contraseña")

    def test_login_rechaza_cadena_de_inyeccion_como_correo(self):
        respuesta = self.api.post(
            reverse("monitoreo:api_login"),
            {"email": "' OR 1=1; DROP TABLE cuentas_usuario; --", "password": "x"},
            format="json",
        )

        self.assertEqual(respuesta.status_code, 400)
        self.assertNotIn("token", respuesta.data)
        self.assertEqual(get_user_model().objects.count(), 2)

    def test_dashboard_requiere_login_y_muestra_comunidad(self):
        respuesta = self.client.get(reverse("monitoreo:dashboard"))
        self.assertEqual(respuesta.status_code, 302)
        self.client.force_login(self.otro)
        respuesta = self.client.get(reverse("monitoreo:piscina_detalle", args=[self.piscina.id]))
        self.assertEqual(respuesta.status_code, 200)

    def test_dashboard_muestra_lombricultura_sin_crear_lom_01(self):
        self.client.force_login(self.user)

        respuesta = self.client.get(reverse("monitoreo:dashboard"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, ">Lombricultura</h3>", html=False, count=1)
        self.assertContains(respuesta, "Próximamente")
        self.assertContains(respuesta, "No crea una piscina ni almacena datos")
        self.assertFalse(Piscina.objects.filter(tipo=Piscina.Tipo.LOMBRICES).exists())
        self.assertContains(respuesta, "Solo piscinas reales habilitadas")

    def test_dashboard_no_expone_una_fila_antigua_de_lombricultura(self):
        Piscina.objects.create(
            comunidad=self.comunidad,
            nombre="Lecho demo que no debe mostrarse",
            codigo="LOM-01",
            tipo=Piscina.Tipo.LOMBRICES,
        )
        self.client.force_login(self.user)

        respuesta = self.client.get(reverse("monitoreo:dashboard"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, "Lecho demo que no debe mostrarse")
        self.assertNotContains(respuesta, "LOM-01")
        self.assertContains(respuesta, ">Lombricultura</h3>", html=False, count=1)

    def test_catalogo_api_no_entrega_lombricultura_a_android(self):
        Piscina.objects.create(
            comunidad=self.comunidad,
            nombre="Lecho demo que no debe sincronizarse",
            codigo="LOM-01",
            tipo=Piscina.Tipo.LOMBRICES,
        )
        self.autenticar()

        respuesta = self.api.get(reverse("monitoreo:api_piscinas"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual([item["codigo"] for item in respuesta.data], ["P-01"])

    def test_detalle_piscina_muestra_un_solo_acceso_a_nuevo_registro(self):
        self.client.force_login(self.user)

        respuesta = self.client.get(reverse("monitoreo:piscina_detalle", args=[self.piscina.id]))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Nuevo registro")
        self.assertNotContains(respuesta, "Agregar medición")
        self.assertContains(
            respuesta,
            reverse("monitoreo:registro_nuevo", args=[self.piscina.id]),
            count=1,
        )

    def test_web_crea_jornada_solo_agua(self):
        self.client.force_login(self.user)
        respuesta = self.client.post(
            reverse("monitoreo:registro_nuevo", args=[self.piscina.id]),
            {
                "capturada_en": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
                "poblacion_estimada": "200",
                "observaciones": "Solo agua",
                "registrar_agua": "on",
                "ph": "7.31",
                "nitrato": "12.375",
                "nitrito": "0.375",
                "amoniaco_total": "0.125",
                "muestras-TOTAL_FORMS": "0",
                "muestras-INITIAL_FORMS": "0",
                "muestras-MIN_NUM_FORMS": "0",
                "muestras-MAX_NUM_FORMS": "500",
            },
        )
        self.assertEqual(respuesta.status_code, 302)
        jornada = JornadaRegistro.objects.get()
        self.assertEqual(jornada.estado, JornadaRegistro.Estado.COMPLETA)
        self.assertEqual(jornada.agua.ph, Decimal("7.31"))
        self.assertEqual(jornada.agua.nitrato, Decimal("12.375"))
        self.assertEqual(jornada.agua.nitrito, Decimal("0.375"))
        self.assertEqual(jornada.agua.amoniaco_total, Decimal("0.125"))
        self.assertFalse(hasattr(jornada, "muestra_biometrica"))

    def test_web_muestra_agua_como_campos_numericos_editables(self):
        self.client.force_login(self.user)

        respuesta = self.client.get(
            reverse("monitoreo:registro_nuevo", args=[self.piscina.id])
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'name="ph"')
        self.assertContains(respuesta, 'type="number"')
        self.assertContains(respuesta, 'name="ph"', count=1)
        self.assertContains(respuesta, 'step="0.01"')
        self.assertContains(respuesta, 'step="0.001"', count=3)
        self.assertNotContains(respuesta, "Selecciona una lectura")


class JornadasApiTests(BasePaiPayTest):
    def test_acepta_agua_biometria_o_ambos_y_rechaza_jornada_vacia(self):
        self.autenticar()
        agua = self.api.post(reverse("monitoreo:api_jornadas"), self.payload_jornada(), format="json")
        self.assertEqual(agua.status_code, 201)
        biometria = self.api.post(
            reverse("monitoreo:api_jornadas"),
            self.payload_jornada(agua=None, peces=[{"peso_gramos": "250.40", "talla_centimetros": "21.30"}]),
            format="json",
        )
        self.assertEqual(biometria.status_code, 201)
        ambos = self.api.post(
            reverse("monitoreo:api_jornadas"),
            self.payload_jornada(peces=[{"peso_gramos": "260.00", "talla_centimetros": "22.00"}]),
            format="json",
        )
        self.assertEqual(ambos.status_code, 201)
        vacia = self.api.post(reverse("monitoreo:api_jornadas"), self.payload_jornada(agua=None, peces=[]), format="json")
        self.assertEqual(vacia.status_code, 400)

    def test_agua_acepta_decimales_manuales_y_conserva_limites(self):
        self.autenticar()
        manual = self.payload_jornada()
        manual["agua"] = {
            "ph": "7.31",
            "nitrato": "12.375",
            "nitrito": "0.375",
            "amoniaco_total": "0.125",
        }

        aceptada = self.api.post(
            reverse("monitoreo:api_jornadas"), manual, format="json"
        )

        self.assertEqual(aceptada.status_code, 201)
        self.assertEqual(aceptada.data["agua"]["ph"], "7.31")
        self.assertEqual(aceptada.data["agua"]["nitrato"], "12.375")

        fuera_de_rango = self.payload_jornada()
        fuera_de_rango["agua"]["ph"] = "14.01"
        rechazada = self.api.post(
            reverse("monitoreo:api_jornadas"), fuera_de_rango, format="json"
        )
        self.assertEqual(rechazada.status_code, 400)
        self.assertIn("ph", rechazada.data["agua"])

        contrato_antiguo = self.payload_jornada()
        contrato_antiguo["agua"]["amonio"] = contrato_antiguo["agua"].pop(
            "amoniaco_total"
        )
        clave_antigua = self.api.post(
            reverse("monitoreo:api_jornadas"), contrato_antiguo, format="json"
        )
        self.assertEqual(clave_antigua.status_code, 400)
        self.assertIn("amoniaco_total", clave_antigua.data["agua"])
        self.assertIn("amoniaco_total", aceptada.data["agua"])
        self.assertNotIn("amonio", aceptada.data["agua"])

    def test_observacion_sql_maliciosa_se_guarda_como_texto(self):
        self.autenticar()
        contenido = "'); DROP TABLE monitoreo_jornadaregistro; --"

        respuesta = self.api.post(
            reverse("monitoreo:api_jornadas"),
            self.payload_jornada(observaciones=contenido),
            format="json",
        )

        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(JornadaRegistro.objects.get().observaciones, contenido)
        self.assertEqual(self.api.get(reverse("monitoreo:api_jornadas")).status_code, 200)

    def test_api_limita_observaciones_excesivas(self):
        self.autenticar()
        respuesta = self.api.post(
            reverse("monitoreo:api_jornadas"),
            self.payload_jornada(observaciones="x" * 5001),
            format="json",
        )

        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(JornadaRegistro.objects.count(), 0)

    def test_uuid_hace_reintento_idempotente(self):
        self.autenticar()
        payload = self.payload_jornada()
        primera = self.api.post(reverse("monitoreo:api_jornadas"), payload, format="json")
        segunda = self.api.post(reverse("monitoreo:api_jornadas"), payload, format="json")
        self.assertEqual(primera.status_code, 201)
        self.assertEqual(segunda.status_code, 200)
        self.assertEqual(JornadaRegistro.objects.count(), 1)
        self.assertEqual(AuditoriaCambio.objects.count(), 1)

    def test_mismo_uuid_con_datos_distintos_devuelve_409(self):
        self.autenticar()
        payload = self.payload_jornada()
        primera = self.api.post(reverse("monitoreo:api_jornadas"), payload, format="json")
        payload["poblacion_estimada"] = 187
        conflicto = self.api.post(reverse("monitoreo:api_jornadas"), payload, format="json")

        self.assertEqual(primera.status_code, 201)
        self.assertEqual(conflicto.status_code, 409)
        self.assertEqual(JornadaRegistro.objects.get().poblacion_estimada, 200)
        self.assertEqual(AuditoriaCambio.objects.count(), 1)

    def test_correccion_incrementa_version_y_version_antigua_devuelve_409(self):
        self.autenticar()
        creada = self.api.post(reverse("monitoreo:api_jornadas"), self.payload_jornada(), format="json")
        jornada_id = creada.data["id"]
        payload = self.payload_jornada(id=jornada_id, version=1, poblacion_estimada=187, motivo_correccion="Conteo corregido")
        corregida = self.api.put(reverse("monitoreo:api_jornada_detalle", args=[jornada_id]), payload, format="json")
        self.assertEqual(corregida.status_code, 200)
        self.assertEqual(corregida.data["version"], 2)
        conflicto = self.api.put(reverse("monitoreo:api_jornada_detalle", args=[jornada_id]), payload, format="json")
        self.assertEqual(conflicto.status_code, 409)
        self.assertEqual(AuditoriaCambio.objects.filter(entidad_uuid=jornada_id).count(), 2)

    def test_otro_usuario_ve_historial_comunitario_pero_no_puede_modificarlo(self):
        jornada, _ = crear_jornada(
            actor=self.user,
            piscina=self.piscina,
            capturada_en=timezone.now(),
            poblacion_estimada=200,
            agua={"ph": Decimal("7.2"), "nitrato": Decimal("10"), "nitrito": Decimal("0.25"), "amoniaco_total": Decimal("0.25")},
        )
        self.autenticar(self.otro)
        lista = self.api.get(reverse("monitoreo:api_jornadas"))
        self.assertEqual(len(lista.data), 1)
        detalle = self.api.get(reverse("monitoreo:api_jornada_detalle", args=[jornada.id]))
        self.assertEqual(detalle.status_code, 200)
        payload = self.payload_jornada(id=str(jornada.id), version=1)
        correccion = self.api.put(
            reverse("monitoreo:api_jornada_detalle", args=[jornada.id]),
            payload,
            format="json",
        )
        self.assertEqual(correccion.status_code, 403)

    def test_anular_es_logico_y_auditado(self):
        self.autenticar()
        creada = self.api.post(reverse("monitoreo:api_jornadas"), self.payload_jornada(), format="json")
        respuesta = self.api.post(
            reverse("monitoreo:api_jornada_anular", args=[creada.data["id"]]),
            {"version": 1, "motivo": "Medición ingresada en la piscina equivocada"},
            format="json",
        )
        self.assertEqual(respuesta.status_code, 200)
        jornada = JornadaRegistro.objects.get(pk=creada.data["id"])
        self.assertEqual(jornada.estado, JornadaRegistro.Estado.ANULADA)
        self.assertTrue(JornadaRegistro.objects.filter(pk=jornada.id).exists())
        self.assertEqual(AuditoriaCambio.objects.filter(entidad_uuid=jornada.id).count(), 2)

    def test_edicion_antigua_de_jornada_anulada_devuelve_409(self):
        self.autenticar()
        payload = self.payload_jornada()
        creada = self.api.post(reverse("monitoreo:api_jornadas"), payload, format="json")
        jornada_id = creada.data["id"]
        self.api.post(
            reverse("monitoreo:api_jornada_anular", args=[jornada_id]),
            {"version": 1, "motivo": "Registro duplicado"},
            format="json",
        )
        payload.update({"version": 1, "poblacion_estimada": 187})

        conflicto = self.api.put(
            reverse("monitoreo:api_jornada_detalle", args=[jornada_id]),
            payload,
            format="json",
        )

        self.assertEqual(conflicto.status_code, 409)


class SemaforoYPoblacionTests(BasePaiPayTest):
    def test_semaforo_conserva_umbrales_sobre_las_lecturas_del_kit(self):
        base = {
            "ph": Decimal("7.2"),
            "nitrato": Decimal("10"),
            "nitrito": Decimal("0.25"),
            "amoniaco_total": Decimal("0.25"),
        }

        self.assertEqual(evaluar_agua(SimpleNamespace(**base))["estado"], "VERDE")
        nitrato_amarillo = {**base, "nitrato": Decimal("80")}
        self.assertEqual(
            evaluar_agua(SimpleNamespace(**nitrato_amarillo))["estado"], "AMARILLO"
        )
        nitrito_rojo = {**base, "nitrito": Decimal("2")}
        self.assertEqual(
            evaluar_agua(SimpleNamespace(**nitrito_rojo))["estado"], "ROJO"
        )
        nh3_estimado_rojo = {
            **base,
            "ph": Decimal("8.8"),
            "amoniaco_total": Decimal("0.25"),
        }
        self.assertEqual(
            evaluar_agua(SimpleNamespace(**nh3_estimado_rojo))["estado"], "ROJO"
        )

    def test_semaforo_usa_ultima_jornada_comunitaria_sin_importar_autor(self):
        crear_jornada(
            actor=self.otro,
            piscina=self.piscina,
            capturada_en=timezone.now(),
            poblacion_estimada=190,
            agua={"ph": Decimal("8.8"), "nitrato": Decimal("10"), "nitrito": Decimal("0.25"), "amoniaco_total": Decimal("8")},
        )
        self.autenticar(self.user)
        respuesta = self.api.get(reverse("monitoreo:api_semaforos"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data[0]["semaforo"]["estado"], "ROJO")
        self.assertEqual(respuesta.data[0]["jornada"]["autor"]["correo"], self.otro.email)

    def test_poblacion_teorica_aplica_movimientos_y_no_infiere_muertes(self):
        instante = timezone.now() - timedelta(days=2)
        crear_jornada(
            actor=self.user,
            piscina=self.piscina,
            capturada_en=instante,
            poblacion_estimada=200,
            agua={"ph": Decimal("7.2"), "nitrato": Decimal("10"), "nitrito": Decimal("0.25"), "amoniaco_total": Decimal("0.25")},
        )
        crear_movimiento(
            actor=self.user,
            tipo=MovimientoPoblacion.Tipo.MORTALIDAD,
            cantidad=13,
            ocurrido_en=instante + timedelta(days=1),
            piscina_origen=self.piscina,
        )
        self.assertEqual(calcular_poblacion_teorica(self.piscina), 187)
        self.assertEqual(MovimientoPoblacion.objects.count(), 1)

    def test_especie_de_piscina_no_puede_cambiar(self):
        otra = Especie.objects.create(nombre_comun="Tilapia")
        self.piscina.especie = otra
        with self.assertRaises(ValidationError):
            self.piscina.full_clean()


class MovimientosApiTests(BasePaiPayTest):
    def test_movimiento_se_puede_corregir_y_anular_sin_borrarlo(self):
        self.autenticar()
        movimiento_id = str(uuid.uuid4())
        base = {
            "id": movimiento_id,
            "tipo": "MORTALIDAD",
            "cantidad": 13,
            "piscina_origen": str(self.piscina.id),
            "piscina_destino": None,
            "ocurrido_en": timezone.now().isoformat(),
            "observaciones": "Conteo inicial",
        }
        creado = self.api.post(reverse("monitoreo:api_movimientos"), base, format="json")
        self.assertEqual(creado.status_code, 201)
        base.update({"version": 1, "cantidad": 12, "motivo_correccion": "Reconteo"})
        corregido = self.api.put(reverse("monitoreo:api_movimiento_detalle", args=[movimiento_id]), base, format="json")
        self.assertEqual(corregido.status_code, 200)
        self.assertEqual(corregido.data["version"], 2)
        anulado = self.api.post(
            reverse("monitoreo:api_movimiento_anular", args=[movimiento_id]),
            {"version": 2, "motivo": "Movimiento duplicado"},
            format="json",
        )
        self.assertEqual(anulado.status_code, 200)
        movimiento = MovimientoPoblacion.objects.get(pk=movimiento_id)
        self.assertEqual(movimiento.estado, MovimientoPoblacion.Estado.ANULADO)
        self.assertEqual(movimiento.version, 3)
        self.assertEqual(AuditoriaCambio.objects.filter(entidad_uuid=movimiento_id).count(), 3)

    def test_mismo_uuid_de_movimiento_con_datos_distintos_devuelve_409(self):
        self.autenticar()
        movimiento_id = str(uuid.uuid4())
        base = {
            "id": movimiento_id,
            "tipo": "MORTALIDAD",
            "cantidad": 13,
            "piscina_origen": str(self.piscina.id),
            "piscina_destino": None,
            "ocurrido_en": timezone.now().isoformat(),
            "observaciones": "Conteo inicial",
        }
        primera = self.api.post(reverse("monitoreo:api_movimientos"), base, format="json")
        base["cantidad"] = 12
        conflicto = self.api.post(reverse("monitoreo:api_movimientos"), base, format="json")

        self.assertEqual(primera.status_code, 201)
        self.assertEqual(conflicto.status_code, 409)
        self.assertEqual(MovimientoPoblacion.objects.get().cantidad, 13)

    def test_salud_no_requiere_token(self):
        respuesta = self.api.get(reverse("monitoreo:api_health"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data["database"], "ok")


class CiclosV15Tests(BasePaiPayTest):
    def test_api_impide_dos_ciclos_activos_en_la_misma_piscina(self):
        self.autenticar()
        respuesta = self.api.post(
            reverse("monitoreo:api_ciclos"),
            {
                "id": str(uuid.uuid4()),
                "piscina": str(self.piscina.id),
                "iniciado_en": timezone.now().isoformat(),
                "poblacion_inicial": 220,
            },
            format="json",
        )

        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(CicloProductivo.objects.filter(estado="ACTIVO").count(), 1)

    def test_cierre_es_idempotente_y_mortalidad_total_exige_cero(self):
        self.autenticar()
        url = reverse("monitoreo:api_ciclo_cerrar", args=[self.ciclo.id])
        cierre = {
            "version": 1,
            "cerrado_en": timezone.now().isoformat(),
            "destino_cierre": "VENTA",
            "poblacion_final": 187,
            "observaciones_cierre": "Fin ficticio de prueba",
        }
        primera = self.api.post(url, cierre, format="json")
        repetida = self.api.post(url, cierre, format="json")

        self.assertEqual(primera.status_code, 200)
        self.assertEqual(repetida.status_code, 200)
        self.assertEqual(CicloProductivo.objects.get().version, 2)
        self.assertEqual(
            AuditoriaCambio.objects.filter(entidad=AuditoriaCambio.Entidad.CICLO).count(),
            1,
        )

    def test_prediccion_usa_mediana_y_excluye_ciclo_con_ajuste(self):
        ahora = timezone.now()
        cerrar_ciclo(
            ciclo=self.ciclo,
            actor=self.user,
            version_esperada=1,
            cerrado_en=ahora - timedelta(days=1),
            destino_cierre=CicloProductivo.DestinoCierre.VENTA,
            poblacion_final=180,
        )
        ciclo_dos = CicloProductivo.objects.create(
            piscina=self.piscina,
            especie=self.especie,
            numero=2,
            estado=CicloProductivo.Estado.CERRADO,
            iniciado_en=ahora - timedelta(days=500),
            poblacion_inicial=200,
            autor_apertura=self.user.perfil_acuicultor,
            cerrado_en=ahora - timedelta(days=200),
            destino_cierre=CicloProductivo.DestinoCierre.VENTA,
            poblacion_final=160,
            autor_cierre=self.user.perfil_acuicultor,
        )
        CicloProductivo.objects.create(
            piscina=self.piscina,
            especie=self.especie,
            numero=3,
            estado=CicloProductivo.Estado.CERRADO,
            iniciado_en=ahora - timedelta(days=800),
            poblacion_inicial=200,
            autor_apertura=self.user.perfil_acuicultor,
            cerrado_en=ahora - timedelta(days=510),
            destino_cierre=CicloProductivo.DestinoCierre.VENTA,
            poblacion_final=190,
            autor_cierre=self.user.perfil_acuicultor,
        )

        tres = calcular_prediccion(self.piscina, 100)
        self.assertEqual(tres["prediccion_poblacion_final"], 90)
        self.assertEqual((tres["prediccion_min"], tres["prediccion_max"]), (80, 95))
        self.assertEqual(tres["prediccion_ciclos_usados"], 3)

        MovimientoPoblacion.objects.create(
            tipo=MovimientoPoblacion.Tipo.AJUSTE,
            cantidad=1,
            piscina_origen=self.piscina,
            ciclo_origen=ciclo_dos,
            autor=self.user.perfil_acuicultor,
            ocurrido_en=ciclo_dos.iniciado_en + timedelta(days=1),
        )
        dos = calcular_prediccion(self.piscina, 100)
        self.assertEqual(dos["prediccion_ciclos_usados"], 2)
        self.assertEqual(dos["prediccion_poblacion_final"], 93)
        self.assertEqual(dos["prediccion_confianza"], "MUY_BAJA")

    def test_recordatorio_semanal_tiene_tolerancia_lunes_martes_y_atraso_miercoles(self):
        zona = timezone.get_current_timezone()
        self.ciclo.iniciado_en = timezone.make_aware(datetime(2026, 8, 3, 10, 0), zona)
        self.ciclo.save(update_fields=["iniciado_en"])
        jornada = JornadaRegistro.objects.create(
            piscina=self.piscina,
            ciclo=self.ciclo,
            autor=self.user.perfil_acuicultor,
            capturada_en=timezone.make_aware(datetime(2026, 8, 4, 10, 0), zona),
            poblacion_estimada=200,
            estado=JornadaRegistro.Estado.COMPLETA,
        )
        MedicionAgua.objects.create(
            jornada=jornada,
            ph=Decimal("7.20"),
            nitrato=Decimal("10"),
            nitrito=Decimal("0.25"),
            amoniaco_total=Decimal("0.25"),
        )

        lunes = estado_agua(
            self.ciclo,
            ahora=timezone.make_aware(datetime(2026, 8, 17, 9, 0), zona),
        )
        miercoles = estado_agua(
            self.ciclo,
            ahora=timezone.make_aware(datetime(2026, 8, 19, 0, 0), zona),
        )
        self.assertEqual(lunes["estado"], TOLERANCIA)
        self.assertEqual(miercoles["estado"], ATRASADO)

    def test_telemetria_esta_deshabilitada_y_lectura_parcial_es_valida(self):
        respuesta = self.api.post(
            reverse("monitoreo:api_sensor_lecturas_lote"), {"lecturas": []}, format="json"
        )
        self.assertEqual(respuesta.status_code, 404)
        dispositivo = DispositivoSensor.objects.create(
            piscina=self.piscina,
            codigo="SENSOR-FICTICIO-01",
            nombre="Sensor ficticio",
        )
        lectura = LecturaSensor(
            dispositivo=dispositivo,
            piscina=self.piscina,
            ciclo=self.ciclo,
            medida_en=timezone.now(),
            temperatura_c=Decimal("25.100"),
            calidad=LecturaSensor.Calidad.PARCIAL,
        )
        lectura.full_clean()

    @override_settings(SENSORES_HABILITADOS=True)
    def test_sensor_ficticio_autentica_y_reintenta_lote_sin_duplicar(self):
        dispositivo = DispositivoSensor.objects.create(
            piscina=self.piscina,
            codigo="SENSOR-FICTICIO-IDEMPOTENCIA",
            nombre="Sensor ficticio de prueba",
            activo=True,
        )
        credencial = dispositivo.emitir_credencial()
        self.api.credentials(HTTP_AUTHORIZATION=f"Sensor {credencial}")
        lectura_id = str(uuid.uuid4())
        lote = {
            "lecturas": [
                {
                    "id": lectura_id,
                    "medida_en": timezone.now().isoformat(),
                    "temperatura_c": "25.100",
                }
            ]
        }

        primera = self.api.post(
            reverse("monitoreo:api_sensor_lecturas_lote"), lote, format="json"
        )
        repetida = self.api.post(
            reverse("monitoreo:api_sensor_lecturas_lote"), lote, format="json"
        )

        self.assertEqual(primera.status_code, 200)
        self.assertEqual(primera.data, {"creadas": 1, "repetidas": 0})
        self.assertEqual(repetida.status_code, 200)
        self.assertEqual(repetida.data, {"creadas": 0, "repetidas": 1})
        lectura = LecturaSensor.objects.get(pk=lectura_id)
        self.assertEqual(lectura.piscina, self.piscina)
        self.assertEqual(lectura.ciclo, self.ciclo)
        self.assertEqual(lectura.calidad, LecturaSensor.Calidad.PARCIAL)

    def test_respuesta_400_incluye_identificador_sin_exponer_payload(self):
        self.autenticar()
        respuesta = self.api.post(
            reverse("monitoreo:api_jornadas"),
            self.payload_jornada(agua=None, peces=[]),
            format="json",
        )
        self.assertEqual(respuesta.status_code, 400)
        self.assertRegex(respuesta["X-Request-ID"], r"^[a-f0-9]{32}$")

    @override_settings(DEBUG=True)
    def test_limpieza_desarrollo_conserva_identidad_y_catalogos(self):
        salida = StringIO()
        call_command(
            "limpiar_datos_operativos_desarrollo",
            "--ejecutar",
            "--confirmar",
            "BORRAR-DATOS-DESARROLLO",
            stdout=salida,
        )

        self.assertEqual(CicloProductivo.objects.count(), 0)
        self.assertTrue(get_user_model().objects.filter(pk=self.user.pk).exists())
        self.assertTrue(Piscina.objects.filter(pk=self.piscina.pk).exists())
        self.assertIn("Se conservaron usuarios", salida.getvalue())

    @override_settings(DEBUG=False)
    def test_limpieza_se_rechaza_fuera_de_desarrollo(self):
        entorno = {
            clave: valor
            for clave, valor in os.environ.items()
            if clave not in {"RAILWAY_ENVIRONMENT_NAME", "PAIPAY_ENVIRONMENT"}
        }
        with patch.dict(os.environ, entorno, clear=True):
            with self.assertRaises(CommandError):
                call_command(
                    "limpiar_datos_operativos_desarrollo",
                    "--ejecutar",
                    "--confirmar",
                    "BORRAR-DATOS-DESARROLLO",
                )
