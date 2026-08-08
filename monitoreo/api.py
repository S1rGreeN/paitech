from django.contrib.auth import authenticate
from django.core.exceptions import PermissionDenied, ValidationError as DjangoValidationError
from decimal import Decimal

from django.db.models import Avg
from django.db import connection
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    Especie,
    JornadaRegistro,
    MedicionAgua,
    MovimientoPoblacion,
    MuestraBiometrica,
    Piscina,
)
from .semaforo import evaluar_agua
from .services import (
    ConflictoVersion,
    anular_movimiento,
    anular_jornada,
    calcular_poblacion_teorica,
    corregir_jornada,
    corregir_movimiento,
    crear_jornada,
    crear_movimiento,
    perfil_de,
)


class AguaSerializer(serializers.Serializer):
    ph = serializers.DecimalField(max_digits=4, decimal_places=2, min_value=0, max_value=14)
    nitrato = serializers.DecimalField(max_digits=10, decimal_places=3, min_value=0)
    nitrito = serializers.DecimalField(max_digits=10, decimal_places=3, min_value=0)
    amonio = serializers.DecimalField(max_digits=10, decimal_places=3, min_value=0)


class PezSerializer(serializers.Serializer):
    peso_gramos = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"))
    talla_centimetros = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"))


class JornadaEscrituraSerializer(serializers.Serializer):
    id = serializers.UUIDField(required=False)
    piscina = serializers.UUIDField()
    capturada_en = serializers.DateTimeField()
    poblacion_estimada = serializers.IntegerField(min_value=0)
    observaciones = serializers.CharField(required=False, allow_blank=True, default="")
    dispositivo_id = serializers.CharField(required=False, allow_blank=True, max_length=120, default="")
    version = serializers.IntegerField(required=False, min_value=1)
    motivo_correccion = serializers.CharField(required=False, allow_blank=True, default="")
    agua = AguaSerializer(required=False, allow_null=True)
    peces = PezSerializer(many=True, required=False, default=list)

    def validate(self, attrs):
        if attrs.get("agua") is None and not attrs.get("peces"):
            raise serializers.ValidationError("La jornada requiere agua, biometría o ambos bloques.")
        return attrs


class AnulacionSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    motivo = serializers.CharField(min_length=3, max_length=1000)


class MovimientoEscrituraSerializer(serializers.Serializer):
    id = serializers.UUIDField(required=False)
    tipo = serializers.ChoiceField(choices=MovimientoPoblacion.Tipo.choices)
    cantidad = serializers.IntegerField(min_value=1)
    piscina_origen = serializers.UUIDField(required=False, allow_null=True)
    piscina_destino = serializers.UUIDField(required=False, allow_null=True)
    ocurrido_en = serializers.DateTimeField()
    observaciones = serializers.CharField(required=False, allow_blank=True, default="")
    version = serializers.IntegerField(required=False, min_value=1)
    motivo_correccion = serializers.CharField(required=False, allow_blank=True, default="")


def _errores_django(error):
    if hasattr(error, "message_dict"):
        return error.message_dict
    return {"detail": getattr(error, "messages", [str(error)])}


def _respuesta_error(error):
    if isinstance(error, ConflictoVersion):
        return Response({"detail": str(error), "codigo": "conflicto_version"}, status=status.HTTP_409_CONFLICT)
    if isinstance(error, PermissionDenied):
        return Response({"detail": str(error)}, status=status.HTTP_403_FORBIDDEN)
    if isinstance(error, DjangoValidationError):
        return Response(_errores_django(error), status=status.HTTP_400_BAD_REQUEST)
    raise error


def _autor_json(autor):
    return {
        "id": autor.id,
        "nombre": autor.nickname,
        "correo": autor.user.email,
    }


