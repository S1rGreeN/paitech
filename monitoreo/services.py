import json
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (
    Acuicultor,
    AuditoriaCambio,
    JornadaRegistro,
    MedicionAgua,
    MovimientoPoblacion,
    MuestraBiometrica,
    ObservacionPez,
    Piscina,
)


class ConflictoVersion(Exception):
    pass


def _json_seguro(datos):
    return json.loads(json.dumps(datos, default=str))


def perfil_de(usuario):
    try:
        perfil = usuario.perfil_acuicultor
    except Acuicultor.DoesNotExist as exc:
        raise PermissionDenied("El usuario no tiene un perfil de acuicultor.") from exc
    if not perfil.activo or not perfil.comunidad.activa:
        raise PermissionDenied("El perfil o la comunidad están inactivos.")
    return perfil


def snapshot_jornada(jornada):
    datos = {
        "id": jornada.id,
        "piscina": jornada.piscina_id,
        "autor": jornada.autor_id,
        "capturada_en": jornada.capturada_en,
        "poblacion_estimada": jornada.poblacion_estimada,
        "observaciones": jornada.observaciones,
        "fuente": jornada.fuente,
        "dispositivo_id": jornada.dispositivo_id,
        "estado": jornada.estado,
        "version": jornada.version,
    }
    try:
        agua = jornada.agua
    except MedicionAgua.DoesNotExist:
        datos["agua"] = None
    else:
        datos["agua"] = {
            "ph": agua.ph,
            "nitrato": agua.nitrato,
            "nitrito": agua.nitrito,
            "amonio": agua.amonio,
        }
    try:
        muestra = jornada.muestra_biometrica
    except MuestraBiometrica.DoesNotExist:
        datos["peces"] = []
    else:
        datos["peces"] = list(
            muestra.peces.values("id", "orden", "peso_gramos", "talla_centimetros")
        )
    return _json_seguro(datos)


def snapshot_movimiento(movimiento):
    return _json_seguro(
        {
            "id": movimiento.id,
            "tipo": movimiento.tipo,
            "cantidad": movimiento.cantidad,
            "piscina_origen": movimiento.piscina_origen_id,
            "piscina_destino": movimiento.piscina_destino_id,
            "autor": movimiento.autor_id,
            "ocurrido_en": movimiento.ocurrido_en,
            "observaciones": movimiento.observaciones,
            "estado": movimiento.estado,
            "version": movimiento.version,
        }
    )


def _registrar_auditoria(*, entidad, entidad_uuid, accion, actor, version_anterior, version_nueva, antes, despues, motivo=""):
    AuditoriaCambio.objects.create(
        entidad=entidad,
        entidad_uuid=entidad_uuid,
        accion=accion,
        actor=actor,
        version_anterior=version_anterior,
        version_nueva=version_nueva,
        datos_anteriores=antes,
        datos_nuevos=despues,
        motivo=motivo,
    )


def _validar_piscina(perfil, piscina):
    if piscina.comunidad_id != perfil.comunidad_id:
        raise PermissionDenied("La piscina no pertenece a la comunidad del usuario.")
    if not piscina.activa:
        raise ValidationError("La piscina está inactiva.")
    if piscina.tipo != Piscina.Tipo.PECES:
        raise ValidationError("Lombricultura permanece como Próximamente en esta versión.")


def _guardar_bloques(jornada, agua, peces):
    if agua is None and not peces:
        raise ValidationError("Una jornada completa requiere agua, biometría o ambos bloques.")
    if agua is not None:
        medicion = MedicionAgua(jornada=jornada, **agua)
        medicion.full_clean()
        medicion.save()
    if peces:
        muestra = MuestraBiometrica.objects.create(jornada=jornada)
        observaciones = []
        for indice, pez in enumerate(peces, start=1):
            observacion = ObservacionPez(muestra=muestra, orden=indice, **pez)
            observacion.full_clean()
            observaciones.append(observacion)
        ObservacionPez.objects.bulk_create(observaciones)


@transaction.atomic
def crear_jornada(*, actor, piscina, capturada_en, poblacion_estimada, observaciones="", fuente=JornadaRegistro.Fuente.ANDROID, dispositivo_id="", agua=None, peces=None, jornada_id=None):
    perfil = perfil_de(actor)
    _validar_piscina(perfil, piscina)
    if jornada_id:
        existente = JornadaRegistro.objects.select_for_update().filter(pk=jornada_id).first()
        if existente:
            if not existente.puede_modificar(actor):
                raise PermissionDenied("El UUID ya pertenece a otro autor.")
            return existente, False

    jornada = JornadaRegistro(
        id=jornada_id,
        piscina=piscina,
        autor=perfil,
        capturada_en=capturada_en,
        poblacion_estimada=poblacion_estimada,
        observaciones=observaciones,
        fuente=fuente,
        dispositivo_id=dispositivo_id,
        estado=JornadaRegistro.Estado.COMPLETA,
    )
    jornada.full_clean()
    jornada.save()
    _guardar_bloques(jornada, agua, peces or [])
    despues = snapshot_jornada(jornada)
    _registrar_auditoria(
        entidad=AuditoriaCambio.Entidad.JORNADA,
        entidad_uuid=jornada.id,
        accion=AuditoriaCambio.Accion.CREAR,
        actor=actor,
        version_anterior=None,
        version_nueva=1,
        antes=None,
        despues=despues,
    )
    return jornada, True


