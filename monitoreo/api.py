from django.contrib.auth import authenticate
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError as DjangoValidationError
from decimal import Decimal

from django.db.models import Avg, Q
from django.db import connection, transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from cuentas.models import EventoSeguridad, TokenDispositivo
from cuentas.security import (
    estado_bloqueo,
    normalizar_email,
    obtener_ip,
    registrar_evento,
    registrar_login_exitoso,
    registrar_login_fallido,
)

from .calidad_agua import (
    validar_amoniaco_total_kit,
    validar_nitrato_kit,
    validar_nitrito_kit,
    validar_ph_kit,
)
from .models import (
    CicloProductivo,
    DispositivoSensor,
    Especie,
    JornadaRegistro,
    LecturaSensor,
    MedicionAgua,
    MovimientoPoblacion,
    MuestraBiometrica,
    Piscina,
)
from .recordatorios import recordatorios_piscina
from .prediccion import calcular_prediccion
from .sensor_authentication import SensorAuthentication
from .semaforo import evaluar_agua
from .services import (
    ConflictoVersion,
    anular_movimiento,
    anular_jornada,
    calcular_poblacion_teorica,
    cerrar_ciclo,
    corregir_jornada,
    corregir_movimiento,
    crear_ciclo,
    crear_jornada,
    crear_movimiento,
    perfil_de,
)


class AguaSerializer(serializers.Serializer):
    ph = serializers.DecimalField(max_digits=4, decimal_places=2, min_value=0, max_value=14)
    nitrato = serializers.DecimalField(max_digits=10, decimal_places=3, min_value=0)
    nitrito = serializers.DecimalField(max_digits=10, decimal_places=3, min_value=0)
    amoniaco_total = serializers.DecimalField(max_digits=10, decimal_places=3, min_value=0)

    @staticmethod
    def _validar(valor, validador):
        try:
            validador(valor)
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.messages) from error
        return valor

    def validate_ph(self, valor):
        return self._validar(valor, validar_ph_kit)

    def validate_nitrato(self, valor):
        return self._validar(valor, validar_nitrato_kit)

    def validate_nitrito(self, valor):
        return self._validar(valor, validar_nitrito_kit)

    def validate_amoniaco_total(self, valor):
        return self._validar(valor, validar_amoniaco_total_kit)


class PezSerializer(serializers.Serializer):
    peso_gramos = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"))
    talla_centimetros = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"))


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(
        max_length=128,
        trim_whitespace=False,
        write_only=True,
    )
    dispositivo_id = serializers.CharField(min_length=10, max_length=128)
    nombre_dispositivo = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=160
    )


class CambioClaveSerializer(serializers.Serializer):
    password_actual = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)
    password_nuevo = serializers.CharField(min_length=8, max_length=32, trim_whitespace=False, write_only=True)
    confirmacion = serializers.CharField(min_length=8, max_length=32, trim_whitespace=False, write_only=True)

    def validate(self, attrs):
        usuario = self.context["request"].user
        if not usuario.check_password(attrs["password_actual"]):
            raise serializers.ValidationError({"password_actual": "La contraseña actual no es correcta."})
        if attrs["password_nuevo"] != attrs["confirmacion"]:
            raise serializers.ValidationError({"confirmacion": "Las contraseñas no coinciden."})
        try:
            validate_password(attrs["password_nuevo"], user=usuario)
        except DjangoValidationError as error:
            raise serializers.ValidationError({"password_nuevo": error.messages}) from error
        return attrs


class JornadaEscrituraSerializer(serializers.Serializer):
    id = serializers.UUIDField(required=False)
    piscina = serializers.UUIDField()
    ciclo = serializers.UUIDField(required=False, allow_null=True)
    capturada_en = serializers.DateTimeField()
    poblacion_estimada = serializers.IntegerField(min_value=0)
    observaciones = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=5000
    )
    dispositivo_id = serializers.CharField(required=False, allow_blank=True, max_length=120, default="")
    version = serializers.IntegerField(required=False, min_value=1)
    motivo_correccion = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=1000
    )
    agua = AguaSerializer(required=False, allow_null=True)
    peces = PezSerializer(many=True, required=False, default=list, max_length=2000)

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
    ciclo_origen = serializers.UUIDField(required=False, allow_null=True)
    ciclo_destino = serializers.UUIDField(required=False, allow_null=True)
    ocurrido_en = serializers.DateTimeField()
    observaciones = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=5000
    )
    version = serializers.IntegerField(required=False, min_value=1)
    motivo_correccion = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=1000
    )


