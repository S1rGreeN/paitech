from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from .models import ControlIntentoLogin, EventoSeguridad, TokenDispositivo


class SeguridadAutenticacionTests(TestCase):
    password = "ClaveSegura123!"

    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            email="ana@example.com",
            password=self.password,
            first_name="Ana",
        )
        self.api = APIClient()

    def login(self, *, dispositivo="telefono-prueba-001", password=None):
        return self.api.post(
            reverse("monitoreo:api_login"),
            {
                "email": self.usuario.email,
                "password": password or self.password,
                "dispositivo_id": dispositivo,
                "nombre_dispositivo": "Emulador Android",
            },
            format="json",
        )

    def test_token_se_guarda_como_hash_y_expira_en_treinta_dias(self):
        respuesta = self.login()

        self.assertEqual(respuesta.status_code, 200)
        token = TokenDispositivo.objects.get()
        self.assertNotIn(respuesta.data["token"], token.secreto_hash)
        self.assertEqual(len(token.secreto_hash), 64)
        diferencia = token.expira_en - timezone.now()
        self.assertGreater(diferencia, timedelta(days=29, hours=23))
        self.assertLessEqual(diferencia, timedelta(days=30))

    def test_varios_telefonos_conviven_y_logout_revoca_solo_el_actual(self):
        primero = self.login(dispositivo="telefono-prueba-001").data["token"]
        segundo = self.login(dispositivo="telefono-prueba-002").data["token"]
        self.assertEqual(TokenDispositivo.objects.count(), 2)

        cliente_primero = APIClient()
        cliente_primero.credentials(HTTP_AUTHORIZATION=f"Token {primero}")
        self.assertEqual(cliente_primero.post(reverse("monitoreo:api_logout")).status_code, 204)

        cliente_segundo = APIClient()
        cliente_segundo.credentials(HTTP_AUTHORIZATION=f"Token {segundo}")
        self.assertEqual(cliente_segundo.get(reverse("monitoreo:api_me")).status_code, 200)
        self.assertEqual(TokenDispositivo.objects.filter(revocado_en__isnull=False).count(), 1)

    def test_relogin_en_mismo_telefono_rota_el_secreto(self):
        anterior = self.login().data["token"]
        nuevo = self.login().data["token"]
        self.assertNotEqual(anterior, nuevo)
        self.assertEqual(TokenDispositivo.objects.count(), 1)

        cliente = APIClient()
        cliente.credentials(HTTP_AUTHORIZATION=f"Token {anterior}")
        self.assertEqual(cliente.get(reverse("monitoreo:api_me")).status_code, 401)
        cliente.credentials(HTTP_AUTHORIZATION=f"Token {nuevo}")
        self.assertEqual(cliente.get(reverse("monitoreo:api_me")).status_code, 200)

    def test_token_expirado_no_autentica(self):
        credencial = self.login().data["token"]
        TokenDispositivo.objects.update(expira_en=timezone.now() - timedelta(seconds=1))
        self.api.credentials(HTTP_AUTHORIZATION=f"Token {credencial}")
        self.assertEqual(self.api.get(reverse("monitoreo:api_me")).status_code, 401)

    def test_quinto_fallo_bloquea_y_el_mensaje_no_revela_si_existe_la_cuenta(self):
        mensajes = set()
        for numero in range(5):
            respuesta = self.login(password="Incorrecta-123!")
            mensajes.add(respuesta.data["detail"])
            self.assertEqual(respuesta.status_code, 429 if numero == 4 else 401)
        self.assertEqual(len(mensajes), 1)

        correcta_bloqueada = self.login()
        self.assertEqual(correcta_bloqueada.status_code, 429)
        control = ControlIntentoLogin.objects.get()
        self.assertGreater(control.bloqueado_hasta, timezone.now())
        self.assertEqual(control.bloqueos_acumulados, 1)

    def test_reincidencia_aplica_bloqueo_de_una_hora(self):
        for _ in range(5):
            self.login(password="Incorrecta-123!")
        ControlIntentoLogin.objects.update(
            bloqueado_hasta=timezone.now() - timedelta(seconds=1),
            ventana_iniciada_en=timezone.now() - timedelta(minutes=16),
        )

        for _ in range(5):
            respuesta = self.login(password="Incorrecta-123!")

        self.assertEqual(respuesta.status_code, 429)
        control = ControlIntentoLogin.objects.get()
        self.assertEqual(control.bloqueos_acumulados, 2)
        self.assertGreater(control.bloqueado_hasta, timezone.now() + timedelta(minutes=59))

    def test_perfil_inactivo_recibe_error_generico_y_no_token(self):
        self.usuario.perfil_acuicultor.activo = False
        self.usuario.perfil_acuicultor.save(update_fields=["activo"])

        respuesta = self.login()

        self.assertEqual(respuesta.status_code, 401)
        self.assertEqual(
            respuesta.data["detail"],
            "No fue posible iniciar sesión. Verifica los datos o intenta más tarde.",
        )
        self.assertEqual(TokenDispositivo.objects.count(), 0)

    def test_cambio_obligatorio_revoca_todas_las_sesiones(self):
        self.usuario.debe_cambiar_clave = True
        self.usuario.save(update_fields=["debe_cambiar_clave"])
        primera = self.login(dispositivo="telefono-prueba-001").data
        segunda = self.login(dispositivo="telefono-prueba-002").data
        self.assertTrue(primera["debe_cambiar_clave"])

        self.api.credentials(HTTP_AUTHORIZATION=f"Token {primera['token']}")
        self.assertEqual(self.api.get(reverse("monitoreo:api_me")).status_code, 403)
        respuesta = self.api.post(
            reverse("monitoreo:api_cambiar_clave"),
            {
                "password_actual": self.password,
                "password_nuevo": "NuevaClave#2026",
                "confirmacion": "NuevaClave#2026",
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, 204)
        self.usuario.refresh_from_db()
        self.assertFalse(self.usuario.debe_cambiar_clave)
        self.assertTrue(self.usuario.check_password("NuevaClave#2026"))
        self.assertEqual(TokenDispositivo.objects.filter(revocado_en__isnull=True).count(), 0)
        self.assertTrue(EventoSeguridad.objects.filter(tipo=EventoSeguridad.Tipo.CLAVE_CAMBIADA).exists())

        cliente = APIClient()
        cliente.credentials(HTTP_AUTHORIZATION=f"Token {segunda['token']}")
        self.assertEqual(cliente.get(reverse("monitoreo:api_me")).status_code, 401)

    def test_desactivar_cuenta_revoca_sesiones(self):
        self.login()
        self.usuario.is_active = False
        self.usuario.save(update_fields=["is_active"])
        self.assertEqual(TokenDispositivo.objects.filter(revocado_en__isnull=True).count(), 0)

    def test_politica_rechaza_menos_de_ocho_y_mas_de_treinta_y_dos(self):
        with self.assertRaises(ValidationError):
            validate_password("Aa1!xyz", user=self.usuario)
        with self.assertRaises(ValidationError):
            validate_password("Aa1!" + "x" * 29, user=self.usuario)


class CambioClaveWebTests(TestCase):
    def test_cuenta_temporal_es_redirigida_hasta_cambiar_clave(self):
        usuario = get_user_model().objects.create_user(
            email="temporal@example.com",
            password="Temporal#2026",
            debe_cambiar_clave=True,
        )
        respuesta = self.client.post(
            reverse("monitoreo:login"),
            {"username": usuario.email, "password": "Temporal#2026"},
        )
        self.assertRedirects(respuesta, reverse("monitoreo:cambiar_clave_inicial"))
        self.assertRedirects(
            self.client.get(reverse("monitoreo:dashboard")),
            reverse("monitoreo:cambiar_clave_inicial"),
        )

        cambiada = self.client.post(
            reverse("monitoreo:cambiar_clave_inicial"),
            {
                "old_password": "Temporal#2026",
                "new_password1": "Definitiva#2026",
                "new_password2": "Definitiva#2026",
            },
        )
        self.assertRedirects(cambiada, reverse("monitoreo:login"))
        usuario.refresh_from_db()
        self.assertFalse(usuario.debe_cambiar_clave)
        self.assertTrue(usuario.check_password("Definitiva#2026"))
