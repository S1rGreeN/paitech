from decimal import Decimal
import uuid

from django.db import migrations, models


FUENTE_TILAPIA_BIENESTAR = (
    "https://www.frontiersin.org/journals/veterinary-science/articles/"
    "10.3389/fvets.2023.1268396/full"
)
FUENTE_TILAPIA_FAO = "https://www.fao.org/fi/static-media/MeetingDocuments/TiLV/s3.pdf"
FUENTE_TILAPIA_NITRATO = "https://onlinelibrary.wiley.com/doi/10.1111/are.13174"


def preparar_datos(apps, schema_editor):
    Comunidad = apps.get_model("monitoreo", "Comunidad")
    Acuicultor = apps.get_model("monitoreo", "Acuicultor")
    Auditoria = apps.get_model("monitoreo", "AuditoriaCambio")
    Especie = apps.get_model("monitoreo", "Especie")
    Perfil = apps.get_model("monitoreo", "PerfilSemaforoEspecie")
    Piscina = apps.get_model("monitoreo", "Piscina")
    Cama = apps.get_model("monitoreo", "CamaLombrices")
    Ciclo = apps.get_model("monitoreo", "CicloProductivo")
    Jornada = apps.get_model("monitoreo", "JornadaRegistro")
    Movimiento = apps.get_model("monitoreo", "MovimientoPoblacion")
    Dispositivo = apps.get_model("monitoreo", "DispositivoSensor")

    for comunidad in Comunidad.objects.filter(id_publico__isnull=True).iterator():
        comunidad.id_publico = uuid.uuid4()
        comunidad.save(update_fields=["id_publico"])

    comunidad_por_usuario = dict(Acuicultor.objects.values_list("user_id", "comunidad_id"))
    for evento in Auditoria.objects.filter(comunidad__isnull=True).iterator():
        comunidad_id = comunidad_por_usuario.get(evento.actor_id)
        if comunidad_id:
            evento.comunidad_id = comunidad_id
            evento.save(update_fields=["comunidad"])

    # Una piscina histórica marcada como LOMBRICES solo se transforma si no
    # tiene datos acuícolas asociados. Ante cualquier relación, se detiene la
    # migración para evitar una pérdida silenciosa.
    for legado in Piscina.objects.filter(tipo="LOMBRICES").iterator():
        tiene_datos = (
            Ciclo.objects.filter(piscina_id=legado.pk).exists()
            or Jornada.objects.filter(piscina_id=legado.pk).exists()
            or Movimiento.objects.filter(piscina_origen_id=legado.pk).exists()
            or Movimiento.objects.filter(piscina_destino_id=legado.pk).exists()
            or Dispositivo.objects.filter(piscina_id=legado.pk).exists()
        )
        if tiene_datos:
            raise RuntimeError(
                f"La piscina legada {legado.codigo} contiene datos. "
                "Debe migrarse manualmente antes de separar lombricultura."
            )
        Cama.objects.get_or_create(
            comunidad_id=legado.comunidad_id,
            codigo=legado.codigo,
            defaults={
                "nombre": legado.nombre,
                "descripcion": legado.descripcion,
                "area_m2": legado.area_m2,
                "activa": legado.activa,
            },
        )
        legado.delete()

    paipayales, _ = Comunidad.objects.get_or_create(
        codigo="paipayales",
        defaults={"nombre": "Paipayales", "activa": True, "id_publico": uuid.uuid4()},
    )
    galo, _ = Comunidad.objects.get_or_create(
        codigo="colegio-galo-plaza-lasso",
        defaults={
            "nombre": "Colegio Galo Plaza Lasso",
            "activa": True,
            "id_publico": uuid.uuid4(),
        },
    )
    vieja, _ = Especie.objects.get_or_create(
        nombre_comun="Vieja Azul",
        defaults={"nombre_cientifico": "Andinoacara rivulatus", "activa": True},
    )
    tilapia, _ = Especie.objects.get_or_create(
        nombre_comun="Tilapia",
        defaults={"nombre_cientifico": "", "activa": True},
    )

    Piscina.objects.get_or_create(
        comunidad=paipayales,
        codigo="P-01",
        defaults={
            "nombre": "Piscina 1 Paipayales",
            "tipo": "PECES",
            "especie": vieja,
            "descripcion": "",
            "area_m2": None,
            "activa": True,
        },
    )
    Piscina.objects.get_or_create(
        comunidad=galo,
        codigo="P-01",
        defaults={
            "nombre": "Piscina 1 Colegio Galo Plaza Lasso",
            "tipo": "PECES",
            "especie": tilapia,
            "descripcion": "",
            "area_m2": None,
            "activa": True,
        },
    )
    Cama.objects.get_or_create(
        comunidad=paipayales,
        codigo="C-01",
        defaults={
            "nombre": "Cama 1 Paipayales",
            "descripcion": "",
            "area_m2": None,
            "activa": True,
        },
    )

    Perfil.objects.update_or_create(
        especie=vieja,
        defaults={
            "version": "vieja-azul-1.3",
            "provisional": True,
            "supuesto_biologico": (
                "Conserva los umbrales que ya utilizaba la aplicación para Vieja Azul; "
                "requiere validación posterior por un profesional acuícola."
            ),
            "fuentes": [],
            "ph_critico_bajo": Decimal("6.00"),
            "ph_ideal_bajo": Decimal("6.50"),
            "ph_ideal_alto": Decimal("8.50"),
            "ph_critico_alto": Decimal("9.00"),
            "nitrito_amarillo_desde": Decimal("0.500"),
            "nitrito_rojo_desde": Decimal("1.001"),
            "nitrato_amarillo_desde": Decimal("50.000"),
            "nitrato_rojo_desde": Decimal("100.001"),
            "amoniaco_total_amarillo_desde": Decimal("0.500"),
            "amoniaco_total_rojo_desde": Decimal("1.001"),
            "nh3_amarillo_desde": Decimal("0.02001"),
            "nh3_rojo_desde": Decimal("0.05001"),
        },
    )
    Perfil.objects.update_or_create(
        especie=tilapia,
        defaults={
            "version": "tilapia-nilo-prov-2026.1",
            "provisional": True,
            "supuesto_biologico": (
                "El catálogo aún no identifica la especie científica. El perfil usa "
                "provisionalmente evidencia de tilapia del Nilo (Oreochromis niloticus) "
                "y debe revisarse al confirmar la especie."
            ),
            "fuentes": [
                FUENTE_TILAPIA_BIENESTAR,
                FUENTE_TILAPIA_FAO,
                FUENTE_TILAPIA_NITRATO,
            ],
            "ph_critico_bajo": Decimal("5.50"),
            "ph_ideal_bajo": Decimal("6.00"),
            "ph_ideal_alto": Decimal("8.50"),
            "ph_critico_alto": Decimal("9.50"),
            "nitrito_amarillo_desde": Decimal("0.310"),
            "nitrito_rojo_desde": Decimal("0.500"),
            "nitrato_amarillo_desde": Decimal("443.000"),
            "nitrato_rojo_desde": Decimal("2214.000"),
            "amoniaco_total_amarillo_desde": Decimal("0.100"),
            "amoniaco_total_rojo_desde": Decimal("0.500"),
            "nh3_amarillo_desde": Decimal("0.06000"),
            "nh3_rojo_desde": Decimal("0.10000"),
            "temperatura_critica_baja_c": Decimal("21.00"),
            "temperatura_ideal_baja_c": Decimal("24.00"),
            "temperatura_ideal_alta_c": Decimal("31.00"),
            "temperatura_critica_alta_c": Decimal("35.00"),
            "oxigeno_rojo_menor_que_mg_l": Decimal("1.00"),
            "oxigeno_verde_desde_mg_l": Decimal("6.00"),
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ("monitoreo", "0005_comunidades_lombricultura_semaforos"),
    ]

    operations = [
        migrations.RunPython(preparar_datos, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="comunidad",
            name="id_publico",
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                help_text=(
                    "Identificador estable que puede exponerse a clientes sin revelar la PK interna."
                ),
                unique=True,
            ),
        ),
        migrations.AddConstraint(
            model_name="piscina",
            constraint=models.CheckConstraint(
                condition=models.Q(("tipo", "PECES"), ("especie__isnull", False)),
                name="ck_piscina_peces_con_especie",
            ),
        ),
    ]
