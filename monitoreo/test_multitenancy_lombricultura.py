import uuid
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.contrib.admin.sites import AdminSite
from django.test import TestCase
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from .models import (
    AuditoriaCambio,
    CamaLombrices,
    CicloLombricultura,
    Comunidad,
    Especie,
    MovimientoPoblacion,
    Piscina,
    RegistroLombricultura,
)
from .semaforo import evaluar_agua
from .admin import ComunidadAdmin, EspecieAdmin, MovimientoPoblacionAdmin


class BaseComunidadesTest(TestCase):
    def setUp(self):
        Usuario = get_user_model()
        self.paipayales = Comunidad.objects.get(codigo="paipayales")
        self.galo = Comunidad.objects.get(codigo="colegio-galo-plaza-lasso")
        self.piscina_paipayales = Piscina.objects.get(
            comunidad=self.paipayales, codigo="P-01"
        )
        self.piscina_galo = Piscina.objects.get(comunidad=self.galo, codigo="P-01")
        self.cama = CamaLombrices.objects.get(
            comunidad=self.paipayales, codigo="C-01"
        )
        self.acuicultor = Usuario.objects.create_user(
            email="acuicultor.paipayales@example.com", password="ClaveSegura123!"
        )
        self.otro_paipayales = Usuario.objects.create_user(
            email="otro.paipayales@example.com", password="ClaveSegura123!"
        )
        self.acuicultor_galo = Usuario.objects.create_user(
            email="acuicultor.galo@example.com", password="ClaveSegura123!"
        )
        perfil_galo = self.acuicultor_galo.perfil_acuicultor
        perfil_galo.comunidad = self.galo
        perfil_galo.nickname = "Acuicultor Galo"
        perfil_galo.save(update_fields=["comunidad", "nickname"])
        self.api = APIClient()


class AislamientoComunidadesTests(BaseComunidadesTest):
    def test_login_y_me_exponen_uuid_publico_no_pk_interno(self):
        respuesta = self.api.post(
            reverse("monitoreo:api_login"),
            {
                "email": self.acuicultor.email,
                "password": "ClaveSegura123!",
                "dispositivo_id": "telefono-paipayales-001",
            },
            format="json",
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            respuesta.data["usuario"]["comunidad"]["id_publico"],
            str(self.paipayales.id_publico),
        )
        self.assertNotIn("id", respuesta.data["usuario"]["comunidad"])

    def test_catalogos_ordinarios_solo_muestran_la_comunidad_actual(self):
        self.api.force_authenticate(self.acuicultor)

        piscinas = self.api.get(reverse("monitoreo:api_piscinas"))
        camas = self.api.get(reverse("monitoreo:api_camas"))
        especies = self.api.get(reverse("monitoreo:api_especies"))

        self.assertEqual([dato["id"] for dato in piscinas.data], [str(self.piscina_paipayales.id)])
        self.assertEqual([dato["id"] for dato in camas.data], [str(self.cama.id)])
        self.assertEqual([dato["nombre_comun"] for dato in especies.data], ["Vieja Azul"])

        self.api.force_authenticate(self.acuicultor_galo)
        piscinas = self.api.get(reverse("monitoreo:api_piscinas"))
        camas = self.api.get(reverse("monitoreo:api_camas"))
        especies = self.api.get(reverse("monitoreo:api_especies"))

        self.assertEqual([dato["id"] for dato in piscinas.data], [str(self.piscina_galo.id)])
        self.assertEqual(camas.data, [])
        self.assertEqual([dato["nombre_comun"] for dato in especies.data], ["Tilapia"])

    def test_acceso_directo_web_y_api_cruzado_responde_404(self):
        self.client.force_login(self.acuicultor)
        web = self.client.get(
            reverse("monitoreo:piscina_detalle", args=[self.piscina_galo.id])
        )
        self.assertEqual(web.status_code, 404)

        self.api.force_authenticate(self.acuicultor_galo)
        self.client.force_login(self.acuicultor_galo)
        cama_web = self.client.get(reverse("monitoreo:cama_detalle", args=[self.cama.id]))
        apertura = self.api.post(
            reverse("monitoreo:api_ciclos_lombricultura"),
            {
                "id": str(uuid.uuid4()),
                "cama": str(self.cama.id),
                "iniciado_en": timezone.now().isoformat(),
                "conteo_inicial": 100,
            },
            format="json",
        )

        self.assertEqual(cama_web.status_code, 404)
        self.assertEqual(apertura.status_code, 404)
        self.assertFalse(CicloLombricultura.objects.exists())

    def test_dashboard_de_galo_no_filtra_paipayales(self):
        self.client.force_login(self.acuicultor_galo)

        respuesta = self.client.get(reverse("monitoreo:dashboard"))

        self.assertContains(respuesta, "Piscina 1 Colegio Galo Plaza Lasso")
        self.assertNotContains(respuesta, "Piscina 1 Paipayales")
        self.assertNotContains(respuesta, "Cama 1 Paipayales")

    def test_admin_funcional_limita_catalogos_y_relaciones_a_su_comunidad(self):
        solicitud = RequestFactory().get("/admin/monitoreo/piscina/")
        solicitud.user = self.acuicultor

        comunidades = ComunidadAdmin(Comunidad, AdminSite()).get_queryset(solicitud)
        especies = EspecieAdmin(Especie, AdminSite()).get_queryset(solicitud)
        movimientos = MovimientoPoblacionAdmin(
            MovimientoPoblacion, AdminSite()
        )
        campo_origen = movimientos.formfield_for_foreignkey(
            movimientos.model._meta.get_field("piscina_origen"), solicitud
        )

        self.assertEqual(list(comunidades), [self.paipayales])
        self.assertEqual([item.nombre_comun for item in especies], ["Vieja Azul"])
        self.assertEqual(list(campo_origen.queryset), [self.piscina_paipayales])


