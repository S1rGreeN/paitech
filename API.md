# Contrato REST de PaiPayTech v1.6-dev

Base: `/api/v1/`. Todas las rutas, salvo `health` y `auth/login`, requieren:

```http
Authorization: Token <token>
Content-Type: application/json
```

## Autenticación

- `POST auth/login/`:

  ```json
  {
    "email": "acuicultor@example.com",
    "password": "...",
    "dispositivo_id": "android-uuid-de-instalacion",
    "nombre_dispositivo": "Google sdk_gphone64_x86_64"
  }
  ```

  Devuelve una credencial con formato `<selector>.<secreto>`, `expira_en`,
  `debe_cambiar_clave` y los datos del usuario. El nombre es informativo y el
  identificador representa la instalación, no un identificador de hardware.
- `POST auth/logout/`: revoca el token del dispositivo.
- `POST auth/cambiar-clave/`: requiere una sesión autenticada y recibe
  `password_actual`, `password_nuevo` y `confirmacion`. Al completarse revoca
  todas las sesiones web y móviles de esa cuenta, por lo que se debe iniciar
  sesión otra vez.
- `GET auth/me/`: usuario, rol y comunidad. La comunidad expone `id_publico`
  (UUID), `codigo` y `nombre`, nunca su PK numérica interna.

Cada instalación tiene una sesión independiente y un usuario puede usar varios
teléfonos simultáneamente. La vigencia es deslizante: cada solicitud autenticada
renueva 30 días desde ese contacto con Django. Android también limita el uso
offline a 30 días desde la última validación del servidor. Neon conserva SHA-256
del secreto, no la credencial completa; Android la guarda cifrada con el
Keystore del sistema.

Una cuenta con contraseña temporal puede usar solamente `logout` y
`cambiar-clave` hasta reemplazarla. Cinco fallos para la misma combinación de
correo e IP dentro de 15 minutos producen un bloqueo de 15 minutos; la
reincidencia produce uno de 60 minutos. Las respuestas son genéricas: `401` para
un fallo normal y `429` cuando el acceso está bloqueado.

## Catálogos y semáforo

- `GET catalogos/especies/`: solo especies asociadas a piscinas de la comunidad.
- `GET catalogos/piscinas/`: piscinas de la comunidad, población teórica,
  ciclo activo y estados informativos de agua/biometría.
- `GET catalogos/camas/`: camas activas de lombricultura de la comunidad, ciclo
  activo y último registro.
- `GET semaforos/`: última jornada comunitaria con agua por piscina. No descarga el historial comunitario completo.

Todos los querysets se filtran con la comunidad del perfil autenticado. Un UUID
válido perteneciente a otra comunidad responde `404` para no confirmar la
existencia del objeto.

## Ciclos productivos

- `GET ciclos/`: hasta 200 ciclos de la comunidad.
- `POST ciclos/`: apertura idempotente por UUID.
- `GET ciclos/{uuid}/`.
- `POST ciclos/{uuid}/cerrar/`: cierre optimista; requiere `version`.
- `GET ciclos/prediccion/?piscina=<uuid>&poblacion_inicial=200`: vista
  previa calculada en Django para la web.

Solo puede existir un ciclo activo por piscina. La apertura requiere piscina,
fecha/hora y población inicial; duración estimada y observaciones son opcionales.
La especie se copia de la piscina y queda como instantánea histórica.

```json
{
  "id": "d0bbbda2-6b33-4e15-a567-42b6e51945c3",
  "piscina": "2f0f06e5-d61b-48f8-a8a7-a22fc25bf421",
  "iniciado_en": "2026-08-07T15:00:00-05:00",
  "poblacion_inicial": 200,
  "duracion_estimada_meses": 10,
  "observaciones_apertura": "Ciclo ficticio de prueba",
  "dispositivo_id": "android-a1b2c3"
}
```

Android puede añadir `prediccion_cache` cuando abrió offline y tenía historia
sincronizada. Django valida y conserva exactamente esa instantánea con método,
fecha y origen; si no había historia, Android omite el bloque y no inventa una
cifra.

El cierre recibe `destino_cierre` (`VENTA`, `CONSUMO`, `TRASLADO`,
`MORTALIDAD_TOTAL` u `OTRO`), `poblacion_final` y `cerrado_en`. Observaciones,
`peso_total_cosechado_kg` y `piscina_destino_cierre` son opcionales. La piscina
destino solo aplica a traslado, debe ser distinta y de la misma especie. Una
mortalidad total exige población final cero.

```json
{
  "version": 1,
  "cerrado_en": "2027-06-07T15:00:00-05:00",
  "destino_cierre": "VENTA",
  "poblacion_final": 187,
  "peso_total_cosechado_kg": null,
  "observaciones_cierre": "Fin completo de la cohorte",
  "piscina_destino_cierre": null
}
```

La predicción `mediana_supervivencia_v1` usa únicamente ciclos cerrados de la
misma piscina y excluye los que tengan traslados o ajustes. Devuelve estimación,
rango histórico, cantidad de ciclos y confianza (`MUY_BAJA`, `BAJA` o `MEDIA`).
Sin historia devuelve `SIN_DATOS` y valores numéricos nulos.

## Jornadas

- `GET jornadas/`: historial comunitario, máximo 200 elementos.
- `POST jornadas/`: creación idempotente por UUID.
- `GET jornadas/{uuid}/`.
- `PUT jornadas/{uuid}/`: corrección completa; requiere `version`.
- `POST jornadas/{uuid}/anular/`: `{"version":1,"motivo":"..."}`.

Ejemplo con agua y dos peces:

