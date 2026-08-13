from django.shortcuts import redirect
from django.urls import reverse


class CambioClaveInicialMiddleware:
    RUTAS_EXENTAS = ("/api/", "/static/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario = getattr(request, "user", None)
        if usuario and usuario.is_authenticated and usuario.debe_cambiar_clave:
            ruta_cambio = reverse("monitoreo:cambiar_clave_inicial")
            ruta_logout = reverse("monitoreo:logout")
            if (
                request.path not in {ruta_cambio, ruta_logout}
                and not request.path.startswith(self.RUTAS_EXENTAS)
            ):
                return redirect(ruta_cambio)
        return self.get_response(request)