class LombriculturaApiTests(BaseComunidadesTest):
    def setUp(self):
        super().setUp()
        self.api.force_authenticate(self.acuicultor)
        self.inicio = timezone.now().replace(second=0, microsecond=0)

    def abrir_ciclo(self, *, ciclo_id=None, conteo=120):
        return self.api.post(
            reverse("monitoreo:api_ciclos_lombricultura"),
            {
                "id": str(ciclo_id or uuid.uuid4()),
                "cama": str(self.cama.id),
                "iniciado_en": self.inicio.isoformat(),
                "conteo_inicial": conteo,
                "observaciones_apertura": "Inicio de prueba",
                "dispositivo_id": "emulador-001",
            },
            format="json",
        )

    def test_ciclo_y_registro_admiten_conteos_reales_que_aumentan(self):
        ciclo_id = uuid.uuid4()
        apertura = self.abrir_ciclo(ciclo_id=ciclo_id, conteo=120)
        reintento = self.abrir_ciclo(ciclo_id=ciclo_id, conteo=120)
        registro_id = uuid.uuid4()
        registro = self.api.post(
            reverse("monitoreo:api_registros_lombricultura"),
            {
                "id": str(registro_id),
                "cama": str(self.cama.id),
                "ciclo": str(ciclo_id),
                "capturada_en": self.inicio.isoformat(),
                "ph_suelo": "7.35",
                "conteo_lombrices": 180,
                "observaciones": "Se reprodujeron",
                "dispositivo_id": "emulador-001",
            },
            format="json",
        )
        cierre = self.api.post(
            reverse("monitoreo:api_ciclo_lombricultura_cerrar", args=[ciclo_id]),
            {
                "version": 1,
                "cerrado_en": (self.inicio + timedelta(days=30)).isoformat(),
                "conteo_final": 275,
                "observaciones_cierre": "Conteo verdadero al cierre",
            },
            format="json",
        )

        self.assertEqual(apertura.status_code, 201)
        self.assertEqual(reintento.status_code, 200)
        self.assertEqual(registro.status_code, 201)
        self.assertEqual(registro.data["ph_suelo"], "7.35")
        self.assertEqual(registro.data["conteo_lombrices"], 180)
        self.assertEqual(cierre.status_code, 200)
        self.assertEqual(cierre.data["conteo_final"], 275)
        self.assertEqual(cierre.data["estado"], CicloLombricultura.Estado.CERRADO)
        self.assertTrue(
            AuditoriaCambio.objects.filter(
                comunidad=self.paipayales,
                entidad=AuditoriaCambio.Entidad.REGISTRO_LOMBRIZ,
                entidad_uuid=registro_id,
            ).exists()
        )

    def test_ph_suelo_se_valida_entre_cero_y_catorce_con_dos_decimales(self):
        ciclo = self.abrir_ciclo()
        respuesta = self.api.post(
            reverse("monitoreo:api_registros_lombricultura"),
            {
                "cama": str(self.cama.id),
                "ciclo": ciclo.data["id"],
                "capturada_en": self.inicio.isoformat(),
                "ph_suelo": "14.01",
                "conteo_lombrices": 0,
            },
            format="json",
        )

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("ph_suelo", respuesta.data)
        self.assertFalse(RegistroLombricultura.objects.exists())

    def test_version_obsoleta_devuelve_409_y_otro_autor_no_puede_corregir(self):
        ciclo = self.abrir_ciclo()
        creado = self.api.post(
            reverse("monitoreo:api_registros_lombricultura"),
            {
                "cama": str(self.cama.id),
                "ciclo": ciclo.data["id"],
                "capturada_en": self.inicio.isoformat(),
                "ph_suelo": "6.50",
                "conteo_lombrices": 90,
            },
            format="json",
        )
        url = reverse("monitoreo:api_registro_lombricultura_detalle", args=[creado.data["id"]])
        correccion = {
            "cama": str(self.cama.id),
            "ciclo": ciclo.data["id"],
            "capturada_en": self.inicio.isoformat(),
            "ph_suelo": "6.75",
            "conteo_lombrices": 95,
            "version": 1,
            "motivo_correccion": "Corrección de lectura",
        }

        primera = self.api.put(url, correccion, format="json")
        obsoleta = self.api.put(url, correccion, format="json")
        self.api.force_authenticate(self.otro_paipayales)
        ajena = self.api.put(
            url, {**correccion, "version": 2, "ph_suelo": "7.00"}, format="json"
        )

        self.assertEqual(primera.status_code, 200)
        self.assertEqual(primera.data["version"], 2)
        self.assertEqual(obsoleta.status_code, 409)
        self.assertEqual(ajena.status_code, 403)

    def test_uuid_idempotente_no_puede_reutilizarse_desde_otro_autor(self):
        ciclo_id = uuid.uuid4()
        apertura = self.abrir_ciclo(ciclo_id=ciclo_id)
        registro_id = uuid.uuid4()
        cuerpo = {
            "id": str(registro_id),
            "cama": str(self.cama.id),
            "ciclo": str(ciclo_id),
            "capturada_en": self.inicio.isoformat(),
            "ph_suelo": "7.00",
            "conteo_lombrices": 120,
            "dispositivo_id": "emulador-001",
        }
        creado = self.api.post(
            reverse("monitoreo:api_registros_lombricultura"), cuerpo, format="json"
        )
        self.api.force_authenticate(self.otro_paipayales)

        ciclo_ajeno = self.api.post(
            reverse("monitoreo:api_ciclos_lombricultura"),
            {
                "id": str(ciclo_id),
                "cama": str(self.cama.id),
                "iniciado_en": self.inicio.isoformat(),
                "conteo_inicial": 120,
                "observaciones_apertura": "Inicio de prueba",
                "dispositivo_id": "emulador-001",
            },
            format="json",
        )
        registro_ajeno = self.api.post(
            reverse("monitoreo:api_registros_lombricultura"), cuerpo, format="json"
        )

        self.assertEqual(apertura.status_code, 201)
        self.assertEqual(creado.status_code, 201)
        self.assertEqual(ciclo_ajeno.status_code, 403)
        self.assertEqual(registro_ajeno.status_code, 403)


class PerfilesSemaforoTests(BaseComunidadesTest):
    def test_tilapia_usa_perfil_provisional_por_especie(self):
        tilapia = Especie.objects.get(nombre_comun="Tilapia")
        agua = SimpleNamespace(
            ph=Decimal("7.00"),
            nitrato=Decimal("10.000"),
            nitrito=Decimal("0.310"),
            amoniaco_total=Decimal("0.050"),
        )

        resultado = evaluar_agua(agua, especie=tilapia)

        self.assertEqual(resultado["especie"], "Tilapia")
        self.assertEqual(resultado["perfil_version"], "tilapia-nilo-provisional-2026.1")
        self.assertTrue(resultado["umbrales_provisionales"])
        self.assertEqual(resultado["estado"], "AMARILLO")
