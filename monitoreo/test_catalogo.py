from io import StringIO
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase, override_settings

from monitoreo.models import Comunidad, Especie, JornadaRegistro, Piscina


class ProteccionSeedDemoTests(SimpleTestCase):
    @override_settings(DEBUG=False)
    def test_seed_demo_se_bloquea_fuera_de_debug(self):
        with self.assertRaisesMessage(CommandError, "DEBUG=False"):
            call_command("seed_demo", stdout=StringIO(), stderr=StringIO())

    @override_settings(DEBUG=True)
    def test_seed_demo_se_bloquea_sobre_postgresql(self):
        with patch.dict(
            settings.DATABASES["default"],
            {"ENGINE": "django.db.backends.postgresql"},
        ):
            with self.assertRaisesMessage(CommandError, "nunca sobre Neon/PostgreSQL"):
                call_command("seed_demo", stdout=StringIO(), stderr=StringIO())


class InicializacionCatalogoTests(TestCase):
    def ejecutar(self):
        salida = StringIO()
        call_command("inicializar_catalogo_paipayales", stdout=salida)
        return salida.getvalue()

    def test_crea_solo_catalogo_real_confirmado(self):
        salida = self.ejecutar()

        comunidad = Comunidad.objects.get(codigo="paipayales")
        especie = Especie.objects.get(nombre_comun="Vieja Azul")
        piscina = Piscina.objects.get(comunidad=comunidad, codigo="P-01")

        self.assertEqual(comunidad.nombre, "Paipayales")
        self.assertEqual(especie.nombre_cientifico, "Andinoacara rivulatus")
        self.assertEqual(piscina.nombre, "Piscina 1 Paipayales")
        self.assertEqual(piscina.tipo, Piscina.Tipo.PECES)
        self.assertEqual(piscina.especie, especie)
        self.assertIsNone(piscina.area_m2)
        self.assertEqual(piscina.descripcion, "")
        self.assertFalse(Piscina.objects.filter(codigo="LOM-01").exists())
        self.assertEqual(get_user_model().objects.count(), 0)
        self.assertEqual(JornadaRegistro.objects.count(), 0)
        self.assertIn("No se crearon usuarios, jornadas ni LOM-01", salida)

    def test_es_idempotente(self):
        self.ejecutar()
        self.ejecutar()

        self.assertEqual(Comunidad.objects.count(), 1)
        self.assertEqual(Especie.objects.count(), 1)
        self.assertEqual(Piscina.objects.count(), 1)
