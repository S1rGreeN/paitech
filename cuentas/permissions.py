from rest_framework.exceptions import PermissionDenied


class ClaveActualizada:
    def has_permission(self, request, view):
        usuario = request.user
        if usuario and usuario.is_authenticated and usuario.debe_cambiar_clave:
            raise PermissionDenied(
                {
                    "detail": "Debes cambiar la contraseña temporal antes de continuar.",
                    "codigo": "cambio_clave_requerido",
                }
            )
        return True