def jornada_json(jornada, incluir_advertencia=True):
    try:
        agua_obj = jornada.agua
    except MedicionAgua.DoesNotExist:
        agua = None
    else:
        agua = {
            "ph": str(agua_obj.ph),
            "nitrato": str(agua_obj.nitrato),
            "nitrito": str(agua_obj.nitrito),
            "amonio": str(agua_obj.amonio),
        }
    try:
        peces_qs = jornada.muestra_biometrica.peces.all()
    except MuestraBiometrica.DoesNotExist:
        peces = []
        resumen = None
    else:
        peces = [
            {
                "id": str(pez.id),
                "orden": pez.orden,
                "peso_gramos": str(pez.peso_gramos),
                "talla_centimetros": str(pez.talla_centimetros),
            }
            for pez in peces_qs
        ]
        agregados = peces_qs.aggregate(
            peso_promedio=Avg("peso_gramos"),
            talla_promedio=Avg("talla_centimetros"),
        )
        resumen = {
            "cantidad": len(peces),
            "peso_promedio": str(agregados["peso_promedio"]) if agregados["peso_promedio"] is not None else None,
            "talla_promedio": str(agregados["talla_promedio"]) if agregados["talla_promedio"] is not None else None,
        }
    resultado = {
        "id": str(jornada.id),
        "piscina": str(jornada.piscina_id),
        "piscina_codigo": jornada.piscina.codigo,
        "especie": jornada.piscina.especie.nombre_comun if jornada.piscina.especie else None,
        "autor": _autor_json(jornada.autor),
        "capturada_en": jornada.capturada_en.isoformat(),
        "recibida_en": jornada.recibida_en.isoformat(),
        "poblacion_estimada": jornada.poblacion_estimada,
        "observaciones": jornada.observaciones,
        "fuente": jornada.fuente,
        "dispositivo_id": jornada.dispositivo_id,
        "estado": jornada.estado,
        "version": jornada.version,
        "agua": agua,
        "peces": peces,
        "resumen_biometrico": resumen,
    }
    if incluir_advertencia:
        teorica = calcular_poblacion_teorica(
            jornada.piscina,
            hasta=jornada.capturada_en,
            excluir_jornada=jornada.id,
        )
        resultado["poblacion_teorica_antes"] = teorica
        resultado["diferencia_poblacion"] = (
            jornada.poblacion_estimada - teorica if teorica is not None else None
        )
    return resultado


def movimiento_json(movimiento):
    return {
        "id": str(movimiento.id),
        "tipo": movimiento.tipo,
        "cantidad": movimiento.cantidad,
        "piscina_origen": str(movimiento.piscina_origen_id) if movimiento.piscina_origen_id else None,
        "piscina_destino": str(movimiento.piscina_destino_id) if movimiento.piscina_destino_id else None,
        "autor": _autor_json(movimiento.autor),
        "ocurrido_en": movimiento.ocurrido_en.isoformat(),
        "observaciones": movimiento.observaciones,
        "estado": movimiento.estado,
        "version": movimiento.version,
    }


