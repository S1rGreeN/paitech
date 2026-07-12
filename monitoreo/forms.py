from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.forms import formset_factory

from .models import MuestraPez, Registro

INPUT_CLASS = (
    "mt-1 block w-full rounded-2xl border border-stone-200 bg-white px-4 py-3 "
    "text-stone-800 shadow-sm outline-none transition focus:border-brand-green "
    "focus:ring-4 focus:ring-lime-100"
)
TEXTAREA_CLASS = INPUT_CLASS + " min-h-28 resize-y"


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label="Usuario",
        widget=forms.TextInput(
            attrs={
                "class": INPUT_CLASS,
                "placeholder": "Ej. acuicultor",
                "autocomplete": "username",
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


class RegistroForm(forms.ModelForm):
    class Meta:
        model = Registro
        fields = [
            "ph",
            "nitrato",
            "amonio",
            "nitrito",
            "poblacion_estimada",
            "observaciones",
        ]
        widgets = {
            "ph": forms.NumberInput(attrs={"class": INPUT_CLASS, "step": "0.01", "min": "0", "max": "14"}),
            "nitrato": forms.NumberInput(attrs={"class": INPUT_CLASS, "step": "0.01", "min": "0"}),
            "amonio": forms.NumberInput(attrs={"class": INPUT_CLASS, "step": "0.01", "min": "0"}),
            "nitrito": forms.NumberInput(attrs={"class": INPUT_CLASS, "step": "0.01", "min": "0"}),
            "poblacion_estimada": forms.NumberInput(attrs={"class": INPUT_CLASS, "min": "1"}),
            "observaciones": forms.Textarea(
                attrs={
                    "class": TEXTAREA_CLASS,
                    "placeholder": "Comportamiento, alimentación, color del agua u otras novedades.",
                }
            ),
        }
        labels = {
            "ph": "pH del agua",
            "nitrato": "Nitrato (mg/L)",
            "amonio": "Amonio (mg/L)",
            "nitrito": "Nitrito (mg/L)",
            "poblacion_estimada": "Población estimada",
            "observaciones": "Observaciones",
        }


class MuestraPezForm(forms.ModelForm):
    class Meta:
        model = MuestraPez
        fields = ["especie", "peso_gramos", "talla_centimetros"]
        widgets = {
            "especie": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Ej. Tilapia roja"}),
            "peso_gramos": forms.NumberInput(attrs={"class": INPUT_CLASS, "step": "0.01", "min": "0.01"}),
            "talla_centimetros": forms.NumberInput(attrs={"class": INPUT_CLASS, "step": "0.01", "min": "0.01"}),
        }
        labels = {
            "especie": "Especie",
            "peso_gramos": "Peso (g)",
            "talla_centimetros": "Talla (cm)",
        }


MuestraPezFormSet = formset_factory(
    MuestraPezForm,
    extra=3,
    min_num=1,
    validate_min=True,
    max_num=10,
    validate_max=True,
)
