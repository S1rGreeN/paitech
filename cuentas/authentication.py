import hmac
import uuid
from django.utils import timezone
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, get_authorization_header

from .models import TokenDispositivo, VIGENCIA_TOKEN_DISPOSITIVO


class TokenDispositivoAuthentication(BaseAuthentication):
    keyword = "Token"

    def authenticate(self, request):
        partes = get_authorization_header(request).split()
        if not partes:
            return None
        if partes[0].lower() != self.keyword.lower().encode():
            return None
        if len(partes) != 2:
            raise exceptions.AuthenticationFailed("Encabezado de autorización inválido.")
        try:
            credencial = partes[1].decode("ascii")
            selector, secreto = credencial.split(".", 1)
            token_id = uuid.UUID(selector)
        except (UnicodeDecodeError, ValueError):
            raise exceptions.AuthenticationFailed("Sesión inválida.")

        try:
            token = TokenDispositivo.objects.select_related("usuario").get(pk=token_id)
        except TokenDispositivo.DoesNotExist:
            raise exceptions.AuthenticationFailed("Sesión inválida.")

        hash_recibido = TokenDispositivo.hash_secreto(secreto)
        if not hmac.compare_digest(hash_recibido, token.secreto_hash):
            raise exceptions.AuthenticationFailed("Sesión inválida.")
        if token.revocado_en is not None or token.expira_en <= timezone.now():
            raise exceptions.AuthenticationFailed("La sesión expiró o fue revocada.")
        if not token.usuario.is_active:
            raise exceptions.AuthenticationFailed("La cuenta no está disponible.")

        ahora = timezone.now()
        token.ultimo_uso_en = ahora
        token.expira_en = ahora + VIGENCIA_TOKEN_DISPOSITIVO
        token.save(update_fields=["ultimo_uso_en", "expira_en"])
        return token.usuario, token

    def authenticate_header(self, request):
        return self.keyword