```json
{
  "id": "6bc4eb6d-421f-4f51-a70b-9805915f2061",
  "piscina": "2f0f06e5-d61b-48f8-a8a7-a22fc25bf421",
  "ciclo": "d0bbbda2-6b33-4e15-a567-42b6e51945c3",
  "capturada_en": "2026-08-07T15:00:00-05:00",
  "poblacion_estimada": 200,
  "observaciones": "Sin novedades",
  "dispositivo_id": "android-a1b2c3",
  "agua": {"ph": "7.20", "nitrato": "10.000", "nitrito": "0.250", "amoniaco_total": "0.250"},
  "peces": [
    {"peso_gramos": "250.40", "talla_centimetros": "21.30"},
    {"peso_gramos": "246.10", "talla_centimetros": "20.90"}
  ]
}
```

`agua` puede ser `null` y `peces` puede ser una lista vacía, pero no
simultáneamente. `poblacion_estimada` siempre es obligatoria. La jornada debe
pertenecer al ciclo de la piscina aplicable a su fecha. La especie proviene de
la piscina.

Los recordatorios no bloquean registros: agua se espera una vez por semana
calendario y biometría una vez por mes calendario. El primer vencimiento es
siete días y un mes calendario después de abrir el ciclo, respectivamente. Los
dos días posteriores son tolerancia; después se informa atraso.

El campo `ph` contiene un único resultado final aunque en campo se usen las
pruebas de rango normal y alto. Los cuatro campos aceptan escritura numérica
manual: pH usa hasta dos decimales y debe estar entre 0 y 14; `nitrato`,
`nitrito` y `amoniaco_total` usan hasta tres decimales y no pueden ser
negativos. Los tres últimos se expresan en ppm; `amoniaco_total` representa la
lectura conjunta rotulada por el kit como NH₃/NH₄⁺, no únicamente el ion
amonio.

Un `POST` repetido con el mismo UUID **y el mismo contenido** devuelve el registro
existente sin duplicarlo. Si ese UUID ya existe con datos distintos o fue
modificado/anulado, devuelve HTTP `409`; así una respuesta perdida no puede
convertirse después en una sobrescritura silenciosa. Una corrección o anulación
con versión obsoleta también devuelve `409` y `codigo: conflicto_version`.

## Movimientos

- `GET/POST movimientos/`.
- `GET/PUT movimientos/{uuid}/`.
- `POST movimientos/{uuid}/anular/`.

Tipos operativos: `MORTALIDAD`, `COSECHA_VENTA`, `TRASLADO`, `ESCAPE` y
`AJUSTE`. `SIEMBRA` permanece en el catálogo histórico, pero la API rechaza su
creación: la población inicial se registra al abrir el ciclo. La dirección se
expresa con `piscina_origen`/`piscina_destino` y cada lado incluye
`ciclo_origen`/`ciclo_destino`. Los movimientos son excepcionales y auditados;
una venta o traslado parcial no cierra el ciclo.

## Sensores futuros

El contrato previsto es `POST sensores/lecturas/lote/`, autenticado por
dispositivo y con lecturas UUID idempotentes. Cada lectura admite uno o más de:
oxígeno disuelto (`mg/L`), temperatura (`°C`) y turbidez (`NTU`). El dispositivo
solo escribe para su piscina y puede enviar datos aun si no hay ciclo activo.

En `1.6-dev`, `SENSORES_HABILITADOS=False` es obligatorio: el endpoint responde
`404`, no se emiten credenciales de hardware y los modelos quedan preparados
para una integración posterior.

## Lombricultura

- `GET/POST lombricultura/ciclos/`.
- `GET lombricultura/ciclos/{uuid}/`.
- `POST lombricultura/ciclos/{uuid}/cerrar/`.
- `GET/POST lombricultura/registros/`.
- `GET/PUT lombricultura/registros/{uuid}/`.
- `POST lombricultura/registros/{uuid}/anular/`.

Solo puede existir un ciclo activo por cama. La apertura exige fecha/hora y
conteo inicial real; el cierre exige fecha/hora y conteo final real. Ambos
conteos aceptan cero y el final puede ser menor, igual o mayor porque las
lombrices pueden morir, mantenerse o reproducirse. No existen movimientos,
pesos ni predicción para camas.

```json
{
  "id": "34aed38d-94df-42a2-881d-b27f20599538",
  "cama": "a96fbddf-e90f-44fa-bb57-bb1b37cdd8fb",
  "ciclo": "16654a1c-9d8f-4cce-9968-699436679765",
  "capturada_en": "2026-09-01T15:00:00-05:00",
  "ph_suelo": "7.35",
  "conteo_lombrices": 180,
  "observaciones": "Se observó reproducción",
  "dispositivo_id": "android-a1b2c3"
}
```

El pH del suelo se escribe manualmente entre 0 y 14 con hasta dos decimales. El
conteo es un entero observado igual o mayor que cero. No hay recordatorios ni
semáforo de lombricultura en esta versión. Creación, corrección, anulación,
idempotencia, autoría, auditoría y conflictos `409` siguen la misma política que
las jornadas. Un UUID existente de otro autor responde `403`, aunque el contenido
coincida: la idempotencia nunca transfiere autoría.

## Borrado y auditoría

No existe `DELETE` operativo. Anular cambia el estado y crea una entrada de
auditoría con actor, motivo, fecha, versión anterior y copia de los datos. Web y
Android pueden consultar el historial comunitario; solo el autor puede preparar
correcciones/anulaciones ordinarias desde Android y la excepción administrativa
queda auditada en Django.

Un reintento idéntico conserva idempotencia. Datos distintos con el mismo UUID,
dos aperturas simultáneas o una operación con versión obsoleta devuelven HTTP
`409`. Android conserva el cambio local, muestra la comparación y exige una
decisión explícita; nunca sobrescribe silenciosamente el servidor.
