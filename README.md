# PaiPayTech Django

Backend, web comunitaria y API REST del sistema PaiPayTech para comunidades de
acuicultura y lombricultura.

## Alcance v1.6-dev

- Usuarios administrados en Django e inicio de sesión por correo.
- Varias comunidades aisladas; cada cuenta pertenece exactamente a una.
- Especies globales y piscinas de peces con una especie permanente.
- Camas de lombrices separadas de las piscinas, con ciclos, pH del suelo y
  conteo real de lombrices.
- Ciclos productivos desde población inicial hasta cierre completo de la cohorte.
- Predicción transparente por mediana de supervivencia histórica de la misma piscina.
- Jornadas con agua, biometría o ambos bloques y población estimada obligatoria.
- Recordatorios no bloqueantes: agua semanal y biometría mensual.
- Peces anónimos con peso en gramos y longitud total en centímetros.
- Movimientos explícitos de población y cálculo de población teórica.
- Correcciones con versión optimista y anulaciones lógicas auditadas.
- API para Android con UUID idempotentes, comunidad identificada mediante UUID
  público y semáforo por perfil de especie.
- Estructura futura de sensores horarios vía API, deshabilitada por configuración.
- Ensayos de laboratorio fuera del alcance vigente.
- Neon PostgreSQL como base compartida y Railway como destino de despliegue.

El contrato móvil está documentado en [API.md](API.md), la línea base de
seguridad en [SECURITY.md](SECURITY.md) y las decisiones generales en
`../decisiones.md`.

## Desarrollo local en Windows

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --require-hashes -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

La base local conserva el archivo `db_v14.sqlite3` y aplica las migraciones de
v1.6. El antiguo `db.sqlite3` no se modifica y queda como respaldo del prototipo.

El comando muestra credenciales aleatorias únicamente cuando crea las cuentas.
Si las cuentas ya existen y necesitas claves nuevas, ejecuta:

```powershell
python manage.py seed_demo --rotar-claves
```

Las claves demo no se guardan en Git. Este comando es solo para desarrollo
local: se bloquea con `DEBUG=False` y también ante cualquier base que no sea
SQLite. Nunca debe ejecutarse en Neon ni crear una piscina legada para lombrices.

## Dependencias reproducibles

Python queda fijado a la familia `3.12` mediante `.python-version`. Las
dependencias directas de producción se declaran con versión exacta en
`requirements.in`; `requirements.txt` contiene además todas las dependencias
transitivas y los hashes aceptados para cada paquete. Railway y CI deben instalar
siempre con `--require-hashes`: si una versión o archivo descargado no coincide,
la instalación se detiene.

Para actualizar deliberadamente las dependencias desde un entorno Python 3.12:

```powershell
python -m pip install pip-tools==7.6.1 pip-audit==2.10.1
python -m piptools compile --upgrade --generate-hashes --strip-extras --output-file requirements.txt requirements.in
python -m pip install --require-hashes -r requirements.txt
python -m pip check
python -m pip_audit -r requirements.txt --disable-pip
python manage.py test
```

No se edita `requirements.txt` a mano. Toda actualización comienza en
`requirements.in` y debe revisar el diff, la compatibilidad documentada y las
pruebas antes de versionarse.

## Inicialización del catálogo real

Después de ejecutar migraciones sobre una base Neon vacía, crear el catálogo
mínimo confirmado con:

```powershell
python manage.py inicializar_catalogo_paipayales
```

Aunque conserva su nombre histórico, el comando es idempotente y crea o valida
el catálogo multi-comunidad confirmado:

- `Paipayales`: Vieja Azul (*Andinoacara rivulatus*), piscina `P-01` y cama
  `C-01`, sin áreas inventadas;
- `Colegio Galo Plaza Lasso`: Tilapia, piscina `P-01` y ninguna cama;
- perfiles versionados de semáforo para ambas especies. El perfil de Tilapia es
  provisional hasta confirmar el nombre científico y validarlo con un profesional.

No crea usuarios, contraseñas, ciclos ni registros operativos. Si encuentra esos
códigos con una identidad incompatible, se detiene en vez de sobrescribir
información.

