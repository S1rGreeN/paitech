# Seguridad de PaiPayTech v1.6-dev

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
- Lombricultura: pH del suelo de 0 a 14 con dos decimales y conteos enteros no
  negativos; cama y ciclo deben pertenecer a la misma comunidad.
- Cuerpo HTTP: máximo 2 MiB en Django v1.4.
- Login: correo válido; la política de alta/cambio acepta entre 8 y 32
  caracteres y aplica los validadores de similitud, claves comunes y claves
  exclusivamente numéricas de Django.
- Intentos: contador compartido en la base por correo normalizado e IP. Cinco
  fallos en 15 minutos bloquean 15 minutos; una reincidencia bloquea 60 minutos.
  Los mensajes no confirman si el correo existe y no se registran claves,
  tokens ni cuerpos HTTP.

## Sesiones, contraseñas y recuperación

- Cada instalación Android recibe su propio token aleatorio. La base guarda un
  selector UUID y SHA-256 del secreto; nunca el secreto original.
- Una solicitud autenticada renueva una vigencia deslizante de 30 días. Varios
  teléfonos pueden permanecer activos y cada uno puede revocarse de forma
  independiente desde Django Admin por el superusuario técnico.
- Cerrar sesión revoca ese dispositivo. Cambiar/restablecer la contraseña o
  desactivar la cuenta revoca todas las sesiones web y móviles.
- Las claves temporales obligan a cambiarlas antes de usar la web o los recursos
  de negocio de la API. No se fuerza rotación periódica de una clave definitiva.
- No existe recuperación automática por correo en esta etapa. El superusuario
  técnico puede restablecer cualquier cuenta; un administrador funcional solo
  cuentas de acuicultores. La clave temporal se entrega por un canal privado,
  obliga al cambio y el evento queda auditado sin guardar la clave.
- Los eventos de acceso se conservan 30 días. Los accesos eliminan
  oportunísticamente eventos antiguos y el comando diario recomendado es
  `python manage.py limpiar_eventos_seguridad`.
- Toda respuesta incluye `X-Request-ID`. Los HTTP 400 registran únicamente
  identificador, método y ruta: nunca cuerpo, contraseña, token, cookie ni query.

## Seguridad local de Android

- Token, correo, UUID público de comunidad y marca temporal de validación se guardan en
  `EncryptedSharedPreferences`, protegidas por Android Keystore. La base Room
  permanece dentro del sandbox privado y las copias de seguridad están
  deshabilitadas.
- Si el teléfono no tiene PIN, patrón, contraseña o biometría, la app muestra una
  advertencia y permite continuar, según la decisión funcional del proyecto.
- El trabajo offline se permite como máximo 30 días desde la última respuesta
  autenticada. Una expiración conserva los pendientes; un cierre voluntario solo
  se permite sin pendientes/conflictos y elimina sesión, Room y caché local.
- Un cambio de cuenta o comunidad se rechaza mientras exista cualquier jornada,
  movimiento, ciclo o registro de lombricultura pendiente/conflictivo. Cuando no
  hay trabajo sin resolver, Room se limpia y se descarga el catálogo del tenant
  nuevo.

## Aislamiento entre comunidades

- Cada perfil pertenece exactamente a una `Comunidad`; la PK numérica permanece
  interna y los clientes reciben un UUID público no secuencial.
- Web, API y Django Admin funcional parten de la comunidad autenticada y filtran
  también claves foráneas. Conocer el UUID de una piscina, cama, ciclo o registro
  ajeno no concede acceso y produce `404`.
- Especies y perfiles de semáforo son globales, pero un usuario ordinario solo
  ve especies utilizadas por las piscinas de su comunidad. Solo el superusuario
  técnico puede modificarlos o consultar datos transversalmente en Django Admin.
- La comunidad nunca se acepta como un campo libre del payload operativo; Django
  la deriva del usuario y de la piscina/cama seleccionada.

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
- configurar `TRUST_X_FORWARDED_FOR=True` solamente en Railway, donde el proxy es
  controlado, para que el contador compartido use la IP del cliente;
- programar `limpiar_eventos_seguridad` una vez al día;
- no ejecutar `seed_demo` en Railway/Neon; el propio comando se bloquea con
  `DEBUG=False` o una base distinta de SQLite;
- inicializar solo los catálogos confirmados mediante
  `inicializar_catalogo_paipayales` y crear usuarios con entrada interactiva;
- no activar HSTS prolongado hasta verificar primero dominio y HTTPS; después
  aumentarlo gradualmente;
- mantener deshabilitada la ingestión de sensores hasta provisionar dispositivos;
- los sensores futuros usarán secretos aleatorios almacenados solo como hash,
  quedarán limitados a una piscina y escribirán únicamente mediante Django;
- rotar inmediatamente cualquier secreto que aparezca en capturas, logs, Git o
  conversaciones.

Railway permite sellar variables sensibles. Neon exige conexiones TLS. La guía
paso a paso se realizará junto con el propietario cuando llegue el hito de
despliegue; no se copiarán secretos en archivos versionados.

## Controles todavía pendientes antes de v1.6 final

- ejecutar pruebas dinámicas contra el despliegue de desarrollo;
- revisar dependencias y alertas de vulnerabilidades;
- repetir dinámicamente expiración/revocación contra Railway y Neon;
- hacer prueba de aceptación en un teléfono físico antes del uso de campo;
- definir copias de seguridad, restauración y respuesta ante incidentes.
