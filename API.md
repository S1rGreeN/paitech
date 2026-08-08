# Contrato REST de PaiPayTech v1

Base: `/api/v1/`. Todas las rutas, salvo `health` y `auth/login`, requieren:

```http
Authorization: Token <token>
Content-Type: application/json
```

## Autenticación

- `POST auth/login/`: `{"email":"...","password":"..."}`.
- `POST auth/logout/`: revoca el token del dispositivo.
- `GET auth/me/`: usuario, rol y comunidad.

El primer ingreso de Android requiere conexión. El token se guarda cifrado para permitir trabajo offline posterior.

## Catálogos y semáforo

- `GET catalogos/especies/`.
- `GET catalogos/piscinas/`: piscinas de la comunidad y población teórica actual.
- `GET semaforos/`: última jornada comunitaria con agua por piscina. No descarga el historial comunitario completo.

## Jornadas

- `GET jornadas/`: historial del autor autenticado, máximo 200 elementos.
- `POST jornadas/`: creación idempotente por UUID.
- `GET jornadas/{uuid}/`.
- `PUT jornadas/{uuid}/`: corrección completa; requiere `version`.
- `POST jornadas/{uuid}/anular/`: `{"version":1,"motivo":"..."}`.

Ejemplo con agua y dos peces:

```json
{
  "id": "6bc4eb6d-421f-4f51-a70b-9805915f2061",
  "piscina": "2f0f06e5-d61b-48f8-a8a7-a22fc25bf421",
  "capturada_en": "2026-08-07T15:00:00-05:00",
  "poblacion_estimada": 200,
  "observaciones": "Sin novedades",
  "dispositivo_id": "android-a1b2c3",
  "agua": {"ph": "7.20", "nitrato": "10.000", "nitrito": "0.100", "amonio": "0.200"},
  "peces": [
    {"peso_gramos": "250.40", "talla_centimetros": "21.30"},
    {"peso_gramos": "246.10", "talla_centimetros": "20.90"}
  ]
}
```

`agua` puede ser `null` y `peces` puede ser una lista vacía, pero no simultáneamente. `poblacion_estimada` siempre es obligatoria. La especie proviene de la piscina.

Un `POST` repetido con el mismo UUID devuelve el registro existente sin duplicarlo. Una corrección con versión obsoleta devuelve HTTP `409` y `codigo: conflicto_version`.

## Movimientos

- `GET/POST movimientos/`.
- `GET/PUT movimientos/{uuid}/`.
- `POST movimientos/{uuid}/anular/`.

Tipos: `SIEMBRA`, `MORTALIDAD`, `COSECHA_VENTA`, `TRASLADO`, `ESCAPE`, `AJUSTE`. La dirección se expresa con `piscina_origen` y/o `piscina_destino`; no se repite especie.

## Borrado y auditoría

No existe `DELETE`. Anular cambia el estado y crea una entrada de auditoría con actor, motivo, fecha, versión anterior y copia de los datos. La API móvil solo lista el historial propio; la web permite lectura comunitaria.
