import json
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, models, transaction
from django.utils import timezone

from .models import (
    Acuicultor,
    AuditoriaCambio,
    CicloProductivo,
    JornadaRegistro,
    MedicionAgua,
    MovimientoPoblacion,
    MuestraBiometrica,
    ObservacionPez,
    Piscina,
)
from .prediccion import calcular_prediccion, validar_prediccion_cache


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
        "ciclo": jornada.ciclo_id,
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
            "amoniaco_total": agua.amoniaco_total,
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
            "ciclo_origen": movimiento.ciclo_origen_id,
            "ciclo_destino": movimiento.ciclo_destino_id,
            "autor": movimiento.autor_id,
            "ocurrido_en": movimiento.ocurrido_en,
            "observaciones": movimiento.observaciones,
            "estado": movimiento.estado,
            "version": movimiento.version,
        }
    )


def snapshot_ciclo(ciclo):
    return _json_seguro(
        {
            "id": ciclo.id,
            "piscina": ciclo.piscina_id,
            "especie": ciclo.especie_id,
            "numero": ciclo.numero,
            "estado": ciclo.estado,
            "iniciado_en": ciclo.iniciado_en,
            "poblacion_inicial": ciclo.poblacion_inicial,
            "duracion_estimada_meses": ciclo.duracion_estimada_meses,
            "observaciones_apertura": ciclo.observaciones_apertura,
            "autor_apertura": ciclo.autor_apertura_id,
            "fuente": ciclo.fuente,
            "dispositivo_id": ciclo.dispositivo_id,
            "cerrado_en": ciclo.cerrado_en,
            "destino_cierre": ciclo.destino_cierre,
            "poblacion_final": ciclo.poblacion_final,
            "peso_total_cosechado_kg": ciclo.peso_total_cosechado_kg,
            "observaciones_cierre": ciclo.observaciones_cierre,
            "piscina_destino_cierre": ciclo.piscina_destino_cierre_id,
            "autor_cierre": ciclo.autor_cierre_id,
            "prediccion_poblacion_final": ciclo.prediccion_poblacion_final,
            "prediccion_min": ciclo.prediccion_min,
            "prediccion_max": ciclo.prediccion_max,
            "prediccion_tasa": ciclo.prediccion_tasa,
            "prediccion_ciclos_usados": ciclo.prediccion_ciclos_usados,
            "prediccion_confianza": ciclo.prediccion_confianza,
            "prediccion_metodo_version": ciclo.prediccion_metodo_version,
            "prediccion_calculada_en": ciclo.prediccion_calculada_en,
            "prediccion_datos_hasta": ciclo.prediccion_datos_hasta,
            "prediccion_origen": ciclo.prediccion_origen,
            "version": ciclo.version,
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


def _jornada_equivale_a_reintento(existente, *, piscina, ciclo, capturada_en,
                                   poblacion_estimada, observaciones,
                                   fuente, dispositivo_id, agua, peces):
    if existente.version != 1 or existente.estado != JornadaRegistro.Estado.COMPLETA:
        return False
    if (
        existente.piscina_id != piscina.id
        or existente.ciclo_id != ciclo.id
        or existente.capturada_en != capturada_en
        or existente.poblacion_estimada != poblacion_estimada
        or existente.observaciones != observaciones
        or existente.fuente != fuente
        or existente.dispositivo_id != dispositivo_id
    ):
        return False

    try:
        agua_existente = existente.agua
    except MedicionAgua.DoesNotExist:
        agua_existente = None
    if (agua_existente is None) != (agua is None):
        return False
    if agua_existente is not None:
        for campo in ("ph", "nitrato", "nitrito", "amoniaco_total"):
            if getattr(agua_existente, campo) != agua[campo]:
                return False

    try:
        peces_existentes = list(existente.muestra_biometrica.peces.all())
    except MuestraBiometrica.DoesNotExist:
        peces_existentes = []
    if len(peces_existentes) != len(peces):
        return False
    return all(
        existente_pez.peso_gramos == recibido["peso_gramos"]
        and existente_pez.talla_centimetros == recibido["talla_centimetros"]
        for existente_pez, recibido in zip(peces_existentes, peces)
    )


def _movimiento_equivale_a_reintento(existente, *, tipo, cantidad,
                                      ocurrido_en, piscina_origen,
                                      piscina_destino, ciclo_origen,
                                      ciclo_destino, observaciones):
    return (
        existente.version == 1
        and existente.estado == MovimientoPoblacion.Estado.ACTIVO
        and existente.tipo == tipo
        and existente.cantidad == cantidad
        and existente.ocurrido_en == ocurrido_en
        and existente.piscina_origen_id == (
            piscina_origen.id if piscina_origen else None
        )
        and existente.piscina_destino_id == (
            piscina_destino.id if piscina_destino else None
        )
        and existente.ciclo_origen_id == (
            ciclo_origen.id if ciclo_origen else None
        )
        and existente.ciclo_destino_id == (
            ciclo_destino.id if ciclo_destino else None
        )
        and existente.observaciones == observaciones
    )


def _validar_piscina(perfil, piscina):
    if piscina.comunidad_id != perfil.comunidad_id:
        raise PermissionDenied("La piscina no pertenece a la comunidad del usuario.")
    if not piscina.activa:
        raise ValidationError("La piscina está inactiva.")
    if piscina.tipo != Piscina.Tipo.PECES:
        raise ValidationError("Lombricultura permanece como Próximamente en esta versión.")


def _ciclo_para_fecha(piscina, fecha, ciclo=None):
    if ciclo is None:
        ciclo = (
            CicloProductivo.objects.filter(
                piscina=piscina,
                estado=CicloProductivo.Estado.ACTIVO,
                iniciado_en__lte=fecha,
            )
            .order_by("-iniciado_en")
            .first()
        )
    if ciclo is None:
        raise ValidationError(
            {"ciclo": "La piscina necesita un ciclo activo para registrar esta operación."}
        )
    if ciclo.piscina_id != piscina.id:
        raise ValidationError({"ciclo": "El ciclo no pertenece a la piscina indicada."})
    if ciclo.estado == CicloProductivo.Estado.ANULADO:
        raise ValidationError({"ciclo": "No se puede registrar en un ciclo anulado."})
    if fecha < ciclo.iniciado_en:
        raise ValidationError({"ciclo": "La fecha es anterior a la apertura del ciclo."})
    if ciclo.cerrado_en and fecha > ciclo.cerrado_en:
        raise ValidationError({"ciclo": "La fecha es posterior al cierre del ciclo."})
    return ciclo


@transaction.atomic
def crear_ciclo(
    *,
    actor,
    piscina,
    iniciado_en,
    poblacion_inicial,
    duracion_estimada_meses=None,
    observaciones_apertura="",
    fuente=CicloProductivo.Fuente.ANDROID,
    dispositivo_id="",
    ciclo_id=None,
    prediccion_cache=None,
):
    perfil = perfil_de(actor)
    _validar_piscina(perfil, piscina)
    Piscina.objects.select_for_update().get(pk=piscina.pk)

    if ciclo_id:
        existente = (
            CicloProductivo.objects.select_for_update().filter(pk=ciclo_id).first()
        )
        if existente:
            if existente.autor_apertura.user_id != actor.id and not actor.is_superuser:
                raise PermissionDenied("El UUID ya pertenece a otro autor.")
            equivalente = (
                existente.version == 1
                and existente.estado == CicloProductivo.Estado.ACTIVO
                and existente.piscina_id == piscina.id
                and existente.iniciado_en == iniciado_en
                and existente.poblacion_inicial == poblacion_inicial
                and existente.duracion_estimada_meses == duracion_estimada_meses
                and existente.observaciones_apertura == observaciones_apertura
                and existente.fuente == fuente
                and existente.dispositivo_id == dispositivo_id
            )
            if equivalente:
                return existente, False
            raise ConflictoVersion(
                "El UUID del ciclo ya existe con datos o versión diferentes."
            )

    if CicloProductivo.objects.filter(
        piscina=piscina, estado=CicloProductivo.Estado.ACTIVO
    ).exists():
        raise ConflictoVersion("La piscina ya tiene un ciclo activo.")

    numero = (
        CicloProductivo.objects.filter(piscina=piscina).aggregate(
            valor=models.Max("numero")
        )["valor"]
        or 0
    ) + 1
    if prediccion_cache:
        try:
            prediccion = validar_prediccion_cache(prediccion_cache)
        except (KeyError, TypeError, ValueError) as error:
            raise ValidationError({"prediccion": str(error)}) from error
    else:
        prediccion = calcular_prediccion(piscina, poblacion_inicial)

    ciclo = CicloProductivo(
        id=ciclo_id,
        piscina=piscina,
        especie=piscina.especie,
        numero=numero,
        iniciado_en=iniciado_en,
        poblacion_inicial=poblacion_inicial,
        duracion_estimada_meses=duracion_estimada_meses,
        observaciones_apertura=observaciones_apertura,
        autor_apertura=perfil,
        fuente=fuente,
        dispositivo_id=dispositivo_id,
        **prediccion,
    )
    ciclo.full_clean()
    try:
        ciclo.save()
    except IntegrityError as error:
        raise ConflictoVersion("La piscina ya tiene un ciclo activo.") from error
    _registrar_auditoria(
        entidad=AuditoriaCambio.Entidad.CICLO,
        entidad_uuid=ciclo.id,
        accion=AuditoriaCambio.Accion.CREAR,
        actor=actor,
        version_anterior=None,
        version_nueva=1,
        antes=None,
        despues=snapshot_ciclo(ciclo),
    )
    return ciclo, True


@transaction.atomic
def cerrar_ciclo(
    *,
    ciclo,
    actor,
    version_esperada,
    cerrado_en,
    destino_cierre,
    poblacion_final,
    peso_total_cosechado_kg=None,
    observaciones_cierre="",
    piscina_destino_cierre=None,
):
    perfil = perfil_de(actor)
    ciclo = (
        CicloProductivo.objects.select_for_update()
        .select_related("piscina", "especie")
        .get(pk=ciclo.pk)
    )
    _validar_piscina(perfil, ciclo.piscina)
    if piscina_destino_cierre is not None:
        _validar_piscina(perfil, piscina_destino_cierre)

    cierre_equivalente = (
        ciclo.estado == CicloProductivo.Estado.CERRADO
        and ciclo.version == version_esperada + 1
        and ciclo.cerrado_en == cerrado_en
        and ciclo.destino_cierre == destino_cierre
        and ciclo.poblacion_final == poblacion_final
        and ciclo.peso_total_cosechado_kg == peso_total_cosechado_kg
        and ciclo.observaciones_cierre == observaciones_cierre
        and ciclo.piscina_destino_cierre_id
        == (piscina_destino_cierre.id if piscina_destino_cierre else None)
    )
    if cierre_equivalente:
        return ciclo, False
    if ciclo.version != version_esperada:
        raise ConflictoVersion(
            f"El ciclo está en la versión {ciclo.version}; se recibió la {version_esperada}."
        )
    if ciclo.estado != CicloProductivo.Estado.ACTIVO:
        raise ConflictoVersion("El ciclo ya no está activo.")

    antes = snapshot_ciclo(ciclo)
    ciclo.estado = CicloProductivo.Estado.CERRADO
    ciclo.cerrado_en = cerrado_en
    ciclo.destino_cierre = destino_cierre
    ciclo.poblacion_final = poblacion_final
    ciclo.peso_total_cosechado_kg = peso_total_cosechado_kg
    ciclo.observaciones_cierre = observaciones_cierre
    ciclo.piscina_destino_cierre = piscina_destino_cierre
    ciclo.autor_cierre = perfil
    ciclo.version += 1
    ciclo.full_clean()
    ciclo.save()
    _registrar_auditoria(
        entidad=AuditoriaCambio.Entidad.CICLO,
        entidad_uuid=ciclo.id,
        accion=AuditoriaCambio.Accion.CORREGIR,
        actor=actor,
        version_anterior=version_esperada,
        version_nueva=ciclo.version,
        antes=antes,
        despues=snapshot_ciclo(ciclo),
        motivo="Cierre del ciclo productivo",
    )
    return ciclo, True


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
def crear_jornada(*, actor, piscina, capturada_en, poblacion_estimada, ciclo=None, observaciones="", fuente=JornadaRegistro.Fuente.ANDROID, dispositivo_id="", agua=None, peces=None, jornada_id=None):
    perfil = perfil_de(actor)
    _validar_piscina(perfil, piscina)
    ciclo = _ciclo_para_fecha(piscina, capturada_en, ciclo)
    if jornada_id:
        existente = JornadaRegistro.objects.select_for_update().filter(pk=jornada_id).first()
        if existente:
            if not existente.puede_modificar(actor):
                raise PermissionDenied("El UUID ya pertenece a otro autor.")
            if _jornada_equivale_a_reintento(
                existente,
                piscina=piscina,
                ciclo=ciclo,
                capturada_en=capturada_en,
                poblacion_estimada=poblacion_estimada,
                observaciones=observaciones,
                fuente=fuente,
                dispositivo_id=dispositivo_id,
                agua=agua,
                peces=peces or [],
            ):
                return existente, False
            raise ConflictoVersion(
                "El UUID de la jornada ya existe con datos o versión diferentes."
            )

    jornada = JornadaRegistro(
        id=jornada_id,
        piscina=piscina,
        ciclo=ciclo,
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
def corregir_jornada(*, jornada, actor, version_esperada, piscina, capturada_en, poblacion_estimada, ciclo=None, observaciones="", dispositivo_id="", agua=None, peces=None, motivo=""):
    jornada = JornadaRegistro.objects.select_for_update().get(pk=jornada.pk)
    if not jornada.puede_modificar(actor):
        raise PermissionDenied("Solo el autor o un administrador pueden corregir la jornada.")
    if jornada.version != version_esperada:
        raise ConflictoVersion(f"La jornada está en la versión {jornada.version}; se recibió la {version_esperada}.")
    if jornada.estado == JornadaRegistro.Estado.ANULADA:
        raise ValidationError("Una jornada anulada no puede corregirse.")
    perfil = perfil_de(actor)
    _validar_piscina(perfil, piscina)
    ciclo = _ciclo_para_fecha(piscina, capturada_en, ciclo)
    antes = snapshot_jornada(jornada)
    version_anterior = jornada.version
    jornada.piscina = piscina
    jornada.ciclo = ciclo
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
def crear_movimiento(*, actor, tipo, cantidad, ocurrido_en, piscina_origen=None, piscina_destino=None, ciclo_origen=None, ciclo_destino=None, observaciones="", movimiento_id=None):
    perfil = perfil_de(actor)
    for piscina in (piscina_origen, piscina_destino):
        if piscina is not None:
            _validar_piscina(perfil, piscina)
    if tipo == MovimientoPoblacion.Tipo.SIEMBRA:
        raise ValidationError(
            {"tipo": "La siembra se registra abriendo un ciclo productivo."}
        )
    if piscina_origen is not None:
        ciclo_origen = _ciclo_para_fecha(piscina_origen, ocurrido_en, ciclo_origen)
    if piscina_destino is not None:
        ciclo_destino = _ciclo_para_fecha(piscina_destino, ocurrido_en, ciclo_destino)
    if movimiento_id:
        existente = MovimientoPoblacion.objects.select_for_update().filter(pk=movimiento_id).first()
        if existente:
            if not existente.puede_modificar(actor):
                raise PermissionDenied("El UUID ya pertenece a otro autor.")
            if _movimiento_equivale_a_reintento(
                existente,
                tipo=tipo,
                cantidad=cantidad,
                ocurrido_en=ocurrido_en,
                piscina_origen=piscina_origen,
                piscina_destino=piscina_destino,
                ciclo_origen=ciclo_origen,
                ciclo_destino=ciclo_destino,
                observaciones=observaciones,
            ):
                return existente, False
            raise ConflictoVersion(
                "El UUID del movimiento ya existe con datos o versión diferentes."
            )
    movimiento = MovimientoPoblacion(
        id=movimiento_id,
        tipo=tipo,
        cantidad=cantidad,
        piscina_origen=piscina_origen,
        piscina_destino=piscina_destino,
        ciclo_origen=ciclo_origen,
        ciclo_destino=ciclo_destino,
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
def corregir_movimiento(*, movimiento, actor, version_esperada, tipo, cantidad, ocurrido_en, piscina_origen=None, piscina_destino=None, ciclo_origen=None, ciclo_destino=None, observaciones="", motivo=""):
    movimiento = MovimientoPoblacion.objects.select_for_update().get(pk=movimiento.pk)
    if not movimiento.puede_modificar(actor):
        raise PermissionDenied("Solo el autor o un administrador pueden corregir el movimiento.")
    if movimiento.version != version_esperada:
        raise ConflictoVersion(f"El movimiento está en la versión {movimiento.version}; se recibió la {version_esperada}.")
    if movimiento.estado == MovimientoPoblacion.Estado.ANULADO:
        raise ValidationError("Un movimiento anulado no puede corregirse.")
    perfil = perfil_de(actor)
    for piscina in (piscina_origen, piscina_destino):
        if piscina is not None:
            _validar_piscina(perfil, piscina)
    if tipo == MovimientoPoblacion.Tipo.SIEMBRA:
        raise ValidationError(
            {"tipo": "La siembra se registra abriendo un ciclo productivo."}
        )
    if piscina_origen is not None:
        ciclo_origen = _ciclo_para_fecha(piscina_origen, ocurrido_en, ciclo_origen)
    if piscina_destino is not None:
        ciclo_destino = _ciclo_para_fecha(piscina_destino, ocurrido_en, ciclo_destino)
    antes = snapshot_movimiento(movimiento)
    version_anterior = movimiento.version
    movimiento.tipo = tipo
    movimiento.cantidad = cantidad
    movimiento.ocurrido_en = ocurrido_en
    movimiento.piscina_origen = piscina_origen
    movimiento.piscina_destino = piscina_destino
    movimiento.ciclo_origen = ciclo_origen
    movimiento.ciclo_destino = ciclo_destino
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
