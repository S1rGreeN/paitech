# Arquitectura de PaiPayTech v1.5-dev

```mermaid
flowchart LR
    A["Android Java + Room"] -->|"HTTPS / Token"| B["Django REST Framework · Railway"]
    W["Web Django"] --> B
    B --> N["PostgreSQL · Neon"]
```

Django concentra autenticación, permisos, validación, auditoría y semáforo. Android nunca accede directamente a Neon y usa Room como fuente local para trabajar sin conexión.

```mermaid
erDiagram
    COMUNIDAD ||--o{ ACUICULTOR : agrupa
    USUARIO ||--|| ACUICULTOR : posee
    COMUNIDAD ||--o{ PISCINA : posee
    ESPECIE ||--o{ PISCINA : "es permanente en"
    PISCINA ||--o{ CICLO_PRODUCTIVO : organiza
    ESPECIE ||--o{ CICLO_PRODUCTIVO : "queda registrada en"
    CICLO_PRODUCTIVO ||--o{ JORNADA_REGISTRO : contiene
    PISCINA ||--o{ JORNADA_REGISTRO : recibe
    ACUICULTOR ||--o{ JORNADA_REGISTRO : crea
    JORNADA_REGISTRO ||--o| MEDICION_AGUA : incluye
    JORNADA_REGISTRO ||--o| MUESTRA_BIOMETRICA : incluye
    MUESTRA_BIOMETRICA ||--|{ OBSERVACION_PEZ : contiene
    PISCINA ||--o{ MOVIMIENTO_POBLACION : afecta
    CICLO_PRODUCTIVO ||--o{ MOVIMIENTO_POBLACION : contextualiza
    ACUICULTOR ||--o{ MOVIMIENTO_POBLACION : registra
    PISCINA ||--o{ DISPOSITIVO_SENSOR : equipa
    DISPOSITIVO_SENSOR ||--o{ LECTURA_SENSOR : envia
    CICLO_PRODUCTIVO ||--o{ LECTURA_SENSOR : contextualiza
    USUARIO ||--o{ AUDITORIA_CAMBIO : ejecuta
```

## Límites de lectura

- Web: todos los miembros autenticados ven las jornadas de su comunidad.
- Android: cachea el historial comunitario para consulta offline; solo habilita
  edición/anulación para la cuenta autora.
- Semáforo Android: descarga la última jornada comunitaria con agua de cada piscina.

## Sincronización

Android genera UUID y guarda primero en Room. Sincroniza ciclos antes de jornadas
y movimientos para que las referencias existan. `POST` es idempotente; cierres,
`PUT` y anulaciones requieren la versión conocida. Un servidor adelantado
devuelve `409`, y el dato local permanece en conflicto hasta comparar y resolver.

El ciclo delimita desde la siembra hasta el destino final de toda la cohorte.
Una piscina solo tiene un ciclo activo y su especie es permanente. La población
inicial vive en la apertura; mortalidad, escape, traslado, venta parcial y ajuste
son movimientos excepcionales ligados a los ciclos afectados.

Agua y biometría siguen siendo bloques de una jornada: agua se espera semanal y
biometría mensual. Los recordatorios son estados derivados, no bloqueos.

La telemetría futura también atraviesa HTTPS y Django. Un sensor nunca conoce
`DATABASE_URL` ni accede a Neon. El endpoint permanece deshabilitado hasta
definir hardware, aprovisionamiento y rotación de credenciales.

Los borradores solo existen localmente. En el servidor no hay borrado físico de jornadas ni movimientos: las anulaciones incrementan versión y crean auditoría.
