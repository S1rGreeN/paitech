from io import StringIO

from django.conf import settings
from django.core.management import call_command
from django.http import JsonResponse
from django.utils.crypto import constant_time_compare
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


@never_cache
@require_GET
def mantenimiento(request):
    """Retención existente de seguridad y sesiones vencidas, invocada por Vercel."""
    secreto = settings.CRON_SECRET
    if not secreto:
        return JsonResponse({"detail": "Mantenimiento no configurado."}, status=503)
    if not constant_time_compare(request.headers.get("Authorization", ""), f"Bearer {secreto}"):
        response = JsonResponse({"detail": "No autorizado."}, status=401)
        response["WWW-Authenticate"] = "Bearer"
        return response

    # Reutiliza los comandos: no borra usuarios ni registros productivos.
    salida = StringIO()
    call_command("limpiar_eventos_seguridad", stdout=salida)
    call_command("clearsessions", stdout=salida)
    return JsonResponse({"status": "ok"})