class LoginApiView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = str(request.data.get("email", "")).strip().lower()
        password = request.data.get("password", "")
        if not email or not password:
            return Response({"detail": "Correo y contraseña son obligatorios."}, status=status.HTTP_400_BAD_REQUEST)
        usuario = authenticate(request=request, username=email, password=password)
        if usuario is None or not usuario.is_active:
            return Response({"detail": "Credenciales inválidas."}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            perfil = perfil_de(usuario)
        except PermissionDenied as error:
            return _respuesta_error(error)
        token, _ = Token.objects.get_or_create(user=usuario)
        return Response(
            {
                "token": token.key,
                "usuario": {
                    "id": usuario.id,
                    "correo": usuario.email,
                    "nombre": usuario.get_full_name() or perfil.nickname,
                    "rol": perfil.rol,
                    "comunidad": {"codigo": perfil.comunidad.codigo, "nombre": perfil.comunidad.nombre},
                },
            }
        )


class HealthApiView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return Response({"status": "ok", "database": "ok"})


class LogoutApiView(APIView):
    def post(self, request):
        if request.auth:
            request.auth.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeApiView(APIView):
    def get(self, request):
        perfil = perfil_de(request.user)
        return Response(
            {
                "id": request.user.id,
                "correo": request.user.email,
                "nombre": request.user.get_full_name() or perfil.nickname,
                "rol": perfil.rol,
                "comunidad": {"codigo": perfil.comunidad.codigo, "nombre": perfil.comunidad.nombre},
            }
        )


class EspeciesApiView(APIView):
    def get(self, request):
        perfil_de(request.user)
        especies = Especie.objects.filter(activa=True)
        return Response([{"id": item.id, "nombre_comun": item.nombre_comun, "nombre_cientifico": item.nombre_cientifico} for item in especies])


class PiscinasApiView(APIView):
    def get(self, request):
        perfil = perfil_de(request.user)
        piscinas = Piscina.objects.filter(comunidad=perfil.comunidad, activa=True).select_related("especie")
        return Response(
            [
                {
                    "id": str(item.id),
                    "codigo": item.codigo,
                    "nombre": item.nombre,
                    "tipo": item.tipo,
                    "descripcion": item.descripcion,
                    "area_m2": str(item.area_m2) if item.area_m2 is not None else None,
                    "especie": ({"id": item.especie_id, "nombre_comun": item.especie.nombre_comun} if item.especie else None),
                    "poblacion_teorica_actual": calcular_poblacion_teorica(item),
                }
                for item in piscinas
            ]
        )


class JornadasApiView(APIView):
    def get(self, request):
        perfil = perfil_de(request.user)
        jornadas = (
            JornadaRegistro.objects.filter(autor=perfil)
            .select_related("piscina", "piscina__especie", "autor", "autor__user")
            .prefetch_related("muestra_biometrica__peces")
        )
        return Response([jornada_json(item) for item in jornadas[:200]])

    def post(self, request):
        serializer = JornadaEscrituraSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        piscina = get_object_or_404(Piscina, pk=datos.pop("piscina"))
        datos.pop("version", None)
        datos.pop("motivo_correccion", None)
        try:
            jornada, creada = crear_jornada(
                actor=request.user,
                piscina=piscina,
                jornada_id=datos.pop("id", None),
                fuente=JornadaRegistro.Fuente.ANDROID,
                **datos,
            )
        except (ConflictoVersion, PermissionDenied, DjangoValidationError) as error:
            return _respuesta_error(error)
        return Response(jornada_json(jornada), status=status.HTTP_201_CREATED if creada else status.HTTP_200_OK)


class JornadaDetalleApiView(APIView):
    def _obtener(self, request, jornada_id):
        perfil = perfil_de(request.user)
        consulta = JornadaRegistro.objects.select_related("piscina", "piscina__especie", "autor", "autor__user")
        if not request.user.is_superuser:
            consulta = consulta.filter(autor=perfil)
        return get_object_or_404(consulta, pk=jornada_id)

    def get(self, request, jornada_id):
        return Response(jornada_json(self._obtener(request, jornada_id)))

    def put(self, request, jornada_id):
        jornada = self._obtener(request, jornada_id)
        serializer = JornadaEscrituraSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        version = datos.pop("version", None)
        if version is None:
            return Response({"version": ["La versión actual es obligatoria para corregir."]}, status=status.HTTP_400_BAD_REQUEST)
        piscina = get_object_or_404(Piscina, pk=datos.pop("piscina"))
        datos.pop("id", None)
        motivo = datos.pop("motivo_correccion", "")
        try:
            jornada = corregir_jornada(
                jornada=jornada,
                actor=request.user,
                version_esperada=version,
                piscina=piscina,
                motivo=motivo,
                **datos,
            )
        except (ConflictoVersion, PermissionDenied, DjangoValidationError) as error:
            return _respuesta_error(error)
        return Response(jornada_json(jornada))


class JornadaAnularApiView(APIView):
    def post(self, request, jornada_id):
        perfil = perfil_de(request.user)
        consulta = JornadaRegistro.objects.all() if request.user.is_superuser else JornadaRegistro.objects.filter(autor=perfil)
        jornada = get_object_or_404(consulta, pk=jornada_id)
        serializer = AnulacionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            jornada = anular_jornada(jornada=jornada, actor=request.user, version_esperada=serializer.validated_data["version"], motivo=serializer.validated_data["motivo"])
        except (ConflictoVersion, PermissionDenied, DjangoValidationError) as error:
            return _respuesta_error(error)
        return Response(jornada_json(jornada))


class MovimientosApiView(APIView):
    def get(self, request):
        perfil = perfil_de(request.user)
        movimientos = MovimientoPoblacion.objects.filter(autor=perfil).select_related("autor", "autor__user")[:200]
        return Response([movimiento_json(item) for item in movimientos])

    def post(self, request):
        serializer = MovimientoEscrituraSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        datos.pop("version", None)
        datos.pop("motivo_correccion", None)
        origen_id = datos.pop("piscina_origen", None)
        destino_id = datos.pop("piscina_destino", None)
        origen = get_object_or_404(Piscina, pk=origen_id) if origen_id else None
        destino = get_object_or_404(Piscina, pk=destino_id) if destino_id else None
        try:
            movimiento, creado = crear_movimiento(
                actor=request.user,
                piscina_origen=origen,
                piscina_destino=destino,
                movimiento_id=datos.pop("id", None),
                **datos,
            )
        except (PermissionDenied, DjangoValidationError) as error:
            return _respuesta_error(error)
        return Response(movimiento_json(movimiento), status=status.HTTP_201_CREATED if creado else status.HTTP_200_OK)


class MovimientoDetalleApiView(APIView):
    def _obtener(self, request, movimiento_id):
        perfil = perfil_de(request.user)
        consulta = MovimientoPoblacion.objects.select_related("autor", "autor__user")
        if not request.user.is_superuser:
            consulta = consulta.filter(autor=perfil)
        return get_object_or_404(consulta, pk=movimiento_id)

    def get(self, request, movimiento_id):
        return Response(movimiento_json(self._obtener(request, movimiento_id)))

    def put(self, request, movimiento_id):
        movimiento = self._obtener(request, movimiento_id)
        serializer = MovimientoEscrituraSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        version = datos.pop("version", None)
        if version is None:
            return Response({"version": ["La versión actual es obligatoria para corregir."]}, status=status.HTTP_400_BAD_REQUEST)
        origen_id = datos.pop("piscina_origen", None)
        destino_id = datos.pop("piscina_destino", None)
        origen = get_object_or_404(Piscina, pk=origen_id) if origen_id else None
        destino = get_object_or_404(Piscina, pk=destino_id) if destino_id else None
        datos.pop("id", None)
        motivo = datos.pop("motivo_correccion", "")
        try:
            movimiento = corregir_movimiento(
                movimiento=movimiento,
                actor=request.user,
                version_esperada=version,
                piscina_origen=origen,
                piscina_destino=destino,
                motivo=motivo,
                **datos,
            )
        except (ConflictoVersion, PermissionDenied, DjangoValidationError) as error:
            return _respuesta_error(error)
        return Response(movimiento_json(movimiento))


class MovimientoAnularApiView(APIView):
    def post(self, request, movimiento_id):
        perfil = perfil_de(request.user)
        consulta = MovimientoPoblacion.objects.all() if request.user.is_superuser else MovimientoPoblacion.objects.filter(autor=perfil)
        movimiento = get_object_or_404(consulta, pk=movimiento_id)
        serializer = AnulacionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            movimiento = anular_movimiento(
                movimiento=movimiento,
                actor=request.user,
                version_esperada=serializer.validated_data["version"],
                motivo=serializer.validated_data["motivo"],
            )
        except (ConflictoVersion, PermissionDenied, DjangoValidationError) as error:
            return _respuesta_error(error)
        return Response(movimiento_json(movimiento))


class SemaforosApiView(APIView):
    def get(self, request):
        perfil = perfil_de(request.user)
        piscinas = Piscina.objects.filter(comunidad=perfil.comunidad, activa=True, tipo=Piscina.Tipo.PECES).select_related("especie")
        resultado = []
        for piscina in piscinas:
            jornada = (
                JornadaRegistro.objects.filter(
                    piscina=piscina,
                    estado=JornadaRegistro.Estado.COMPLETA,
                    agua__isnull=False,
                )
                .select_related("agua", "autor", "autor__user")
                .order_by("-capturada_en", "-creada_en")
                .first()
            )
            resultado.append(
                {
                    "piscina": {"id": str(piscina.id), "codigo": piscina.codigo, "nombre": piscina.nombre},
                    "jornada": jornada_json(jornada, incluir_advertencia=False) if jornada else None,
                    "semaforo": evaluar_agua(jornada.agua) if jornada else None,
                }
            )
        return Response(resultado)