## Alta manual de usuarios operativos

Las cuentas reales se crean de forma interactiva para que ninguna contraseña
quede en el código, el historial de Git, los argumentos del proceso ni la salida
de la terminal. El comando solicita la contraseña dos veces con entrada oculta y
aplica la política de contraseñas de Django (8 a 32 caracteres, no común, no
exclusivamente numérica y sin similitud obvia con la cuenta). Toda cuenta creada
por este comando recibe una contraseña temporal y debe reemplazarla en el primer
acceso.

Para la dotación inicial acordada, ejecutar desde una consola privada del
servicio Django —localmente durante pruebas o en Railway después de migrar la
base vacía de Neon—:

```powershell
# Una sola cuenta para mantenimiento técnico completo
python manage.py crear_usuario_operativo --rol tecnico --comunidad paipayales

# Ejecutar tres veces, con correos distintos
python manage.py crear_usuario_operativo --rol administrador --comunidad paipayales

# Ejecutar dos veces, con correos distintos
python manage.py crear_usuario_operativo --rol acuicultor --comunidad paipayales
```

El usuario `tecnico` es el único superusuario. Los administradores funcionales
pueden gestionar cuentas ordinarias, piscinas y camas de su comunidad, y
consultar los datos y auditorías de esa misma comunidad. Las especies y sus
perfiles son catálogos globales administrados solo por el superusuario técnico.
Los administradores funcionales no pueden convertirse en superusuarios, asignar
grupos o permisos, eliminar datos ni modificar directamente cuentas
privilegiadas. Los
acuicultores no tienen acceso a Django Admin y usan la web/API comunitaria.

No se deben usar correos ni contraseñas reales en ejemplos, migraciones,
fixtures o scripts. Para cambiar una clave existente se usa el mecanismo seguro
de Django desde una consola privada, no una sentencia SQL manual.

## Verificación

```powershell
python manage.py makemigrations --check --dry-run
python manage.py check
python manage.py check --deploy
python manage.py test
python manage.py collectstatic --noinput
```

## Limpieza de datos ficticios en Development

La limpieza operativa nunca se ejecuta dentro de una migración. Primero se
revisan los conteos sin modificar nada:

```powershell
python manage.py limpiar_datos_operativos_desarrollo
```

Solo después de comprobar que Railway/Neon corresponden al entorno
`development`, se confirma explícitamente:

```powershell
python manage.py limpiar_datos_operativos_desarrollo --ejecutar --confirmar BORRAR-DATOS-DESARROLLO
```

El comando rechaza producción y elimina jornadas, movimientos, ciclos,
auditorías operativas, registros/ciclos de lombricultura, lecturas y dispositivos
sensores ficticios. Conserva usuarios, perfiles, comunidades, especies,
piscinas y camas.

## Railway + Neon

1. Crear un servicio Railway desde este repositorio y seleccionar la rama `dev` durante las pruebas.
2. Configurar `DATABASE_URL` con la cadena PostgreSQL de Neon.
3. Configurar `SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS`,
   `CSRF_TRUSTED_ORIGINS` y `TRUST_X_FORWARDED_FOR=True`.
4. Mantener `SECURE_HSTS_SECONDS=0` durante la primera validación HTTPS; elevarlo solo cuando el dominio sea definitivo.
5. Railway usará Railpack mediante `railway.toml`: instala el archivo bloqueado,
   recolecta estáticos, ejecuta migraciones y levanta Gunicorn.
6. Ejecutar `python manage.py inicializar_catalogo_paipayales` una sola vez desde una consola privada; repetirlo es seguro.
7. Crear las seis cuentas reales con `crear_usuario_operativo`; no ejecutar `seed_demo`.
8. Validar `GET /api/v1/health/` antes de apuntar Android al dominio.
9. Programar `python manage.py limpiar_eventos_seguridad` diariamente para
   aplicar la retención de 30 días de eventos de acceso.
10. Mantener `SENSORES_HABILITADOS=False` hasta aprobar el hardware y sus claves.

No se guardan credenciales de Neon en la aplicación Android. Django es la única capa que accede a la base central.
