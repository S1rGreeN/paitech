import hmac
import uuid

from django.utils import timezone
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, get_authorization_header

from .models import DispositivoSensor


class PrincipalSensor:
    is_authenticated = True
    is_anonymous = False

    def __init__(self, dispositivo):
        self.dispositivo = dispositivo

    def __str__(self):
        return f"sensor:{self.dispositivo.codigo}"


class SensorAuthentication(BaseAuthentication):
    keyword = "Sensor"

    def authenticate(self, request):
        partes = get_authorization_header(request).split()
        if not partes:
            return None
        if partes[0].lower() != self.keyword.lower().encode():
            return None
        if len(partes) != 2:
            raise exceptions.AuthenticationFailed("Credencial de sensor inválida.")
        try:
            selector, secreto = partes[1].decode("ascii").split(".", 1)
            selector = uuid.UUID(selector)
        except (UnicodeDecodeError, ValueError):
            raise exceptions.AuthenticationFailed("Credencial de sensor inválida.")
        try:
            dispositivo = DispositivoSensor.objects.select_related("piscina").get(
                selector=selector, activo=True
            )
        except DispositivoSensor.DoesNotExist as error:
            raise exceptions.AuthenticationFailed("Credencial de sensor inválida.") from error
        recibido = DispositivoSensor.hash_secreto(secreto)
        if not dispositivo.secreto_hash or not hmac.compare_digest(
            recibido, dispositivo.secreto_hash
        ):
            raise exceptions.AuthenticationFailed("Credencial de sensor inválida.")
        dispositivo.ultimo_uso_en = timezone.now()
        dispositivo.save(update_fields=["ultimo_uso_en"])
        return PrincipalSensor(dispositivo), dispositivo

    def authenticate_header(self, request):
        return self.keyword
