# PaiPayTech

MVP en Django para registrar y visualizar mediciones de piscinas acuícolas de Santa Lucía PaiPay.

## Funcionalidades

- Login y sesiones con Django.
- Perfil de acuicultor.
- Piscina de peces con historial y nuevos registros.
- Datos de pH, nitrato, amonio, nitrito y población estimada.
- Múltiples muestras de peces por registro: especie, peso y talla.
- Piscina de lombrices visible como funcionalidad del siguiente sprint.
- SQLite 3 local y configuración lista para Neon PostgreSQL.
- Templates Jinja2 con Tailwind CSS y paleta oficial PaiPay.
- Vista previa estática en `docs/` para GitHub Pages.
- Preparación para Vercel.
- Integración continua con GitHub Actions.

## Inicio rápido en Windows

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Abre `http://127.0.0.1:8000/`.

Usuario demo:

```text
acuicultor / ${PAIPAY_ACUICULTOR_PASSWORD}
```

Administrador local:

```text
admin / ${PAIPAY_ADMIN_PASSWORD}
```

## Pruebas

```powershell
python manage.py test
python manage.py check
```

## Documentación

- Guía completa: [`GUIA_COMPLETA.md`](GUIA_COMPLETA.md)
- Modelo y diagramas: [`ARQUITECTURA.md`](ARQUITECTURA.md)

## Nota sobre GitHub Pages

GitHub Pages solo ejecuta contenido estático. La carpeta `docs/` contiene una vista previa visual; el backend Django funciona localmente y, en el siguiente sprint, se despliega en Vercel con Neon.
