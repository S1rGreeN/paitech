# Arquitectura de PaiPayTech

## Modelo de datos corregido

```mermaid
erDiagram
    USER ||--|| ACUICULTOR : "tiene perfil"
    ACUICULTOR }o--o{ PISCINA : "puede consultar"
    PISCINA ||--o{ REGISTRO : "contiene"
    ACUICULTOR ||--o{ REGISTRO : "crea"
    REGISTRO ||--|{ MUESTRA_PEZ : "incluye"

    ACUICULTOR {
        bigint id PK
        bigint user_id FK
        string nickname UK
        date fecha_nacimiento
    }

    PISCINA {
        bigint id PK
        string codigo UK
        string nombre
        string tipo
        boolean activa
        datetime fecha_creacion
    }

    REGISTRO {
        bigint id PK
        bigint piscina_id FK
        bigint acuicultor_id FK
        datetime fecha
        decimal ph
        decimal nitrato
        decimal amonio
        decimal nitrito
        integer poblacion_estimada
        text observaciones
    }

    MUESTRA_PEZ {
        bigint id PK
        bigint registro_id FK
        string especie
        decimal peso_gramos
        decimal talla_centimetros
    }
```

## Decisiones

1. `User` de Django administra usuario, contraseña, correo, sesiones y permisos. `Acuicultor` amplía ese usuario con datos del dominio.
2. La relación entre `Acuicultor` y `Piscina` permanece muchos-a-muchos. En este MVP las señales asignan cada piscina activa a todos los acuicultores.
3. `Registro` representa una medición ambiental realizada en una piscina en una fecha concreta.
4. `MuestraPez` es uno-a-muchos respecto de `Registro`, porque una medición puede tomar varias muestras de peces.
5. La piscina de lombrices existe como `tipo='lombrices'`, pero su modelo de muestra no se inventa hasta conocer variables reales del negocio.

## Flujo principal

```mermaid
flowchart LR
    A[Login] --> B[Panel]
    B --> C[Piscina de peces]
    B --> D[Piscina de lombrices]
    C --> E[Historial]
    C --> F[Nuevo registro]
    F --> G[Datos del agua]
    F --> H[1 a 10 muestras de peces]
    G --> I[Guardar]
    H --> I
    I --> J[Detalle del registro]
    D --> K[Próximo sprint]
```