class PrediccionCacheSerializer(serializers.Serializer):
    prediccion_poblacion_final = serializers.IntegerField(min_value=0)
    prediccion_min = serializers.IntegerField(min_value=0)
    prediccion_max = serializers.IntegerField(min_value=0)
    prediccion_tasa = serializers.DecimalField(max_digits=8, decimal_places=6, min_value=0)
    prediccion_ciclos_usados = serializers.IntegerField(min_value=1)
    prediccion_confianza = serializers.ChoiceField(
        choices=CicloProductivo.ConfianzaPrediccion.choices
    )
    prediccion_metodo_version = serializers.CharField(max_length=80)
    prediccion_calculada_en = serializers.DateTimeField()
    prediccion_datos_hasta = serializers.DateTimeField()


class CicloAperturaSerializer(serializers.Serializer):
    id = serializers.UUIDField(required=False)
    piscina = serializers.UUIDField()
    iniciado_en = serializers.DateTimeField()
    poblacion_inicial = serializers.IntegerField(min_value=1)
    duracion_estimada_meses = serializers.IntegerField(
        min_value=1, max_value=60, required=False, allow_null=True
    )
    observaciones_apertura = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=5000
    )
    dispositivo_id = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=120
    )
    prediccion_cache = PrediccionCacheSerializer(required=False, allow_null=True)


class CicloCierreSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    cerrado_en = serializers.DateTimeField()
    destino_cierre = serializers.ChoiceField(choices=CicloProductivo.DestinoCierre.choices)
    poblacion_final = serializers.IntegerField(min_value=0)
    peso_total_cosechado_kg = serializers.DecimalField(
        max_digits=12, decimal_places=3, min_value=0, required=False, allow_null=True
    )
    observaciones_cierre = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=5000
    )
    piscina_destino_cierre = serializers.UUIDField(required=False, allow_null=True)


class LecturaSensorSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    medida_en = serializers.DateTimeField()
    oxigeno_disuelto_mg_l = serializers.DecimalField(
        max_digits=8, decimal_places=3, min_value=0, max_value=50,
        required=False, allow_null=True
    )
    temperatura_c = serializers.DecimalField(
        max_digits=7, decimal_places=3, min_value=-10, max_value=60,
        required=False, allow_null=True
    )
    turbidez_ntu = serializers.DecimalField(
        max_digits=12, decimal_places=3, min_value=0, max_value=100000,
        required=False, allow_null=True
    )
    calidad = serializers.ChoiceField(
        choices=LecturaSensor.Calidad.choices, required=False
    )
    detalle_calidad = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=500
    )
    metadatos = serializers.JSONField(required=False, default=dict)

    def validate(self, attrs):
        campos = (
            "oxigeno_disuelto_mg_l",
            "temperatura_c",
            "turbidez_ntu",
        )
        presentes = sum(attrs.get(campo) is not None for campo in campos)
        if presentes == 0:
            raise serializers.ValidationError("La lectura requiere al menos un valor.")
        calculada = (
            LecturaSensor.Calidad.COMPLETA
            if presentes == 3
            else LecturaSensor.Calidad.PARCIAL
        )
        if attrs.get("calidad") not in (None, LecturaSensor.Calidad.INVALIDA, calculada):
            raise serializers.ValidationError({"calidad": f"Debe ser {calculada}."})
        attrs["calidad"] = attrs.get("calidad") or calculada
        return attrs


class LoteLecturasSensorSerializer(serializers.Serializer):
    lecturas = LecturaSensorSerializer(many=True, min_length=1, max_length=1000)


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
            "amoniaco_total": str(agua_obj.amoniaco_total),
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
        "ciclo": str(jornada.ciclo_id) if jornada.ciclo_id else None,
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
        "ciclo_origen": str(movimiento.ciclo_origen_id) if movimiento.ciclo_origen_id else None,
        "ciclo_destino": str(movimiento.ciclo_destino_id) if movimiento.ciclo_destino_id else None,
        "autor": _autor_json(movimiento.autor),
        "ocurrido_en": movimiento.ocurrido_en.isoformat(),
        "observaciones": movimiento.observaciones,
        "estado": movimiento.estado,
        "version": movimiento.version,
    }


