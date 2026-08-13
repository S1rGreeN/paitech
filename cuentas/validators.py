from django.core.exceptions import ValidationError


class MaximumLengthValidator:
    def __init__(self, max_length=32):
        self.max_length = max_length

    def validate(self, password, user=None):
        if len(password) > self.max_length:
            raise ValidationError(
                "La contraseña no puede superar %(max_length)d caracteres.",
                code="password_too_long",
                params={"max_length": self.max_length},
            )

    def get_help_text(self):
        return "La contraseña puede tener como máximo %(max_length)d caracteres." % {
            "max_length": self.max_length
        }
