import logging
import re
import uuid


logger = logging.getLogger("paipaytech.http")
ID_SEGURO = re.compile(r"^[A-Za-z0-9_.-]{8,64}$")


class RequestIdMiddleware:
    """Hace diagnosticable un 400 sin registrar payloads ni credenciales."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        recibido = request.headers.get("X-Request-ID", "")
        request.request_id = recibido if ID_SEGURO.fullmatch(recibido) else uuid.uuid4().hex
        response = self.get_response(request)
        response["X-Request-ID"] = request.request_id
        if response.status_code == 400:
            logger.warning(
                "HTTP 400 request_id=%s method=%s path=%s",
                request.request_id,
                request.method,
                request.path,
            )
        return response
