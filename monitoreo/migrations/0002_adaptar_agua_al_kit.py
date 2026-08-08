import django.core.validators
from django.db import migrations, models

import monitoreo.calidad_agua


class Migration(migrations.Migration):
    dependencies = [("monitoreo", "0001_initial")]

    operations = [
        migrations.RenameField(
            model_name="medicionagua",
            old_name="amonio",
            new_name="amoniaco_total",
        ),
        migrations.AlterField(
            model_name="medicionagua",
            name="ph",
            field=models.DecimalField(
                decimal_places=2,
                help_text=(
                    "Valor final de una de las dos escalas de pH del kit; "
                    "se guarda un solo pH."
                ),
                max_digits=4,
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(14),
                    monitoreo.calidad_agua.validar_ph_kit,
                ],
                verbose_name="pH",
            ),
        ),
        migrations.AlterField(
            model_name="medicionagua",
            name="nitrato",
            field=models.DecimalField(
                decimal_places=3,
                help_text="Nitrato (NO₃⁻), en ppm.",
                max_digits=10,
                validators=[
                    django.core.validators.MinValueValidator(0),
                    monitoreo.calidad_agua.validar_nitrato_kit,
                ],
            ),
        ),
        migrations.AlterField(
            model_name="medicionagua",
            name="nitrito",
            field=models.DecimalField(
                decimal_places=3,
                help_text="Nitrito (NO₂⁻), en ppm.",
                max_digits=10,
                validators=[
                    django.core.validators.MinValueValidator(0),
                    monitoreo.calidad_agua.validar_nitrito_kit,
                ],
            ),
        ),
        migrations.AlterField(
            model_name="medicionagua",
            name="amoniaco_total",
            field=models.DecimalField(
                decimal_places=3,
                help_text="Amoníaco total (NH₃/NH₄⁺), en ppm.",
                max_digits=10,
                validators=[
                    django.core.validators.MinValueValidator(0),
                    monitoreo.calidad_agua.validar_amoniaco_total_kit,
                ],
                verbose_name="amoníaco total",
            ),
        ),
    ]
