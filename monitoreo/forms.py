from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.forms import BaseFormSet, formset_factory
from django.utils import timezone

from .models import JornadaRegistro

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
    ph = forms.DecimalField(required=False, min_value=0, max_value=14, max_digits=4, decimal_places=2, widget=forms.NumberInput(attrs={"class": INPUT_CLASS, "step": "0.01"}))
    nitrato = forms.DecimalField(required=False, min_value=0, max_digits=10, decimal_places=3, widget=forms.NumberInput(attrs={"class": INPUT_CLASS, "step": "0.001"}))
    nitrito = forms.DecimalField(required=False, min_value=0, max_digits=10, decimal_places=3, widget=forms.NumberInput(attrs={"class": INPUT_CLASS, "step": "0.001"}))
    amonio = forms.DecimalField(required=False, min_value=0, max_digits=10, decimal_places=3, widget=forms.NumberInput(attrs={"class": INPUT_CLASS, "step": "0.001"}))

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
            faltantes = [campo for campo in ("ph", "nitrato", "nitrito", "amonio") if datos.get(campo) is None]
            if faltantes:
                raise forms.ValidationError("Los cuatro parámetros de agua son obligatorios cuando incluyes ese bloque.")
        return datos

    def datos_agua(self):
        if not self.cleaned_data["registrar_agua"]:
            return None
        return {campo: self.cleaned_data[campo] for campo in ("ph", "nitrato", "nitrito", "amonio")}


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
