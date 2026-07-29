# Despliegue en PythonAnywhere

Guia para publicar este proyecto Django en PythonAnywhere usando virtualenv, variables de entorno y archivos estaticos servidos por la plataforma.

## 1. Version de Python

El proyecto usa Django 6.0.7. En PythonAnywhere conviene usar Python 3.13 en una cuenta con system image `innit`.

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

<https://myaccount.google.com/apppasswords>

Ejemplo:

```bash
export DJANGO_SECRET_KEY="clave-generada"
export DJANGO_DEBUG="False"
export DJANGO_ALLOWED_HOSTS="tuusuario.pythonanywhere.com"
export DJANGO_CSRF_TRUSTED_ORIGINS="https://tuusuario.pythonanywhere.com"
export DJANGO_SECURE_SSL_REDIRECT="True"
export DJANGO_SESSION_COOKIE_SECURE="True"
export DJANGO_CSRF_COOKIE_SECURE="True"
export DJANGO_SECURE_HSTS_SECONDS="3600"
export DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS="False"
export DJANGO_SECURE_HSTS_PRELOAD="False"
export EMAIL_HOST="smtp.gmail.com"
export EMAIL_PORT="587"
export EMAIL_USE_TLS="True"
export EMAIL_HOST_USER="tu-cuenta@gmail.com"
export EMAIL_HOST_PASSWORD="clave-de-aplicacion-gmail"
export DEFAULT_FROM_EMAIL="Sistema San Ramon <tu-cuenta@gmail.com>"
export CONSULTA_CODIGO_DURACION_MINUTOS="10"
export CONSULTA_CODIGO_MAX_INTENTOS="5"
export CONSULTA_CODIGO_VENTANA_MINUTOS="2"
export CONSULTA_CODIGO_MAX_SOLICITUDES_SOCIO="3"
export CONSULTA_SESION_DURACION_MINUTOS="15"
export CONSULTA_CODIGO_RETENCION_DIAS="30"
export SEGURIDAD_LOGIN_VENTANA_MINUTOS="15"
export SEGURIDAD_LOGIN_MAX_IDENTIFICADOR="5"
export SEGURIDAD_LOGIN_MAX_IP="20"
export SEGURIDAD_RECUPERACION_VENTANA_MINUTOS="60"
export SEGURIDAD_RECUPERACION_MAX_IDENTIFICADOR="3"
export SEGURIDAD_RECUPERACION_MAX_IP="10"
export SEGURIDAD_REAUTENTICACION_MINUTOS="10"
export SEGURIDAD_INTENTOS_RETENCION_DIAS="30"
export RESPALDO_ENCRYPTION_KEYS="clave-fernet"
export AUDITORIA_HMAC_KEY="secreto-hmac-independiente"
export AUDITORIA_ROTACION_BYTES="10485760"
export AUDITORIA_RETENCION_MESES="12"
export CARGA_CSV_MAX_BYTES="2097152"
```

Para usar una cuenta Gmail gratuita en el envio de recuperacion de contrasena, activar la verificacion en 2 pasos de Google y crear una clave de aplicacion para `EMAIL_HOST_PASSWORD`. No usar la contrasena normal de Gmail en el archivo `.env`.

Generar las claves de respaldo y auditoria:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

No guardar estas claves en Git ni en la base de datos. Perder todas las claves
Fernet impide restaurar respaldos. Para rotarlas, agregar la nueva al inicio de
`RESPALDO_ENCRYPTION_KEYS` y conservar temporalmente las anteriores separadas
por coma.

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
python manage.py verificar_identidades
python manage.py collectstatic --noinput
```

Las solicitudes de verificacion con mas de 30 dias se eliminan de forma
oportunista al recibir nuevas solicitudes OTP. La aplicacion limita esta
limpieza a una ejecucion diaria por proceso.

## Restaurar un respaldo cifrado

Con las claves cargadas en el entorno y fuera del directorio web:

```bash
python manage.py shell -c "from pathlib import Path; from usuarios.respaldos import descifrar_respaldo; origen=Path('/ruta/respaldo.sqlite3.fernet'); Path('/ruta/restaurado.sqlite3').write_bytes(descifrar_respaldo(origen.read_bytes()))"
```

Detener escrituras, verificar la copia restaurada y no conservar el archivo
descifrado en un directorio público.

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

## Retorno a la version anterior

Antes de cada despliegue, registrar el commit activo y crear un respaldo cifrado
verificado. Si el candidato falla:

1. Detener escrituras o poner la aplicacion en mantenimiento.
2. Volver al commit o tag anterior conocido.
3. Restaurar el entorno con sus dependencias fijadas.
4. Si hubo una migracion incompatible, restaurar el respaldo de base de datos
   previo al despliegue en vez de intentar revertir datos manualmente.
5. Ejecutar `python manage.py check --deploy`, `python manage.py
   verificar_identidades` y `collectstatic`.
6. Recargar la aplicacion y comprobar login, correo y archivos estaticos antes
   de reabrir escrituras.

El commit anterior puede registrarse antes del despliegue con:

```bash
git rev-parse HEAD
```

## 7. HTTPS

En `Web > Security`, activar `Force HTTPS` despues de tener certificado HTTPS disponible. En el subdominio `tuusuario.pythonanywhere.com` PythonAnywhere ya entrega certificado; en un dominio propio, primero hay que configurar el certificado.

El proyecto activa redireccion HTTPS y cookies `Secure` automáticamente cuando
`DEBUG=False`; las variables anteriores lo dejan explícito en producción.

Para HSTS:

1. Publicar con certificado válido y `Force HTTPS`.
2. Verificar login, recuperación, consulta OTP, administración y archivos estáticos.
3. Comenzar con `DJANGO_SECURE_HSTS_SECONDS=3600`.
4. Aumentar gradualmente el valor después de observar el despliegue.
5. Mantener `INCLUDE_SUBDOMAINS` y `PRELOAD` desactivados hasta confirmar que
   todos los subdominios funcionan exclusivamente con HTTPS.

En desarrollo local conservar `DJANGO_DEBUG=True` y no definir las variables
`DJANGO_SECURE_*`; de esta forma `http://127.0.0.1:8000` sigue funcionando.

## 8. Primer usuario administrativo

Si la base de datos parte vacia:

```bash
python manage.py createsuperuser
```

Ese comando crea una cuenta especializada para `/admin/` de Django. No reemplaza al rol `ADMINISTRADOR` del sistema web y no debe gestionarse desde el listado web de usuarios.

El archivo `db.sqlite3` no se versiona. Si se necesita conservar la base local, hay que subirla manualmente a `~/sanramon/db.sqlite3` antes de ejecutar la app.
