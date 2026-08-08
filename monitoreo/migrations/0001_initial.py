import django.core.validators
import django.db.models.deletion
import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="Comunidad",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("codigo", models.SlugField(max_length=40, unique=True)),
                ("nombre", models.CharField(max_length=120, unique=True)),
                ("activa", models.BooleanField(default=True)),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
            ],
            options={"verbose_name": "comunidad", "verbose_name_plural": "comunidades", "ordering": ["nombre"]},
        ),
        migrations.CreateModel(
            name="Especie",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre_comun", models.CharField(max_length=120, unique=True)),
                ("nombre_cientifico", models.CharField(blank=True, max_length=180)),
                ("activa", models.BooleanField(default=True)),
            ],
            options={"verbose_name": "especie", "verbose_name_plural": "especies", "ordering": ["nombre_comun"]},
        ),
        migrations.CreateModel(
            name="Acuicultor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nickname", models.CharField(max_length=80, verbose_name="nombre visible")),
                ("fecha_nacimiento", models.DateField(blank=True, null=True)),
                ("rol", models.CharField(choices=[("ACUICULTOR", "Acuicultor"), ("TECNICO", "Técnico"), ("ADMINISTRADOR", "Administrador")], default="ACUICULTOR", max_length=20)),
                ("activo", models.BooleanField(default=True)),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                ("comunidad", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="miembros", to="monitoreo.comunidad")),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="perfil_acuicultor", to=settings.AUTH_USER_MODEL, verbose_name="usuario")),
            ],
            options={"verbose_name": "acuicultor", "verbose_name_plural": "acuicultores", "ordering": ["nickname"]},
        ),
        migrations.CreateModel(
            name="Piscina",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("nombre", models.CharField(max_length=120)),
                ("codigo", models.CharField(max_length=30)),
                ("tipo", models.CharField(choices=[("PECES", "Peces"), ("LOMBRICES", "Lombrices")], max_length=20)),
                ("descripcion", models.TextField(blank=True)),
                ("area_m2", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("activa", models.BooleanField(default=True)),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                ("comunidad", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="piscinas", to="monitoreo.comunidad")),
                ("especie", models.ForeignKey(blank=True, help_text="Obligatoria y permanente para piscinas de peces.", null=True, on_delete=django.db.models.deletion.PROTECT, related_name="piscinas", to="monitoreo.especie")),
            ],
            options={"verbose_name": "piscina", "verbose_name_plural": "piscinas", "ordering": ["tipo", "nombre"]},
        ),
        migrations.CreateModel(
            name="JornadaRegistro",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("capturada_en", models.DateTimeField(default=django.utils.timezone.now)),
                ("recibida_en", models.DateTimeField(auto_now_add=True)),
                ("poblacion_estimada", models.PositiveIntegerField()),
                ("observaciones", models.TextField(blank=True)),
                ("fuente", models.CharField(choices=[("WEB", "Web"), ("ANDROID", "Android")], default="WEB", max_length=12)),
                ("dispositivo_id", models.CharField(blank=True, max_length=120)),
                ("estado", models.CharField(choices=[("BORRADOR", "Borrador"), ("COMPLETA", "Completa"), ("ANULADA", "Anulada")], default="BORRADOR", max_length=12)),
                ("version", models.PositiveIntegerField(default=1)),
                ("creada_en", models.DateTimeField(auto_now_add=True)),
                ("modificada_en", models.DateTimeField(auto_now=True)),
                ("anulada_en", models.DateTimeField(blank=True, null=True)),
                ("motivo_anulacion", models.TextField(blank=True)),
                ("anulada_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="jornadas_anuladas", to=settings.AUTH_USER_MODEL)),
                ("autor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="jornadas_creadas", to="monitoreo.acuicultor")),
                ("piscina", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="registros", to="monitoreo.piscina")),
            ],
            options={"verbose_name": "jornada de registro", "verbose_name_plural": "jornadas de registro", "ordering": ["-capturada_en", "-creada_en"]},
        ),
        migrations.CreateModel(
            name="MedicionAgua",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ph", models.DecimalField(decimal_places=2, max_digits=4, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(14)], verbose_name="pH")),
                ("nitrato", models.DecimalField(decimal_places=3, help_text="Unidad provisional: mg/L.", max_digits=10, validators=[django.core.validators.MinValueValidator(0)])),
                ("nitrito", models.DecimalField(decimal_places=3, help_text="Unidad provisional: mg/L.", max_digits=10, validators=[django.core.validators.MinValueValidator(0)])),
                ("amonio", models.DecimalField(decimal_places=3, help_text="Unidad provisional: mg/L.", max_digits=10, validators=[django.core.validators.MinValueValidator(0)])),
                ("jornada", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="agua", to="monitoreo.jornadaregistro")),
            ],
            options={"verbose_name": "medición de agua", "verbose_name_plural": "mediciones de agua"},
        ),
        migrations.CreateModel(
            name="MuestraBiometrica",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("metodo", models.CharField(blank=True, max_length=160)),
                ("jornada", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="muestra_biometrica", to="monitoreo.jornadaregistro")),
            ],
            options={"verbose_name": "muestra biométrica", "verbose_name_plural": "muestras biométricas"},
        ),
        migrations.CreateModel(
            name="ObservacionPez",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("orden", models.PositiveIntegerField()),
                ("peso_gramos", models.DecimalField(decimal_places=2, max_digits=10, validators=[django.core.validators.MinValueValidator(0.01)])),
                ("talla_centimetros", models.DecimalField(decimal_places=2, help_text="Longitud total del pez.", max_digits=10, validators=[django.core.validators.MinValueValidator(0.01)])),
                ("muestra", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="peces", to="monitoreo.muestrabiometrica")),
            ],
            options={"verbose_name": "observación de pez", "verbose_name_plural": "observaciones de peces", "ordering": ["orden"]},
        ),
        migrations.CreateModel(
            name="MovimientoPoblacion",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("tipo", models.CharField(choices=[("SIEMBRA", "Siembra"), ("MORTALIDAD", "Mortalidad"), ("COSECHA_VENTA", "Cosecha o venta"), ("TRASLADO", "Traslado"), ("ESCAPE", "Escape"), ("AJUSTE", "Ajuste")], max_length=20)),
                ("cantidad", models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(1)])),
                ("ocurrido_en", models.DateTimeField(default=django.utils.timezone.now)),
                ("observaciones", models.TextField(blank=True)),
                ("estado", models.CharField(choices=[("ACTIVO", "Activo"), ("ANULADO", "Anulado")], default="ACTIVO", max_length=10)),
                ("version", models.PositiveIntegerField(default=1)),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("modificado_en", models.DateTimeField(auto_now=True)),
                ("anulado_en", models.DateTimeField(blank=True, null=True)),
                ("motivo_anulacion", models.TextField(blank=True)),
                ("anulado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="movimientos_anulados", to=settings.AUTH_USER_MODEL)),
                ("autor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="movimientos_creados", to="monitoreo.acuicultor")),
                ("piscina_destino", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="movimientos_entrada", to="monitoreo.piscina")),
                ("piscina_origen", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="movimientos_salida", to="monitoreo.piscina")),
            ],
            options={"verbose_name": "movimiento de población", "verbose_name_plural": "movimientos de población", "ordering": ["-ocurrido_en", "-creado_en"]},
        ),
        migrations.CreateModel(
            name="AuditoriaCambio",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("entidad", models.CharField(choices=[("JORNADA", "Jornada"), ("MOVIMIENTO", "Movimiento")], max_length=20)),
                ("entidad_uuid", models.UUIDField()),
                ("accion", models.CharField(choices=[("CREAR", "Crear"), ("CORREGIR", "Corregir"), ("ANULAR", "Anular")], max_length=12)),
                ("version_anterior", models.PositiveIntegerField(blank=True, null=True)),
                ("version_nueva", models.PositiveIntegerField()),
                ("fecha", models.DateTimeField(auto_now_add=True)),
                ("motivo", models.TextField(blank=True)),
                ("datos_anteriores", models.JSONField(blank=True, null=True)),
                ("datos_nuevos", models.JSONField(blank=True, null=True)),
                ("actor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="acciones_auditoria", to=settings.AUTH_USER_MODEL)),
            ],
            options={"verbose_name": "evento de auditoría", "verbose_name_plural": "eventos de auditoría", "ordering": ["-fecha", "-id"]},
        ),
        migrations.AddConstraint(model_name="acuicultor", constraint=models.UniqueConstraint(fields=("comunidad", "nickname"), name="uq_acuicultor_nickname_comunidad")),
        migrations.AddConstraint(model_name="piscina", constraint=models.UniqueConstraint(fields=("comunidad", "codigo"), name="uq_piscina_codigo_comunidad")),
        migrations.AddConstraint(model_name="piscina", constraint=models.CheckConstraint(condition=models.Q(("tipo", "LOMBRICES"), ("especie__isnull", False), _connector="OR"), name="ck_piscina_peces_con_especie")),
        migrations.AddIndex(model_name="jornadaregistro", index=models.Index(fields=["piscina", "-capturada_en"], name="ix_jornada_piscina_fecha")),
        migrations.AddIndex(model_name="jornadaregistro", index=models.Index(fields=["autor", "-capturada_en"], name="ix_jornada_autor_fecha")),
        migrations.AddIndex(model_name="jornadaregistro", index=models.Index(fields=["estado"], name="ix_jornada_estado")),
        migrations.AddConstraint(model_name="jornadaregistro", constraint=models.CheckConstraint(condition=models.Q(("version__gte", 1)), name="ck_jornada_version_positiva")),
        migrations.AddConstraint(model_name="observacionpez", constraint=models.UniqueConstraint(fields=("muestra", "orden"), name="uq_observacion_orden_muestra")),
        migrations.AddConstraint(model_name="movimientopoblacion", constraint=models.CheckConstraint(condition=models.Q(("piscina_origen__isnull", False), ("piscina_destino__isnull", False), _connector="OR"), name="ck_movimiento_con_piscina")),
        migrations.AddConstraint(model_name="movimientopoblacion", constraint=models.CheckConstraint(condition=models.Q(("version__gte", 1)), name="ck_movimiento_version_positiva")),
        migrations.AddIndex(model_name="auditoriacambio", index=models.Index(fields=["entidad", "entidad_uuid", "-fecha"], name="ix_auditoria_entidad")),
    ]
