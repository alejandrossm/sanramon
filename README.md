# SISTEMA ASISTENCIA VALLE SAN RAMON

Version candidata: `1.0.0` (aun sin tag).

## Requisitos

- Python 3.13
- Dependencias fijadas en `requirements.txt`

## Validacion

```bash
python -m pip install -r requirements.txt
python manage.py makemigrations --check --dry-run
python manage.py test
```

## Paquete de produccion

```bash
python scripts/construir_release.py
```

El ZIP generado en `dist/` contiene solo los archivos requeridos por la
aplicacion. La documentacion, pruebas, CI y comandos internos permanecen
exclusivamente en el repositorio de trabajo.

## Despliegue

- [PythonAnywhere](docs/PYTHONANYWHERE.md)
- [Checklist del release 1.0.0](docs/RELEASE_1.0.0.md)
- [Memoria de cumplimiento de la Ley 21.719](docs/MEMORIA_CUMPLIMIENTO_LEY_21719.md)
