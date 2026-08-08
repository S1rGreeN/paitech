# PaiPayTech Django

Backend, web comunitaria y API REST del sistema de monitoreo acuícola de Paipayales.

## Alcance v1.4

- Usuarios administrados en Django e inicio de sesión por correo.
- Comunidad, especies y piscinas; una especie permanente por piscina de peces.
- Jornadas con agua, biometría o ambos bloques y población estimada obligatoria.
- Peces anónimos con peso en gramos y longitud total en centímetros.
- Movimientos explícitos de población y cálculo de población teórica.
- Correcciones con versión optimista y anulaciones lógicas auditadas.
- API para Android con UUID idempotentes y semáforo comunitario.
- Lombricultura visible como “Próximamente”; laboratorio fuera de v1.4.
- Neon PostgreSQL como base compartida y Railway como destino de despliegue.

El contrato móvil está documentado en [API.md](API.md) y las decisiones generales en `../decisiones.md`.

## Desarrollo local en Windows

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

La v1.4 usa `db_v14.sqlite3`. El antiguo `db.sqlite3` no se modifica y queda como respaldo del prototipo.

Credenciales de demostración:

```text
acuicultor@paipay.local / ${PAIPAY_ACUICULTOR_PASSWORD}
admin@paipay.local / ${PAIPAY_ADMIN_PASSWORD}
```

## Verificación

```powershell
python manage.py makemigrations --check --dry-run
python manage.py check
python manage.py test
python manage.py collectstatic --noinput
```

## Railway + Neon

1. Crear un servicio Railway desde este repositorio y seleccionar la rama `dev` durante las pruebas.
2. Configurar `DATABASE_URL` con la cadena PostgreSQL de Neon.
3. Configurar `SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS`.
4. Mantener `SECURE_HSTS_SECONDS=0` durante la primera validación HTTPS; elevarlo solo cuando el dominio sea definitivo.
5. Railway usará `railway.toml`: recolecta estáticos, ejecuta migraciones y levanta Gunicorn.
6. Validar `GET /api/v1/health/` antes de apuntar Android al dominio.

No se guardan credenciales de Neon en la aplicación Android. Django es la única capa que accede a la base central.
