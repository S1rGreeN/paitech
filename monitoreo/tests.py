from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import MuestraPez, Piscina, Registro


class PaiPayTechTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="tester",
            email="tester@example.com",
            password="ClaveSegura123!",
        )
        self.piscina = Piscina.objects.create(
            nombre="Piscina de prueba",
            codigo="TEST-01",
            tipo=Piscina.Tipo.PECES,
        )

    def test_usuario_recibe_perfil_y_acceso_a_piscina(self):
        self.assertEqual(self.user.perfil_acuicultor.nickname, "tester")
        self.assertTrue(self.piscina.acuicultores.filter(pk=self.user.perfil_acuicultor.pk).exists())

    def test_dashboard_requiere_inicio_de_sesion(self):
        response = self.client.get(reverse("monitoreo:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("monitoreo:login"), response.url)


    def test_paginas_principales_renderizan(self):
        self.client.login(username="tester", password="ClaveSegura123!")
        self.assertEqual(self.client.get(reverse("monitoreo:dashboard")).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("monitoreo:piscina_detalle", args=[self.piscina.id])).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("monitoreo:registro_nuevo", args=[self.piscina.id])).status_code,
            200,
        )

    def test_crear_registro_con_muestra(self):
        self.client.login(username="tester", password="ClaveSegura123!")
        response = self.client.post(
            reverse("monitoreo:registro_nuevo", args=[self.piscina.id]),
            {
                "ph": "7.1",
                "nitrato": "10.5",
                "amonio": "0.2",
                "nitrito": "0.1",
                "poblacion_estimada": "800",
                "observaciones": "Sin novedades",
                "muestras-TOTAL_FORMS": "3",
                "muestras-INITIAL_FORMS": "0",
                "muestras-MIN_NUM_FORMS": "1",
                "muestras-MAX_NUM_FORMS": "10",
                "muestras-0-especie": "Tilapia",
                "muestras-0-peso_gramos": "250.4",
                "muestras-0-talla_centimetros": "21.3",
                "muestras-1-especie": "",
                "muestras-1-peso_gramos": "",
                "muestras-1-talla_centimetros": "",
                "muestras-2-especie": "",
                "muestras-2-peso_gramos": "",
                "muestras-2-talla_centimetros": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Registro.objects.count(), 1)
        self.assertEqual(MuestraPez.objects.count(), 1)

    def test_lombrices_no_permite_registro_en_este_sprint(self):
        lombrices = Piscina.objects.create(
            nombre="Lombrices",
            codigo="L-01",
            tipo=Piscina.Tipo.LOMBRICES,
        )
        self.client.login(username="tester", password="ClaveSegura123!")
        response = self.client.get(reverse("monitoreo:registro_nuevo", args=[lombrices.id]))
        self.assertRedirects(response, reverse("monitoreo:piscina_detalle", args=[lombrices.id]))
