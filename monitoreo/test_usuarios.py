from io import StringIO
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import RequestFactory, TestCase

from cuentas.admin import UsuarioAdmin
from monitoreo.admin import AcuicultorAdmin
from monitoreo.models import Acuicultor
from monitoreo.permisos import GRUPO_ADMINISTRADORES_FUNCIONALES


class CreacionUsuariosOperativosTests(TestCase):
    def crear(self, *, rol, email, nombres, apellidos, nickname, clave="Trucha#2026Azul"):
        salida = StringIO()
        with (
            patch("builtins.input", side_effect=[email, nombres, apellidos, nickname]),
            patch(
                "monitoreo.management.commands.crear_usuario_operativo.getpass",
                side_effect=[clave, clave],
            ),
        ):
            call_command(
                "crear_usuario_operativo",
                rol=rol,
                comunidad="paipayales",
                stdout=salida,
            )
        return get_user_model().objects.get(email=email), salida.getvalue()

    def test_crea_superusuario_tecnico(self):
        usuario, salida = self.crear(
            rol="tecnico",
            email="tecnico@example.com",
            nombres="Soporte",
            apellidos="Técnico",
            nickname="Soporte técnico",
        )

        self.assertTrue(usuario.is_staff)
        self.assertTrue(usuario.is_superuser)
        self.assertTrue(usuario.debe_cambiar_clave)
        self.assertEqual(usuario.perfil_acuicultor.rol, Acuicultor.Rol.TECNICO)
        self.assertNotIn("Trucha#2026Azul", salida)

    def test_administrador_es_staff_limitado_por_grupo(self):
        usuario, _ = self.crear(
            rol="administrador",
            email="administrador@example.com",
            nombres="Administración",
            apellidos="Paipayales",
            nickname="Administración",
        )

        self.assertTrue(usuario.is_staff)
        self.assertFalse(usuario.is_superuser)
        self.assertTrue(usuario.debe_cambiar_clave)
        self.assertEqual(usuario.perfil_acuicultor.rol, Acuicultor.Rol.ADMINISTRADOR)
        self.assertTrue(usuario.groups.filter(name=GRUPO_ADMINISTRADORES_FUNCIONALES).exists())
        self.assertTrue(usuario.has_perm("cuentas.add_usuario"))
        self.assertTrue(usuario.has_perm("monitoreo.change_piscina"))
        self.assertFalse(usuario.has_perm("monitoreo.change_especie"))
        self.assertTrue(usuario.has_perm("monitoreo.view_auditoriacambio"))
        self.assertFalse(usuario.has_perm("auth.change_group"))
        self.assertFalse(usuario.has_perm("monitoreo.delete_piscina"))
        self.assertFalse(usuario.has_perm("monitoreo.change_jornadaregistro"))

    def test_acuicultor_no_entra_al_admin(self):
        usuario, _ = self.crear(
            rol="acuicultor",
            email="acuicultor@example.com",
            nombres="Acuicultor",
            apellidos="Uno",
            nickname="Acuicultor uno",
        )

        self.assertFalse(usuario.is_staff)
        self.assertFalse(usuario.is_superuser)
        self.assertTrue(usuario.debe_cambiar_clave)
        self.assertEqual(usuario.perfil_acuicultor.rol, Acuicultor.Rol.ACUICULTOR)
        self.assertFalse(usuario.groups.exists())


class RestriccionesAdminFuncionalTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.tecnico = User.objects.create_superuser(
            email="tecnico@example.com",
            password="Trucha#2026Azul",
        )
        self.funcional = User.objects.create_user(
            email="funcional@example.com",
            password="Trucha#2026Azul",
            is_staff=True,
        )
        self.ordinario = User.objects.create_user(
            email="ordinario@example.com",
            password="Trucha#2026Azul",
        )
        self.solicitud = RequestFactory().get("/admin/cuentas/usuario/")
        self.solicitud.user = self.funcional

    def test_no_puede_ver_ni_modificar_cuentas_privilegiadas(self):
        administracion = UsuarioAdmin(get_user_model(), AdminSite())

        consulta = administracion.get_queryset(self.solicitud)

        self.assertIn(self.ordinario, consulta)
        self.assertNotIn(self.tecnico, consulta)
        self.assertNotIn(self.funcional, consulta)
        self.assertFalse(administracion.has_change_permission(self.solicitud, self.tecnico))
        self.assertFalse(administracion.has_delete_permission(self.solicitud, self.ordinario))
        campos = str(administracion.get_fieldsets(self.solicitud, self.ordinario))
        self.assertNotIn("is_superuser", campos)
        self.assertNotIn("groups", campos)
        self.assertNotIn("user_permissions", campos)

    def test_no_puede_cambiar_rol_ni_comunidad_desde_perfiles(self):
        administracion = AcuicultorAdmin(Acuicultor, AdminSite())

        solo_lectura = administracion.get_readonly_fields(
            self.solicitud,
            self.ordinario.perfil_acuicultor,
        )

        self.assertEqual(solo_lectura, ("user", "comunidad", "rol"))
        self.assertFalse(
            administracion.has_delete_permission(
                self.solicitud,
                self.ordinario.perfil_acuicultor,
            )
        )