def ciclo_json(ciclo):
    return {
        "id": str(ciclo.id),
        "piscina": str(ciclo.piscina_id),
        "piscina_codigo": ciclo.piscina.codigo,
        "especie": {
            "id": ciclo.especie_id,
            "nombre_comun": ciclo.especie.nombre_comun,
            "nombre_cientifico": ciclo.especie.nombre_cientifico,
        },
        "numero": ciclo.numero,
        "estado": ciclo.estado,
        "iniciado_en": ciclo.iniciado_en.isoformat(),
        "poblacion_inicial": ciclo.poblacion_inicial,
        "duracion_estimada_meses": ciclo.duracion_estimada_meses,
        "observaciones_apertura": ciclo.observaciones_apertura,
        "autor_apertura": _autor_json(ciclo.autor_apertura),
        "fuente": ciclo.fuente,
        "dispositivo_id": ciclo.dispositivo_id,
        "cerrado_en": ciclo.cerrado_en.isoformat() if ciclo.cerrado_en else None,
        "destino_cierre": ciclo.destino_cierre or None,
        "poblacion_final": ciclo.poblacion_final,
        "peso_total_cosechado_kg": (
            str(ciclo.peso_total_cosechado_kg)
            if ciclo.peso_total_cosechado_kg is not None
            else None
        ),
        "observaciones_cierre": ciclo.observaciones_cierre,
        "piscina_destino_cierre": (
            str(ciclo.piscina_destino_cierre_id)
            if ciclo.piscina_destino_cierre_id
            else None
        ),
        "autor_cierre": _autor_json(ciclo.autor_cierre) if ciclo.autor_cierre else None,
        "prediccion": {
            "poblacion_final": ciclo.prediccion_poblacion_final,
            "minimo": ciclo.prediccion_min,
            "maximo": ciclo.prediccion_max,
            "tasa": str(ciclo.prediccion_tasa) if ciclo.prediccion_tasa is not None else None,
            "ciclos_usados": ciclo.prediccion_ciclos_usados,
            "confianza": ciclo.prediccion_confianza,
            "metodo_version": ciclo.prediccion_metodo_version,
            "calculada_en": (
                ciclo.prediccion_calculada_en.isoformat()
                if ciclo.prediccion_calculada_en
                else None
            ),
            "datos_hasta": (
                ciclo.prediccion_datos_hasta.isoformat()
                if ciclo.prediccion_datos_hasta
                else None
            ),
            "origen": ciclo.prediccion_origen,
        },
        "version": ciclo.version,
    }


def recordatorios_json(piscina):
    resultado = recordatorios_piscina(piscina)
    ciclo = resultado.pop("ciclo")
    resultado["ciclo_id"] = str(ciclo.id) if ciclo else None
    return resultado


