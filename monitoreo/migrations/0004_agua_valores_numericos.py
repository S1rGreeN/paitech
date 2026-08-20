from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("monitoreo", "0003_ciclos_y_sensores_v15"),
    ]

    operations = [
        migrations.AlterField(
            model_name="medicionagua",
            name="ph",
            field=models.DecimalField(
                decimal_places=2,
                help_text=(
                    "Valor numérico final; se guarda un solo pH aunque se usen "
                    "ambas escalas del kit."
                ),
                max_digits=4,
                validators=[MinValueValidator(0), MaxValueValidator(14)],
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
                validators=[MinValueValidator(0)],
            ),
        ),
        migrations.AlterField(
            model_name="medicionagua",
            name="nitrito",
            field=models.DecimalField(
                decimal_places=3,
                help_text="Nitrito (NO₂⁻), en ppm.",
                max_digits=10,
                validators=[MinValueValidator(0)],
            ),
        ),
        migrations.AlterField(
            model_name="medicionagua",
            name="amoniaco_total",
            field=models.DecimalField(
                decimal_places=3,
                help_text="Amoníaco total (NH₃/NH₄⁺), en ppm.",
                max_digits=10,
                validators=[MinValueValidator(0)],
                verbose_name="amoníaco total",
            ),
        ),
    ]
