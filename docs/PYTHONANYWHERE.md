# Despliegue en PythonAnywhere

Guia para publicar este proyecto Django en PythonAnywhere usando virtualenv, variables de entorno y archivos estaticos servidos por la plataforma.

## 1. Version de Python

El proyecto usa Django 6.0.4. En PythonAnywhere conviene usar Python 3.13 en una cuenta con system image `innit`.

En una consola Bash de PythonAnywhere:

```bash
mkvirtualenv sanramon --python=python3.13
```

Si `python3.13` no existe en la cuenta, revisar `Account > System Image` y cambiar a `innit`.

## 2. Subir codigo e instalar dependencias

```bash
cd ~
git clone <url-del-repositorio> sanramon
cd ~/sanramon
workon sanramon
pip install -r requirements.txt
```

## 3. Crear variables de entorno

Crear `~/sanramon/.env` tomando como base `.env.example`.

Para generar una clave segura:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Ejemplo:

```bash
export DJANGO_SECRET_KEY="clave-generada"
export DJANGO_DEBUG="False"
export DJANGO_ALLOWED_HOSTS="tuusuario.pythonanywhere.com"
export DJANGO_CSRF_TRUSTED_ORIGINS="https://tuusuario.pythonanywhere.com"
```

Para que las variables tambien existan en consolas Bash al activar el virtualenv:

```bash
echo 'set -a; source ~/sanramon/.env; set +a' >> ~/.virtualenvs/sanramon/bin/postactivate
workon sanramon
```

## 4. Configurar Web app

En `Web` crear una app con `Manual configuration`, usando la misma version de Python del virtualenv.

En `Virtualenv`, configurar:

```text
/home/tuusuario/.virtualenvs/sanramon
```

En `Code`, configurar `Source code` y `Working directory`:

```text
/home/tuusuario/sanramon
```

## 5. Editar WSGI de PythonAnywhere

Editar el archivo WSGI enlazado desde la pestaña `Web`. No es el archivo `config/wsgi.py` del repo.

Contenido sugerido:

```python
import os
import sys

from dotenv import load_dotenv

path = '/home/tuusuario/sanramon'
if path not in sys.path:
    sys.path.insert(0, path)

load_dotenv(os.path.join(path, '.env'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

## 6. Base de datos y estaticos

```bash
cd ~/sanramon
workon sanramon
python manage.py migrate
python manage.py collectstatic --noinput
```

En `Web > Static files`, agregar:

```text
URL:       /static/
Directory: /home/tuusuario/sanramon/staticfiles
```

Luego presionar `Reload`.

Verificar especialmente los estilos del admin de Django abriendo:

```text
https://tuusuario.pythonanywhere.com/static/admin/css/base.css
```

Si esa URL no muestra CSS, revisar que `collectstatic` haya creado `staticfiles/admin/css/base.css` y que el mapeo `/static/` apunte a `/home/tuusuario/sanramon/staticfiles`, no a `/home/tuusuario/sanramon/static`.

## 7. HTTPS

En `Web > Security`, activar `Force HTTPS` despues de tener certificado HTTPS disponible. En el subdominio `tuusuario.pythonanywhere.com` PythonAnywhere ya entrega certificado; en un dominio propio, primero hay que configurar el certificado.

## 8. Primer usuario administrativo

Si la base de datos parte vacia:

```bash
python manage.py createsuperuser
```

Ese comando crea una cuenta especializada para `/admin/` de Django. No reemplaza al rol `ADMINISTRADOR` del sistema web y no debe gestionarse desde el listado web de usuarios.

El archivo `db.sqlite3` no se versiona. Si se necesita conservar la base local, hay que subirla manualmente a `~/sanramon/db.sqlite3` antes de ejecutar la app.
