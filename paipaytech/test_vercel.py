import json
import os
from pathlib import Path
import subprocess
import sys

from django.test import SimpleTestCase


class ConfiguracionVercelTests(SimpleTestCase):
    """Carga settings en procesos aislados; nunca abre la base real ni lee .env."""

    def cargar(self, **changes):
        keys = {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "HOME", "USERPROFILE"}
        env = {key: value for key, value in os.environ.items() if key.upper() in keys}
        env.update(
            PYTHON_DOTENV_DISABLED="1",
            PYTHONIOENCODING="utf-8",
            VERCEL="1",
            SECRET_KEY="clave-solo-para-pruebas-de-configuracion",
            ALLOWED_HOSTS="paipay.example.com",
            DATABASE_URL="postgresql://test:test@127.0.0.1:1/test?sslmode=require",
            VERCEL_URL="paipay-prueba.vercel.app",
            VERCEL_PROJECT_PRODUCTION_URL="paipay.vercel.app",
        )
        for key, value in changes.items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        return subprocess.run(
            [sys.executable, "-c", """
import json
from unittest.mock import patch
from django.db.backends.base.base import BaseDatabaseWrapper
with patch.object(BaseDatabaseWrapper, 'connect', side_effect=AssertionError('No conectar en el arranque')):
    from paipaytech.wsgi import application
    from django.conf import settings
    db = settings.DATABASES['default']
    print(json.dumps({
        'debug': settings.DEBUG,
        'hosts': settings.ALLOWED_HOSTS,
        'origins': settings.CSRF_TRUSTED_ORIGINS,
        'engine': db['ENGINE'],
        'conn_max_age': db['CONN_MAX_AGE'],
        'cursors_disabled': db['DISABLE_SERVER_SIDE_CURSORS'],
        'sslmode': db['OPTIONS']['sslmode'],
        'static_backend': settings.STORAGES['staticfiles']['BACKEND'],
        'secure_cookies': settings.SESSION_COOKIE_SECURE and settings.CSRF_COOKIE_SECURE,
    }))
"""],
            cwd=Path(__file__).resolve().parent.parent,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )

    def test_arranca_sin_conectar_y_configura_neon_dominios_y_estaticos(self):
        result = self.cargar()
        self.assertEqual(result.returncode, 0, result.stderr)
        config = json.loads(result.stdout)
        self.assertFalse(config["debug"])
        self.assertTrue(config["secure_cookies"])
        self.assertEqual(config["engine"], "django.db.backends.postgresql")
        self.assertEqual(config["conn_max_age"], 0)
        self.assertTrue(config["cursors_disabled"])
        self.assertEqual(config["sslmode"], "require")
        self.assertIn("paipay.example.com", config["hosts"])
        self.assertIn("paipay-prueba.vercel.app", config["hosts"])
        self.assertIn("https://paipay-prueba.vercel.app", config["origins"])
        self.assertNotIn(".vercel.app", config["hosts"])
        self.assertEqual(config["static_backend"], "whitenoise.storage.CompressedManifestStaticFilesStorage")

    def test_no_acepta_sqlite_ni_configuracion_incompleta_en_vercel(self):
        for changes, expected in (
            ({"DATABASE_URL": ""}, "DATABASE_URL"),
            ({"DATABASE_URL": "sqlite:///:memory:"}, "PostgreSQL"),
            ({"SECRET_KEY": None}, "SECRET_KEY"),
            ({"ALLOWED_HOSTS": None, "VERCEL_URL": None, "VERCEL_PROJECT_PRODUCTION_URL": None}, "ALLOWED_HOSTS"),
            ({"ALLOWED_HOSTS": "*"}, "ALLOWED_HOSTS"),
            ({"ALLOWED_HOSTS": ".vercel.app"}, "ALLOWED_HOSTS"),
            ({"DEBUG": "True"}, "DEBUG=False"),
        ):
            with self.subTest(changes=changes):
                result = self.cargar(**changes)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stderr)

    def test_vercel_solo_necesita_los_secretos_y_los_dominios_del_sistema(self):
        result = self.cargar(ALLOWED_HOSTS=None)
        self.assertEqual(result.returncode, 0, result.stderr)
        config = json.loads(result.stdout)
        self.assertEqual(config["hosts"], ["paipay-prueba.vercel.app", "paipay.vercel.app"])
        self.assertIn("https://paipay.vercel.app", config["origins"])
        self.assertFalse(config["debug"])

    def test_conserva_el_dominio_y_origen_personalizados(self):
        result = self.cargar(CSRF_TRUSTED_ORIGINS="https://paipay.example.com")
        self.assertEqual(result.returncode, 0, result.stderr)
        config = json.loads(result.stdout)
        self.assertIn("https://paipay.example.com", config["origins"])
        self.assertIn("https://paipay.vercel.app", config["origins"])
