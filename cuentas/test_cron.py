from datetime import timedelta

from django.contrib.sessions.models import Session
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from cuentas.models import ControlIntentoLogin, EventoSeguridad


@override_settings(CRON_SECRET="secreto-exclusivo-para-pruebas")
class MantenimientoCronTests(TestCase):
    def setUp(self):
        self.url = reverse("cron_mantenimiento")
        self.antiguo = EventoSeguridad.objects.create(tipo=EventoSeguridad.Tipo.LOGIN_FALLIDO)
        self.reciente = EventoSeguridad.objects.create(tipo=EventoSeguridad.Tipo.LOGIN_EXITOSO)
        pasado = timezone.now() - timedelta(days=31)
        EventoSeguridad.objects.filter(pk=self.antiguo.pk).update(creado_en=pasado)
        self.control_antiguo = ControlIntentoLogin.objects.create(
            email_normalizado="antiguo@example.com", direccion_ip="127.0.0.1"
        )
        ControlIntentoLogin.objects.filter(pk=self.control_antiguo.pk).update(ultimo_intento_en=pasado)
        self.control_reciente = ControlIntentoLogin.objects.create(
            email_normalizado="reciente@example.com", direccion_ip="127.0.0.1"
        )
        Session.objects.create(session_key="vencida", session_data="", expire_date=pasado)
        Session.objects.create(
            session_key="vigente", session_data="", expire_date=timezone.now() + timedelta(days=1)
        )

    def test_rechaza_peticion_sin_secreto_o_con_credencial_incorrecta(self):
        for authorization in ("", "Bearer incorrecto", "Token secreto-exclusivo-para-pruebas"):
            with self.subTest(authorization=authorization):
                response = self.client.get(self.url, HTTP_AUTHORIZATION=authorization)
                self.assertEqual(response.status_code, 401)
                self.assertIn("no-store", response["Cache-Control"])
                self.assertEqual(EventoSeguridad.objects.count(), 2)
                self.assertEqual(Session.objects.count(), 2)

    @override_settings(CRON_SECRET="")
    def test_sin_configuracion_no_permite_ejecutar_la_limpieza(self):
        response = self.client.get(self.url, HTTP_AUTHORIZATION="Bearer ")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(EventoSeguridad.objects.count(), 2)

    def test_limpia_solo_datos_vencidos_y_permite_reintentos(self):
        for _ in range(2):
            response = self.client.get(
                self.url, HTTP_AUTHORIZATION="Bearer secreto-exclusivo-para-pruebas"
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"status": "ok"})
            self.assertIn("no-store", response["Cache-Control"])
        self.assertQuerySetEqual(EventoSeguridad.objects.values_list("pk", flat=True), [self.reciente.pk])
        self.assertQuerySetEqual(
            ControlIntentoLogin.objects.values_list("pk", flat=True), [self.control_reciente.pk]
        )
        self.assertQuerySetEqual(Session.objects.values_list("session_key", flat=True), ["vigente"])

    def test_no_modifica_datos_con_head_o_post(self):
        for method in (self.client.head, self.client.post):
            response = method(self.url, HTTP_AUTHORIZATION="Bearer secreto-exclusivo-para-pruebas")
            self.assertEqual(response.status_code, 405)
        self.assertEqual(EventoSeguridad.objects.count(), 2)
