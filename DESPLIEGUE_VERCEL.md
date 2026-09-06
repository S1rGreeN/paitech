# Migración de Railway a Vercel con Neon

Guía revisada el 5 de septiembre de 2026. Los cambios del repositorio preparan
el despliegue; las cuentas, variables, migraciones remotas y publicación se
configuran manualmente. No hay secretos reales en esta guía.

## 1. Qué se mueve y qué significa estar disponible

El destino es `Android / navegador → Django en Vercel → PostgreSQL en Neon`.
La base sigue siendo la misma: conserva usuarios, contraseñas, comunidades,
registros y tokens al reutilizar la misma rama/base de Neon. No necesitas
exportar/importar datos ni ejecutar `seed_demo` para cambiar de proveedor web.
Confirma en Railway qué rama y base de Neon utiliza actualmente el servicio.

Vercel ejecuta Django bajo demanda y puede arrancar instancias nuevas cuando
llega una petición. No necesitas mantener un servidor Gunicorn encendido.
El usuario acepta que la primera conexión después de un período sin actividad
pueda tardar. Vercel Hobby tiene límites y es para uso personal no comercial;
no equivale a servicio ilimitado ni a una garantía de disponibilidad permanente.
Antes de elegirlo para la operación de una organización, comprueba que el uso
encaje en sus condiciones. Consulta [Hobby](https://vercel.com/docs/plans/hobby)
y los [límites de funciones](https://vercel.com/docs/functions/limitations).

Neon también tiene su propio plan y cuotas. Su suspensión por inactividad permite
reducir consumo y una conexión nueva reactiva el cómputo; los datos persisten.
Evita sondeos frecuentes para mantenerlo despierto. Revisa el consumo en ambos
paneles. Consulta [Scale to Zero](https://neon.com/docs/introduction/scale-to-zero)
y [planes de Neon](https://neon.com/pricing).

## 2. Preparar el proyecto en Vercel

1. Publica estos cambios en el repositorio Git de **PaiPayTech_Django** y en la
   rama que decidas desplegar. La rama de trabajo actual es `dev`. Ten presente
   que publicar en una rama vinculada a Railway también puede activar su despliegue.
2. En Vercel, entra en **Add New → Project**, importa ese repositorio y concede
   acceso solo a los repositorios necesarios.
3. **Framework Preset:** Django. Si importas el repositorio de Django, deja
   **Root Directory** en su raíz (`./`); si en el futuro importas un repositorio
   contenedor, selecciona `PaiPayTech_Django`. La raíz debe contener `manage.py`,
   `vercel.json`, `requirements.txt` y `.python-version`.
4. Asigna un nombre al proyecto. Usa su dominio estable asignado en **Settings →
   Domains** en los ejemplos siguientes: `TU-PROYECTO.vercel.app`. Si Vercel
   asigna otro nombre, utiliza ese valor exacto.
5. Mantén los comandos de `vercel.json`: instalación con
   `uv pip install --require-hashes -r requirements.txt` y build con
   `python manage.py check`. Deja **Output Directory** en el valor del framework.
   El runtime se fija a Python 3.12 mediante `.python-version`.
6. Configura las variables del apartado siguiente antes de desplegar.
7. En **Settings → Git**, comprueba **Production Branch**. Para publicar el
   estado de trabajo actual puedes seleccionar `dev`; cambia a `main` cuando
   esa sea la rama que contiene la versión validada. `Production` en Vercel
   designa el despliegue del dominio estable, independientemente del nombre
   de la rama Git. Un cambio en una rama distinta genera normalmente un Preview.

`pyproject.toml` selecciona explícitamente `paipaytech.wsgi:application`.
La integración nativa de Django ejecuta `collectstatic` y entrega CSS, imágenes
y recursos del admin mediante el CDN. La aplicación usa un manifiesto con
nombres de estáticos versionados. No hace falta crear `api/index.py`, reescribir
todas las rutas ni configurar un comando para arrancar Gunicorn.
[Django en Vercel](https://vercel.com/docs/frameworks/full-stack/django).

La instalación conserva los hashes de `requirements.txt` mediante un comando
explícito ejecutado dentro del entorno Python de construcción.
[Runtime Python](https://vercel.com/docs/functions/runtimes/python) y
[implementación del constructor oficial](https://github.com/vercel/vercel/blob/main/packages/python/src/index.ts).

## 3. Variables que configuras tú

Para el dominio asignado por Vercel solo tienes que introducir `DATABASE_URL`,
`SECRET_KEY` y `CRON_SECRET`. El resto de la tabla describe los valores ya
resueltos por defecto y las opciones para dominios propios; no tienes que
crearlas manualmente para el despliegue rápido.

En **Project → Settings → Environment Variables**, agrega cada nombre y su
valor **sin comillas**. Selecciona **Production** para el dominio estable.
Selecciona el tipo **Secret** para `DATABASE_URL`, `SECRET_KEY` y `CRON_SECRET`
(en interfaces anteriores se llama **Sensitive**); usa **Config** para los demás.
No pegues
credenciales en el chat, capturas ni Git. Los cambios se aplican a un nuevo
despliegue: después de modificarlas ejecuta **Redeploy**.
[Variables de entorno](https://vercel.com/docs/environment-variables) y
[tipos Config/Secret](https://vercel.com/docs/environment-variables/sensitive-environment-variables).

| Variable | Valor y propósito |
| --- | --- |
| `DATABASE_URL` | URL PostgreSQL **con pooling** de la misma rama/base de Neon que ya usas; el host suele contener `-pooler`. Conserva los parámetros TLS entregados por Neon, incluido `sslmode=require`. Se obtiene en Neon → proyecto → Connect, seleccionando rama, base, rol y connection pooling. |
| `SECRET_KEY` | Copia de forma privada el valor que Django ya usa en Railway. Mantenerlo conserva la firma de las sesiones web. Si lo rotas, los usuarios deberán volver a entrar en la web. No uses el ejemplo del repositorio. |
| `DEBUG` | `False`, incluso para Preview. |
| `ALLOWED_HOSTS` | Automática para los dominios generados por Vercel. Para otros dominios propios añade el host exacto, sin `https://` ni `/`, separado por coma. No uses `*` ni `.vercel.app`. |
| `CSRF_TRUSTED_ORIGINS` | Automática para los dominios generados por Vercel. Para otros dominios propios añade su origen HTTPS, sin barra final, separado por coma. |
| `TRUST_X_FORWARDED_FOR` | `True` detrás del proxy de Vercel, para registrar la IP del cliente y aplicar los límites de login. |
| `CRON_SECRET` | Un secreto aleatorio independiente, de al menos 32 caracteres, para autorizar el mantenimiento diario. No se entrega a Android. |
| `SECURE_HSTS_SECONDS` | `0` durante la validación inicial del dominio. Activa HSTS prolongado solo cuando dominio y HTTPS sean definitivos. |
| `SENSORES_HABILITADOS` | `False`, hasta que se valide el hardware. |
| `PAIPAY_ENVIRONMENT` | `production`. No uses `development` para identificar una base con datos reales. |

Para generar `CRON_SECRET`, ejecuta tú en una terminal privada con Python:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copia el resultado directamente a Vercel. Para un despliegue nuevo sin clave
anterior, puedes generar otra cadena independiente para `SECRET_KEY`.
No cambies la contraseña del rol de Neon durante esta migración: Railway puede
seguir necesitándola hasta completar el cambio.
[Conexiones con pooling de Neon](https://neon.com/docs/connect/connection-pooling).

Vercel proporciona `VERCEL` y sus variables de dominio; no las inventes ni las
definas manualmente. El código añade los hosts y orígenes **exactos** de
`VERCEL_URL`, `VERCEL_BRANCH_URL` y `VERCEL_PROJECT_PRODUCTION_URL`. Mantén
activada la exposición de variables del sistema si la interfaz ofrece esa opción.
[Variables del sistema](https://vercel.com/docs/environment-variables/system-environment-variables).

Si habilitas Preview, configura allí **otra rama/base de Neon** y secretos
separados. No marques las credenciales de la base real para todos los entornos.
Un Preview también exige PostgreSQL, clave segura y `DEBUG=False`; que falle
por falta de variables es preferible a conectarlo por accidente a la base real.
Para uso local habitual sigue funcionando SQLite con `.env`.

## 4. Migraciones y administración desde una terminal privada

El build y el arranque en Vercel **no ejecutan migraciones, crean usuarios ni
inicializan catálogos**. Se evita que cada Preview o instancia cambie la base.
Esta migración de alojamiento no añade migraciones de modelos. Si Neon ya
está actualizado, solo debes verificarlo.

Para ejecutar comandos administrativos, abre una terminal local en este
repositorio y activa un entorno Python 3.12 con sus dependencias. Crea tú
`.env.neon.local`, ignorado por Git, con las variables de la tabla; para
`DATABASE_URL` usa aquí la conexión **directa, sin pooling**, de la misma base.
No copies las variables `VERCEL*` al archivo. Es un archivo privado separado
del `.env` de desarrollo; selecciónalo explícitamente:

```powershell
$env:PAIPAY_ENV_FILE = '.env.neon.local'
python manage.py showmigrations --plan
python manage.py migrate --check
```

Estos comandos comprueban la base que elegiste y pueden reactivar Neon. Revisa
visualmente la rama, base y rol en el panel antes de usarlos. Las variables ya
definidas en la terminal tienen prioridad sobre el archivo: usa una terminal
nueva sin un `DATABASE_URL` anterior. Si `migrate --check` informa migraciones
pendientes, crea primero una copia de seguridad o un punto de restauración
disponible en tu plan, revisa el plan y entonces ejecuta manualmente:

```powershell
python manage.py migrate --noinput
python manage.py check --deploy
```

Con HSTS aún en `0`, `check --deploy` puede advertir sobre HSTS; evalúalo al
terminar la validación HTTPS. No se debe activar solo para ocultar la advertencia.

Solo si la base es **nueva y vacía**, utiliza los comandos documentados en el
README para inicializar catálogos y crear cuentas. Para la base existente no
repitas altas ni ejecutes limpieza de datos operativos o `seed_demo`.
Vercel no necesita una consola de servidor permanente: los comandos de gestión
se ejecutan desde tu equipo con la conexión privada. Al terminar:

```powershell
Remove-Item Env:PAIPAY_ENV_FILE
```

Cierra esa terminal y protege el archivo privado. No incluyas `.env.neon.local`
en paquetes, commits o copias compartidas.

## 5. Desplegar y validar

1. Ejecuta **Deploy** o **Redeploy** en Vercel. Revisa los logs de construcción:
   instalación, comprobaciones de Django y recolección de estáticos.
2. Abre `https://TU-PROYECTO.vercel.app/api/v1/health/`. Debe responder
   `{"status":"ok","database":"ok"}`. Este endpoint consulta la base; úsalo
   para validar, no como un sondeo continuo para impedir que Neon se suspenda.
3. Abre la web y `/admin/`. Comprueba logos, CSS, inicio de sesión y cierre de
   sesión. Confirma que aparecen las comunidades y datos existentes.
4. Si la respuesta muestra el login de **Vercel** en lugar de Django, revisa
   **Settings → Deployment Protection**. El dominio de producción utilizado
   por los usuarios y Android debe permitir llegar a Django sin una sesión
   de Vercel. Conserva la protección de Preview. La autenticación y los permisos
   propios de Django siguen aplicándose a los datos.
   [Deployment Protection](https://vercel.com/docs/deployment-protection).
5. Para un `400`, revisa `ALLOWED_HOSTS`; para un `403` del formulario, los
   orígenes CSRF; para fallos de base, la URL, rol, rama y TLS de Neon. Consulta
   los logs de Vercel sin compartir secretos ni cuerpos de peticiones.

## 6. Mantenimiento diario

`vercel.json` programa `/api/internal/cron/mantenimiento/` a las 08:00 UTC
(03:00 de Ecuador continental). En Hobby la ejecución puede desplazarse dentro
de esa hora; el intervalo diario es compatible con su plan.
Elimina eventos y controles de login de más de 30 días y sesiones web vencidas.
No elimina usuarios, jornadas ni ciclos.
[Frecuencia y precisión](https://vercel.com/docs/cron-jobs/usage-and-pricing).

Vercel envía `Authorization: Bearer <CRON_SECRET>`. El endpoint verifica el
secreto, rechaza peticiones no autorizadas y desactiva la caché. Sin secreto
responde `503`; con una credencial incorrecta responde `401` y no limpia nada.
Los reintentos son seguros. Comprueba en **Settings → Cron Jobs** que aparece
tras el despliegue de Production y ejecuta una prueba desde su panel. Un `503`
requiere configurar `CRON_SECRET` y volver a desplegar. El cron no se usa para
mantener caliente la aplicación.
[Administración y autenticación de cron](https://vercel.com/docs/cron-jobs/manage-cron-jobs).

## 7. Apuntar Android al nuevo dominio

En el repositorio hermano `paitech-datalogger`, cambia tú el valor de
`API_BASE_URL` de tu `local.properties` por el **dominio estable**, con `/` final:

```properties
API_BASE_URL=https://TU-PROYECTO.vercel.app/
```

La propiedad se incorpora al APK al compilar; un APK existente seguirá apuntando
a Railway. También puedes sobrescribirla para una compilación concreta:

```powershell
.\gradlew.bat assembleDebug -PAPI_BASE_URL=https://TU-PROYECTO.vercel.app/
```

Esta dirección es pública. Nunca coloques `DATABASE_URL`, `SECRET_KEY` ni
`CRON_SECRET` en Android. La versión queda preparada como `1.6.1-dev`,
`versionCode=9`, superior al `8` de la versión anterior. Conserva el mismo
`applicationId` y la misma firma. Instálala como actualización: no desinstales la app ni borres
su almacenamiento, porque puede contener registros offline pendientes.

Prueba login, consulta de datos, registro offline, sincronización y un reintento
sin duplicación. Usa una comunidad/base de pruebas para crear datos de ensayo.
Los timeouts actuales de Android (30 segundos al conectar y 60 al leer) admiten
la reactivación habitual; la función Vercel tiene un máximo de 60 segundos por
petición. Comprueba los tiempos reales con tu región y plan.

## 8. Retirar Railway y poder volver atrás

Mantén Railway disponible mientras validas Vercel y actualizas los teléfonos.
Los APK antiguos no aprenden automáticamente el dominio nuevo. Cuando todos
usen el APK actualizado y la sincronización esté validada, detén o elimina tú
el servicio de Railway y revisa su facturación/suscripción y cualquier otro
recurso que siga consumiendo. Quitar `railway.toml` de Git no cancela cargos.
No elimines el proyecto ni la rama de Neon que contiene tus datos.

Para volver temporalmente a Railway antes de retirarlo, conserva su configuración
y vuelve a usar su dominio en una actualización de Android. `railway.toml`,
`Procfile` y Gunicorn permanecen como respaldo de transición; Vercel usa su propia
configuración. Como no se cambia el esquema ni la base, no hace falta restaurar
datos por el mero cambio de alojamiento.

## Verificación automatizada disponible

CI ejecuta pruebas en Python 3.12 para `main` y `dev`, valida la configuración
Vercel y recolecta estáticos usando una URL PostgreSQL ficticia. Las pruebas
cubren arranque sin conexiones, rechazo de SQLite/DEBUG/comodines en Vercel,
dominios exactos y autorización/retención del cron. Una compilación real de
Vercel y la prueba web/API/Android siguen siendo necesarias tras configurar
las variables privadas.

Validación local realizada: **80 pruebas aprobadas**, sin migraciones nuevas,
login HTTPS y CSS/logos/admin con el manifiesto generado. El Python instalado
localmente es 3.14.5; CI y Vercel están fijados a 3.12, y la ejecución remota
de CI sigue pendiente de publicar los cambios. `check --deploy` solo advierte
de HSTS en cero. Android generó correctamente `BuildConfig` con JDK 17 y una
URL ficticia de Vercel; no se generó un APK nuevo de distribución ni se verificó
todavía una conexión real de Android a Vercel.
