# Seguridad de PaiPayTech v1.4

Este documento registra controles verificables y reglas que no deben romperse.
No sustituye una auditoría de seguridad externa antes de manejar datos reales.

## Frontera de confianza

```text
Android / navegador
        │ HTTPS + API autenticada
        ▼
Django REST Framework en Railway
        │ conexión PostgreSQL con TLS
        ▼
Neon
```

Android nunca recibe `DATABASE_URL`, credenciales PostgreSQL ni permisos para
consultar Neon directamente. Django es la única capa autorizada para validar,
autorizar y escribir datos de usuarios.

## Prevención de inyección SQL

1. Las entradas HTTP se validan con formularios Django o serializers DRF.
2. El acceso de negocio usa exclusivamente el ORM (`filter`, `get`, `create`,
   relaciones y transacciones), que separa el SQL de sus parámetros.
3. Se prohíbe formar SQL con concatenación, interpolación, `f-string`, `%` o
   `.format()` cuando intervenga cualquier dato externo.
4. `raw()`, `RawSQL`, `extra()` y cursores manuales requieren una decisión de
   seguridad documentada, parámetros enlazados y pruebas específicas.
5. El único cursor del servidor ejecuta la constante `SELECT 1` en el endpoint
   de salud; no contiene ni recibe parámetros del usuario.
6. El SQL manual de Android está limitado a migraciones constantes y `VACUUM`.
   Los DAO Room usan `:parametro`, que enlaza valores sin convertirlos en SQL.
7. Las pruebas envían cadenas como `'); DROP TABLE ...; --` y verifican que se
   rechacen o se almacenen literalmente sin alterar las tablas.

Esta política coincide con la protección documentada por Django:
https://docs.djangoproject.com/en/5.2/topics/security/#sql-injection-protection

## Validación y límites

- IDs externos: UUID validados por serializers y convertidores de URL.
- Valores numéricos: tipos decimales/enteros con rangos explícitos.
- Observaciones: máximo 5000 caracteres.
- Motivos de corrección/anulación: máximo 1000 caracteres.
- Biometría API: máximo 2000 peces por jornada. Este límite es defensivo y
  deberá revisarse si el protocolo de muestreo real exige más.
- Cuerpo HTTP: máximo 2 MiB en Django v1.4.
- Login: correo válido, contraseña de máximo 128 caracteres y límite inicial de
  10 intentos por minuto. El límite debe complementarse con monitoreo en
  producción; no se considera por sí solo protección absoluta contra bots.

## Producción Railway / Neon

Antes de exponer el servicio:

- `DEBUG=False`;
- `SECRET_KEY` aleatoria y sellada, nunca incluida en Git;
- `ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS` exactos, sin `*`;
- `DATABASE_URL` de un rol Neon exclusivo para la aplicación y con el menor
  privilegio práctico;
- TLS obligatorio en PostgreSQL y HTTPS obligatorio hacia Django;
- cookies `Secure`, protección CSRF, `X-Frame-Options: DENY`, `nosniff` y
  política de referente activas;
- ejecutar `python manage.py check --deploy` con las variables reales;
- configurar `/api/v1/health/` como healthcheck de despliegue;
- no activar HSTS prolongado hasta verificar primero dominio y HTTPS; después
  aumentarlo gradualmente;
- rotar inmediatamente cualquier secreto que aparezca en capturas, logs, Git o
  conversaciones.

Railway permite sellar variables sensibles. Neon exige conexiones TLS. La guía
paso a paso se realizará junto con el propietario cuando llegue el hito de
despliegue; no se copiarán secretos en archivos versionados.

## Controles todavía pendientes antes de v1.4 final

- ejecutar pruebas dinámicas contra el despliegue de desarrollo;
- revisar dependencias y alertas de vulnerabilidades;
- probar expiración/revocación de sesión y recuperación tras token vencido;
- ejecutar pruebas Android instrumentadas en emulador API 24+;
- hacer prueba de aceptación en un teléfono físico antes del uso de campo;
- definir copias de seguridad, restauración y respuesta ante incidentes.