class LoginApiView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = normalizar_email(serializer.validated_data["email"])
        password = serializer.validated_data["password"]
        dispositivo_id = serializer.validated_data["dispositivo_id"]
        nombre_dispositivo = serializer.validated_data["nombre_dispositivo"]
        ip = obtener_ip(request)
        if estado_bloqueo(email, ip):
            return Response(
                {"detail": "No fue posible iniciar sesión. Intenta nuevamente más tarde."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        usuario = authenticate(request=request, username=email, password=password)
        if usuario is None or not usuario.is_active:
            bloqueo = registrar_login_fallido(email, ip)
            return Response(
                {"detail": "No fue posible iniciar sesión. Verifica los datos o intenta más tarde."},
                status=(status.HTTP_429_TOO_MANY_REQUESTS if bloqueo else status.HTTP_401_UNAUTHORIZED),
            )
        try:
            perfil = perfil_de(usuario)
        except PermissionDenied:
            bloqueo = registrar_login_fallido(email, ip)
            return Response(
                {"detail": "No fue posible iniciar sesión. Verifica los datos o intenta más tarde."},
                status=(status.HTTP_429_TOO_MANY_REQUESTS if bloqueo else status.HTTP_401_UNAUTHORIZED),
            )
        token, credencial = TokenDispositivo.emitir(
            usuario=usuario,
            dispositivo_id=dispositivo_id,
            nombre_dispositivo=nombre_dispositivo,
        )
        registrar_login_exitoso(
            usuario, ip, canal="android", dispositivo_id=dispositivo_id
        )
        return Response(
            {
                "token": credencial,
                "expira_en": token.expira_en.isoformat(),
                "debe_cambiar_clave": usuario.debe_cambiar_clave,
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
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if isinstance(request.auth, TokenDispositivo):
            request.auth.revocar()
        registrar_evento(
            EventoSeguridad.Tipo.LOGOUT,
            usuario=request.user,
            ip=obtener_ip(request),
            detalle={"canal": "android"},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class CambioClaveApiView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CambioClaveSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        usuario = request.user
        usuario.set_password(serializer.validated_data["password_nuevo"])
        usuario.debe_cambiar_clave = False
        usuario._cambio_clave_confirmado = True
        usuario.save(update_fields=["password", "debe_cambiar_clave"])
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
        piscinas = Piscina.objects.filter(
            comunidad=perfil.comunidad,
            activa=True,
            tipo=Piscina.Tipo.PECES,
        ).select_related("especie")
        resultado = []
        for item in piscinas:
            ciclo_activo = item.ciclos.filter(
                estado=CicloProductivo.Estado.ACTIVO
            ).select_related("especie", "autor_apertura", "autor_apertura__user").first()
            resultado.append(
                {
                    "id": str(item.id),
                    "codigo": item.codigo,
                    "nombre": item.nombre,
                    "tipo": item.tipo,
                    "descripcion": item.descripcion,
                    "area_m2": str(item.area_m2) if item.area_m2 is not None else None,
                    "especie": ({"id": item.especie_id, "nombre_comun": item.especie.nombre_comun} if item.especie else None),
                    "poblacion_teorica_actual": calcular_poblacion_teorica(item),
                    "ciclo_activo": ciclo_json(ciclo_activo) if ciclo_activo else None,
                    "recordatorios": recordatorios_json(item),
                }
            )
        return Response(resultado)


class CiclosApiView(APIView):
    def get(self, request):
        perfil = perfil_de(request.user)
        ciclos = (
            CicloProductivo.objects.filter(piscina__comunidad=perfil.comunidad)
            .select_related(
                "piscina",
                "especie",
                "autor_apertura",
                "autor_apertura__user",
                "autor_cierre",
                "autor_cierre__user",
            )
            .order_by("-iniciado_en")[:200]
        )
        return Response([ciclo_json(item) for item in ciclos])

    def post(self, request):
        serializer = CicloAperturaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        piscina = get_object_or_404(Piscina, pk=datos.pop("piscina"))
        try:
            ciclo, creado = crear_ciclo(
                actor=request.user,
                piscina=piscina,
                ciclo_id=datos.pop("id", None),
                prediccion_cache=datos.pop("prediccion_cache", None),
                fuente=CicloProductivo.Fuente.ANDROID,
                **datos,
            )
        except (ConflictoVersion, PermissionDenied, DjangoValidationError) as error:
            return _respuesta_error(error)
        return Response(
            ciclo_json(ciclo),
            status=status.HTTP_201_CREATED if creado else status.HTTP_200_OK,
        )


class CicloDetalleApiView(APIView):
    def _obtener(self, request, ciclo_id):
        perfil = perfil_de(request.user)
        return get_object_or_404(
            CicloProductivo.objects.filter(piscina__comunidad=perfil.comunidad)
            .select_related(
                "piscina",
                "especie",
                "autor_apertura",
                "autor_apertura__user",
                "autor_cierre",
                "autor_cierre__user",
            ),
            pk=ciclo_id,
        )

    def get(self, request, ciclo_id):
        return Response(ciclo_json(self._obtener(request, ciclo_id)))


class CicloCerrarApiView(CicloDetalleApiView):
    def post(self, request, ciclo_id):
        ciclo = self._obtener(request, ciclo_id)
        serializer = CicloCierreSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        piscina_destino_id = datos.pop("piscina_destino_cierre", None)
        piscina_destino = (
            get_object_or_404(Piscina, pk=piscina_destino_id)
            if piscina_destino_id
            else None
        )
        try:
            ciclo, _ = cerrar_ciclo(
                ciclo=ciclo,
                actor=request.user,
                version_esperada=datos.pop("version"),
                piscina_destino_cierre=piscina_destino,
                **datos,
            )
        except (ConflictoVersion, PermissionDenied, DjangoValidationError) as error:
            return _respuesta_error(error)
        return Response(ciclo_json(ciclo))


class PrediccionCicloApiView(APIView):
    def get(self, request):
        perfil = perfil_de(request.user)
        piscina = get_object_or_404(
            Piscina,
            pk=request.query_params.get("piscina"),
            comunidad=perfil.comunidad,
            activa=True,
            tipo=Piscina.Tipo.PECES,
        )
        try:
            poblacion = int(request.query_params.get("poblacion_inicial", ""))
        except ValueError:
            return Response(
                {"poblacion_inicial": ["Debe ser un entero positivo."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if poblacion < 1:
            return Response(
                {"poblacion_inicial": ["Debe ser mayor que cero."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        prediccion = calcular_prediccion(piscina, poblacion)
        return Response(
            {
                clave.removeprefix("prediccion_"): (
                    valor.isoformat() if hasattr(valor, "isoformat") else str(valor)
                    if isinstance(valor, Decimal)
                    else valor
                )
                for clave, valor in prediccion.items()
            }
        )


class JornadasApiView(APIView):
    def get(self, request):
        perfil = perfil_de(request.user)
        jornadas = (
            JornadaRegistro.objects.filter(piscina__comunidad=perfil.comunidad)
            .select_related("piscina", "piscina__especie", "ciclo", "autor", "autor__user")
            .prefetch_related("muestra_biometrica__peces")
        )
        return Response([jornada_json(item) for item in jornadas[:200]])

    def post(self, request):
        serializer = JornadaEscrituraSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        piscina = get_object_or_404(Piscina, pk=datos.pop("piscina"))
        ciclo_id = datos.pop("ciclo", None)
        ciclo = get_object_or_404(CicloProductivo, pk=ciclo_id) if ciclo_id else None
        datos.pop("version", None)
        datos.pop("motivo_correccion", None)
        try:
            jornada, creada = crear_jornada(
                actor=request.user,
                piscina=piscina,
                ciclo=ciclo,
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
        consulta = JornadaRegistro.objects.filter(
            piscina__comunidad=perfil.comunidad
        ).select_related("piscina", "piscina__especie", "ciclo", "autor", "autor__user")
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
        ciclo_id = datos.pop("ciclo", None)
        ciclo = get_object_or_404(CicloProductivo, pk=ciclo_id) if ciclo_id else None
        datos.pop("id", None)
        motivo = datos.pop("motivo_correccion", "")
        try:
            jornada = corregir_jornada(
                jornada=jornada,
                actor=request.user,
                version_esperada=version,
                piscina=piscina,
                ciclo=ciclo,
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
        movimientos = MovimientoPoblacion.objects.filter(
            Q(piscina_origen__comunidad=perfil.comunidad)
            | Q(piscina_destino__comunidad=perfil.comunidad)
        ).select_related("autor", "autor__user")[:200]
        return Response([movimiento_json(item) for item in movimientos])

    def post(self, request):
        serializer = MovimientoEscrituraSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        datos.pop("version", None)
        datos.pop("motivo_correccion", None)
        origen_id = datos.pop("piscina_origen", None)
        destino_id = datos.pop("piscina_destino", None)
        ciclo_origen_id = datos.pop("ciclo_origen", None)
        ciclo_destino_id = datos.pop("ciclo_destino", None)
        origen = get_object_or_404(Piscina, pk=origen_id) if origen_id else None
        destino = get_object_or_404(Piscina, pk=destino_id) if destino_id else None
        ciclo_origen = get_object_or_404(CicloProductivo, pk=ciclo_origen_id) if ciclo_origen_id else None
        ciclo_destino = get_object_or_404(CicloProductivo, pk=ciclo_destino_id) if ciclo_destino_id else None
        try:
            movimiento, creado = crear_movimiento(
                actor=request.user,
                piscina_origen=origen,
                piscina_destino=destino,
                ciclo_origen=ciclo_origen,
                ciclo_destino=ciclo_destino,
                movimiento_id=datos.pop("id", None),
                **datos,
            )
        except (ConflictoVersion, PermissionDenied, DjangoValidationError) as error:
            return _respuesta_error(error)
        return Response(movimiento_json(movimiento), status=status.HTTP_201_CREATED if creado else status.HTTP_200_OK)


class MovimientoDetalleApiView(APIView):
    def _obtener(self, request, movimiento_id):
        perfil = perfil_de(request.user)
        consulta = MovimientoPoblacion.objects.filter(
            Q(piscina_origen__comunidad=perfil.comunidad)
            | Q(piscina_destino__comunidad=perfil.comunidad)
        ).select_related("autor", "autor__user")
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
        ciclo_origen_id = datos.pop("ciclo_origen", None)
        ciclo_destino_id = datos.pop("ciclo_destino", None)
        origen = get_object_or_404(Piscina, pk=origen_id) if origen_id else None
        destino = get_object_or_404(Piscina, pk=destino_id) if destino_id else None
        ciclo_origen = get_object_or_404(CicloProductivo, pk=ciclo_origen_id) if ciclo_origen_id else None
        ciclo_destino = get_object_or_404(CicloProductivo, pk=ciclo_destino_id) if ciclo_destino_id else None
        datos.pop("id", None)
        motivo = datos.pop("motivo_correccion", "")
        try:
            movimiento = corregir_movimiento(
                movimiento=movimiento,
                actor=request.user,
                version_esperada=version,
                piscina_origen=origen,
                piscina_destino=destino,
                ciclo_origen=ciclo_origen,
                ciclo_destino=ciclo_destino,
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


class LecturasSensorLoteApiView(APIView):
    authentication_classes = [SensorAuthentication]
    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        if not settings.SENSORES_HABILITADOS:
            raise NotFound("La telemetría todavía no está habilitada.")
        return super().initial(request, *args, **kwargs)

    def post(self, request):
        serializer = LoteLecturasSensorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dispositivo = request.auth
        creadas = 0
        repetidas = 0
        try:
            with transaction.atomic():
                for datos_originales in serializer.validated_data["lecturas"]:
                    datos = dict(datos_originales)
                    lectura_id = datos.pop("id")
                    existente = LecturaSensor.objects.select_for_update().filter(
                        pk=lectura_id
                    ).first()
                    if existente:
                        campos = (
                            "medida_en",
                            "oxigeno_disuelto_mg_l",
                            "temperatura_c",
                            "turbidez_ntu",
                            "calidad",
                            "detalle_calidad",
                            "metadatos",
                        )
                        if (
                            existente.dispositivo_id != dispositivo.id
                            or any(getattr(existente, campo) != datos.get(campo) for campo in campos)
                        ):
                            raise ConflictoVersion(
                                f"La lectura {lectura_id} ya existe con datos diferentes."
                            )
                        repetidas += 1
                        continue

                    medida_en = datos["medida_en"]
                    ciclo = (
                        CicloProductivo.objects.filter(
                            piscina=dispositivo.piscina,
                            iniciado_en__lte=medida_en,
                        )
                        .filter(
                            Q(estado=CicloProductivo.Estado.ACTIVO)
                            | Q(
                                estado=CicloProductivo.Estado.CERRADO,
                                cerrado_en__gte=medida_en,
                            )
                        )
                        .order_by("-iniciado_en")
                        .first()
                    )
                    lectura = LecturaSensor(
                        id=lectura_id,
                        dispositivo=dispositivo,
                        piscina=dispositivo.piscina,
                        ciclo=ciclo,
                        **datos,
                    )
                    lectura.full_clean()
                    lectura.save()
                    creadas += 1
        except (ConflictoVersion, DjangoValidationError) as error:
            return _respuesta_error(error)
        return Response({"creadas": creadas, "repetidas": repetidas})


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
    LecturaSensor,
    crear_ciclo,
