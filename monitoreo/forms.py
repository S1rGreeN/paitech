from decimal import Decimal

from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.core.exceptions import ObjectDoesNotExist
from django.forms import BaseFormSet, formset_factory
from django.utils import timezone

from .calidad_agua import (
    AMONIACO_TOTAL_VALORES,
    NITRATO_VALORES,
    NITRITO_VALORES,
    PH_VALORES,
    opciones_formulario,
)
from .models import CicloProductivo, JornadaRegistro, Piscina

INPUT_CLASS = (
    "mt-1 block w-full rounded-2xl border border-stone-200 bg-white px-4 py-3 "
    "text-stone-800 shadow-sm outline-none transition focus:border-brand-green "
    "focus:ring-4 focus:ring-lime-100"
)
TEXTAREA_CLASS = INPUT_CLASS + " min-h-28 resize-y"
CHECKBOX_CLASS = "h-5 w-5 rounded border-stone-300 text-brand-green focus:ring-brand-green"


class LoginForm(AuthenticationForm):
    username = forms.EmailField(
        label="Correo electrónico",
        widget=forms.EmailInput(
            attrs={
                "class": INPUT_CLASS,
                "placeholder": "nombre@ejemplo.com",
                "autocomplete": "email",
                "autofocus": True,
            }
        ),
    )
    password = forms.CharField(
        label="Contraseña",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": INPUT_CLASS,
                "placeholder": "Ingresa tu contraseña",
                "autocomplete": "current-password",
            }
        ),
    )

    def confirm_login_allowed(self, user):
        try:
            perfil = user.perfil_acuicultor
            permitido = user.is_active and perfil.activo and perfil.comunidad.activa
        except ObjectDoesNotExist:
            permitido = False
        if not permitido:
            raise forms.ValidationError(
                "No fue posible iniciar sesión. Verifica los datos o intenta más tarde.",
                code="invalid_login",
            )


class CambioClaveInicialForm(PasswordChangeForm):
    old_password = forms.CharField(
        label="Contraseña temporal",
        strip=False,
        widget=forms.PasswordInput(attrs={"class": INPUT_CLASS, "autocomplete": "current-password"}),
    )
    new_password1 = forms.CharField(
        label="Nueva contraseña",
        strip=False,
        help_text="Entre 8 y 32 caracteres; no uses datos personales ni claves comunes.",
        widget=forms.PasswordInput(attrs={"class": INPUT_CLASS, "autocomplete": "new-password"}),
    )
    new_password2 = forms.CharField(
        label="Confirma la nueva contraseña",
        strip=False,
        widget=forms.PasswordInput(attrs={"class": INPUT_CLASS, "autocomplete": "new-password"}),
    )