@transaction.atomic
def corregir_jornada(*, jornada, actor, version_esperada, piscina, capturada_en, poblacion_estimada, observaciones="", dispositivo_id="", agua=None, peces=None, motivo=""):
    jornada = JornadaRegistro.objects.select_for_update().get(pk=jornada.pk)
    if not jornada.puede_modificar(actor):
        raise PermissionDenied("Solo el autor o un administrador pueden corregir la jornada.")
    if jornada.estado == JornadaRegistro.Estado.ANULADA:
        raise ValidationError("Una jornada anulada no puede corregirse.")
    if jornada.version != version_esperada:
        raise ConflictoVersion(f"La jornada está en la versión {jornada.version}; se recibió la {version_esperada}.")
    perfil = perfil_de(actor)
    _validar_piscina(perfil, piscina)
    antes = snapshot_jornada(jornada)
    version_anterior = jornada.version
    jornada.piscina = piscina
    jornada.capturada_en = capturada_en
    jornada.poblacion_estimada = poblacion_estimada
    jornada.observaciones = observaciones
    jornada.dispositivo_id = dispositivo_id
    jornada.version += 1
    jornada.full_clean()
    jornada.save()
    MedicionAgua.objects.filter(jornada=jornada).delete()
    MuestraBiometrica.objects.filter(jornada=jornada).delete()
    _guardar_bloques(jornada, agua, peces or [])
    despues = snapshot_jornada(jornada)
    _registrar_auditoria(
        entidad=AuditoriaCambio.Entidad.JORNADA,
        entidad_uuid=jornada.id,
        accion=AuditoriaCambio.Accion.CORREGIR,
        actor=actor,
        version_anterior=version_anterior,
        version_nueva=jornada.version,
        antes=antes,
        despues=despues,
        motivo=motivo,
    )
    return jornada


@transaction.atomic
def anular_jornada(*, jornada, actor, version_esperada, motivo):
    jornada = JornadaRegistro.objects.select_for_update().get(pk=jornada.pk)
    if not jornada.puede_modificar(actor):
        raise PermissionDenied("Solo el autor o un administrador pueden anular la jornada.")
    if not motivo.strip():
        raise ValidationError("El motivo de anulación es obligatorio.")
    if jornada.version != version_esperada:
        raise ConflictoVersion(f"La jornada está en la versión {jornada.version}; se recibió la {version_esperada}.")
    if jornada.estado == JornadaRegistro.Estado.ANULADA:
        return jornada
    antes = snapshot_jornada(jornada)
    version_anterior = jornada.version
    jornada.estado = JornadaRegistro.Estado.ANULADA
    jornada.anulada_por = actor
    jornada.anulada_en = timezone.now()
    jornada.motivo_anulacion = motivo.strip()
    jornada.version += 1
    jornada.save()
    _registrar_auditoria(
        entidad=AuditoriaCambio.Entidad.JORNADA,
        entidad_uuid=jornada.id,
        accion=AuditoriaCambio.Accion.ANULAR,
        actor=actor,
        version_anterior=version_anterior,
        version_nueva=jornada.version,
        antes=antes,
        despues=snapshot_jornada(jornada),
        motivo=motivo,
    )
    return jornada


def calcular_poblacion_teorica(piscina, hasta=None, excluir_jornada=None):
    jornadas = JornadaRegistro.objects.filter(
        piscina=piscina,
        estado=JornadaRegistro.Estado.COMPLETA,
    )
    if hasta is not None:
        jornadas = jornadas.filter(capturada_en__lt=hasta)
    if excluir_jornada is not None:
        jornadas = jornadas.exclude(pk=excluir_jornada)
    base = jornadas.order_by("-capturada_en", "-creada_en").first()
    if base is None:
        return None

    movimientos = MovimientoPoblacion.objects.filter(
        estado=MovimientoPoblacion.Estado.ACTIVO,
        ocurrido_en__gt=base.capturada_en,
    ).filter(models.Q(piscina_origen=piscina) | models.Q(piscina_destino=piscina))
    if hasta is not None:
        movimientos = movimientos.filter(ocurrido_en__lte=hasta)
    total = base.poblacion_estimada
    for movimiento in movimientos:
        if movimiento.piscina_destino_id == piscina.id:
            total += movimiento.cantidad
        if movimiento.piscina_origen_id == piscina.id:
            total -= movimiento.cantidad
    return max(total, 0)