class JornadaForm(forms.ModelForm):
    registrar_agua = forms.BooleanField(
        required=False,
        initial=True,
        label="Incluir medición de agua",
        widget=forms.CheckboxInput(attrs={"class": CHECKBOX_CLASS}),
    )
    registrar_biometria = forms.BooleanField(
        required=False,
        initial=True,
        label="Incluir muestra biométrica",
        widget=forms.CheckboxInput(attrs={"class": CHECKBOX_CLASS}),
    )
    ph = forms.TypedChoiceField(
        required=False,
        coerce=Decimal,
        empty_value=None,
        choices=(("", "Selecciona el pH final"),) + opciones_formulario(PH_VALORES),
        label="pH final (escala normal o alta)",
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )
    nitrato = forms.TypedChoiceField(
        required=False,
        coerce=Decimal,
        empty_value=None,
        choices=(("", "Selecciona una lectura"),) + opciones_formulario(NITRATO_VALORES),
        label="Nitrato (NO₃⁻), ppm",
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )
    nitrito = forms.TypedChoiceField(
        required=False,
        coerce=Decimal,
        empty_value=None,
        choices=(("", "Selecciona una lectura"),) + opciones_formulario(NITRITO_VALORES),
        label="Nitrito (NO₂⁻), ppm",
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )
    amoniaco_total = forms.TypedChoiceField(
        required=False,
        coerce=Decimal,
        empty_value=None,
        choices=(("", "Selecciona una lectura"),) + opciones_formulario(AMONIACO_TOTAL_VALORES),
        label="Amoníaco total (NH₃/NH₄⁺), ppm",
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )

    class Meta:
        model = JornadaRegistro
        fields = ["capturada_en", "poblacion_estimada", "observaciones"]
        widgets = {
            "capturada_en": forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"class": INPUT_CLASS, "type": "datetime-local"}),
            "poblacion_estimada": forms.NumberInput(attrs={"class": INPUT_CLASS, "min": "0"}),
            "observaciones": forms.Textarea(attrs={"class": TEXTAREA_CLASS, "placeholder": "Hallazgos, especies inesperadas y cualquier novedad."}),
        }
        labels = {
            "capturada_en": "Fecha y hora de la jornada",
            "poblacion_estimada": "Población total estimada",
            "observaciones": "Observaciones generales",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["capturada_en"].input_formats = ["%Y-%m-%dT%H:%M"]
        if not self.is_bound and not self.instance.pk:
            self.initial["capturada_en"] = timezone.localtime().strftime("%Y-%m-%dT%H:%M")

    def clean(self):
        datos = super().clean()
        if not datos.get("registrar_agua") and not datos.get("registrar_biometria"):
            raise forms.ValidationError("Selecciona agua, biometría o ambos bloques.")
        if datos.get("registrar_agua"):
            faltantes = [campo for campo in ("ph", "nitrato", "nitrito", "amoniaco_total") if datos.get(campo) is None]
            if faltantes:
                raise forms.ValidationError("Los cuatro parámetros de agua son obligatorios cuando incluyes ese bloque.")
        return datos

    def datos_agua(self):
        if not self.cleaned_data["registrar_agua"]:
            return None
        return {campo: self.cleaned_data[campo] for campo in ("ph", "nitrato", "nitrito", "amoniaco_total")}


class CicloAperturaForm(forms.Form):
    iniciado_en = forms.DateTimeField(
        label="Fecha y hora de inicio",
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={"class": INPUT_CLASS, "type": "datetime-local"},
        ),
    )
    poblacion_inicial = forms.IntegerField(
        min_value=1,
        label="Población inicial sembrada",
        widget=forms.NumberInput(attrs={"class": INPUT_CLASS, "min": "1"}),
    )
    duracion_estimada_meses = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=60,
        label="Duración estimada (meses)",
        widget=forms.NumberInput(attrs={"class": INPUT_CLASS, "min": "1", "max": "60"}),
    )
    observaciones_apertura = forms.CharField(
        required=False,
        max_length=5000,
        label="Observaciones",
        widget=forms.Textarea(attrs={"class": TEXTAREA_CLASS}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.initial["iniciado_en"] = timezone.localtime().strftime("%Y-%m-%dT%H:%M")


class CicloCierreForm(forms.Form):
    cerrado_en = forms.DateTimeField(
        label="Fecha y hora de cierre",
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={"class": INPUT_CLASS, "type": "datetime-local"},
        ),
    )
    destino_cierre = forms.ChoiceField(
        choices=CicloProductivo.DestinoCierre.choices,
        label="Destino final",
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )
    poblacion_final = forms.IntegerField(
        min_value=0,
        label="Población final viva",
        widget=forms.NumberInput(attrs={"class": INPUT_CLASS, "min": "0"}),
    )
    peso_total_cosechado_kg = forms.DecimalField(
        required=False,
        min_value=0,
        max_digits=12,
        decimal_places=3,
        label="Peso total cosechado (kg, opcional)",
        widget=forms.NumberInput(attrs={"class": INPUT_CLASS, "min": "0", "step": "0.001"}),
    )
    piscina_destino_cierre = forms.ModelChoiceField(
        required=False,
        queryset=Piscina.objects.none(),
        label="Piscina destino (opcional para traslado)",
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )
    observaciones_cierre = forms.CharField(
        required=False,
        max_length=5000,
        label="Observaciones",
        widget=forms.Textarea(attrs={"class": TEXTAREA_CLASS}),
    )

    def __init__(self, *args, ciclo, **kwargs):
        super().__init__(*args, **kwargs)
        self.ciclo = ciclo
        self.fields["piscina_destino_cierre"].queryset = Piscina.objects.filter(
            comunidad=ciclo.piscina.comunidad,
            especie=ciclo.especie,
            activa=True,
            tipo=Piscina.Tipo.PECES,
        ).exclude(pk=ciclo.piscina_id)
        if not self.is_bound:
            self.initial["cerrado_en"] = timezone.localtime().strftime("%Y-%m-%dT%H:%M")

    def clean(self):
        datos = super().clean()
        destino = datos.get("destino_cierre")
        piscina_destino = datos.get("piscina_destino_cierre")
        if destino != CicloProductivo.DestinoCierre.TRASLADO and piscina_destino:
            self.add_error(
                "piscina_destino_cierre",
                "Solo puede indicarse cuando el destino final es traslado.",
            )
        if (
            destino == CicloProductivo.DestinoCierre.MORTALIDAD_TOTAL
            and datos.get("poblacion_final") != 0
        ):
            self.add_error("poblacion_final", "La mortalidad total requiere población final cero.")
        return datos


class ObservacionPezForm(forms.Form):
    peso_gramos = forms.DecimalField(
        required=False,
        min_value=0.01,
        max_digits=10,
        decimal_places=2,
        label="Peso (g)",
        widget=forms.NumberInput(attrs={"class": INPUT_CLASS, "step": "0.01", "min": "0.01"}),
    )
    talla_centimetros = forms.DecimalField(
        required=False,
        min_value=0.01,
        max_digits=10,
        decimal_places=2,
        label="Longitud total (cm)",
        widget=forms.NumberInput(attrs={"class": INPUT_CLASS, "step": "0.01", "min": "0.01"}),
    )

    def clean(self):
        datos = super().clean()
        peso = datos.get("peso_gramos")
        talla = datos.get("talla_centimetros")
        if (peso is None) != (talla is None):
            raise forms.ValidationError("Cada pez requiere peso y longitud total.")
        return datos


class BaseObservacionPezFormSet(BaseFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        incluir_biometria = self.data.get("registrar_biometria") in {"on", "true", "1"}
        if incluir_biometria and not self.peces_limpios():
            raise forms.ValidationError("Agrega al menos un pez para completar la biometría.")

    def peces_limpios(self):
        return [
            {
                "peso_gramos": formulario.cleaned_data["peso_gramos"],
                "talla_centimetros": formulario.cleaned_data["talla_centimetros"],
            }
            for formulario in self.forms
            if formulario.cleaned_data and formulario.cleaned_data.get("peso_gramos") is not None
        ]


ObservacionPezFormSet = formset_factory(
    ObservacionPezForm,
    formset=BaseObservacionPezFormSet,
    extra=3,
    min_num=0,
    validate_min=False,
    max_num=500,
    validate_max=True,
)