@transaction.atomic
def crear_movimiento(*, actor, tipo, cantidad, ocurrido_en, piscina_origen=None, piscina_destino=None, observaciones="", movimiento_id=None):
    perfil = perfil_de(actor)
    for piscina in (piscina_origen, piscina_destino):
        if piscina is not None:
            _validar_piscina(perfil, piscina)
    if movimiento_id:
        existente = MovimientoPoblacion.objects.select_for_update().filter(pk=movimiento_id).first()
        if existente:
            if not existente.puede_modificar(actor):
                raise PermissionDenied("El UUID ya pertenece a otro autor.")
            return existente, False
    movimiento = MovimientoPoblacion(
        id=movimiento_id,
        tipo=tipo,
        cantidad=cantidad,
        piscina_origen=piscina_origen,
        piscina_destino=piscina_destino,
        autor=perfil,
        ocurrido_en=ocurrido_en,
        observaciones=observaciones,
    )
    movimiento.full_clean()
    movimiento.save()
    _registrar_auditoria(
        entidad=AuditoriaCambio.Entidad.MOVIMIENTO,
        entidad_uuid=movimiento.id,
        accion=AuditoriaCambio.Accion.CREAR,
        actor=actor,
        version_anterior=None,
        version_nueva=1,
        antes=None,
        despues=snapshot_movimiento(movimiento),
    )
    return movimiento, True


@transaction.atomic
def corregir_movimiento(*, movimiento, actor, version_esperada, tipo, cantidad, ocurrido_en, piscina_origen=None, piscina_destino=None, observaciones="", motivo=""):
    movimiento = MovimientoPoblacion.objects.select_for_update().get(pk=movimiento.pk)
    if not movimiento.puede_modificar(actor):
        raise PermissionDenied("Solo el autor o un administrador pueden corregir el movimiento.")
    if movimiento.estado == MovimientoPoblacion.Estado.ANULADO:
        raise ValidationError("Un movimiento anulado no puede corregirse.")
    if movimiento.version != version_esperada:
        raise ConflictoVersion(f"El movimiento está en la versión {movimiento.version}; se recibió la {version_esperada}.")
    perfil = perfil_de(actor)
    for piscina in (piscina_origen, piscina_destino):
        if piscina is not None:
            _validar_piscina(perfil, piscina)
    antes = snapshot_movimiento(movimiento)
    version_anterior = movimiento.version
    movimiento.tipo = tipo
    movimiento.cantidad = cantidad
    movimiento.ocurrido_en = ocurrido_en
    movimiento.piscina_origen = piscina_origen
    movimiento.piscina_destino = piscina_destino
    movimiento.observaciones = observaciones
    movimiento.version += 1
    movimiento.full_clean()
    movimiento.save()
    _registrar_auditoria(
        entidad=AuditoriaCambio.Entidad.MOVIMIENTO,
        entidad_uuid=movimiento.id,
        accion=AuditoriaCambio.Accion.CORREGIR,
        actor=actor,
        version_anterior=version_anterior,
        version_nueva=movimiento.version,
        antes=antes,
        despues=snapshot_movimiento(movimiento),
        motivo=motivo,
    )
    return movimiento


@transaction.atomic
def anular_movimiento(*, movimiento, actor, version_esperada, motivo):
    movimiento = MovimientoPoblacion.objects.select_for_update().get(pk=movimiento.pk)
    if not movimiento.puede_modificar(actor):
        raise PermissionDenied("Solo el autor o un administrador pueden anular el movimiento.")
    if not motivo.strip():
        raise ValidationError("El motivo de anulación es obligatorio.")
    if movimiento.version != version_esperada:
        raise ConflictoVersion(f"El movimiento está en la versión {movimiento.version}; se recibió la {version_esperada}.")
    if movimiento.estado == MovimientoPoblacion.Estado.ANULADO:
        return movimiento
    antes = snapshot_movimiento(movimiento)
    version_anterior = movimiento.version
    movimiento.estado = MovimientoPoblacion.Estado.ANULADO
    movimiento.anulado_por = actor
    movimiento.anulado_en = timezone.now()
    movimiento.motivo_anulacion = motivo.strip()
    movimiento.version += 1
    movimiento.save()
    _registrar_auditoria(
        entidad=AuditoriaCambio.Entidad.MOVIMIENTO,
        entidad_uuid=movimiento.id,
        accion=AuditoriaCambio.Accion.ANULAR,
        actor=actor,
        version_anterior=version_anterior,
        version_nueva=movimiento.version,
        antes=antes,
        despues=snapshot_movimiento(movimiento),
        motivo=motivo,
    )
    return movimiento


# Import al final para mantener legible la sección de servicios.
from django.db import models  # noqa: E402
