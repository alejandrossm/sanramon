# Plan de trabajo - modulo de autenticacion y usuarios

## Objetivo

Construir el primer modulo del sistema de asistencia QR: autenticacion, registro y gestion inicial de usuarios. No se implementaran funcionalidades de asistencia, lectura QR, reuniones, reportes, bloqueos, exportaciones ni auditoria completa en esta etapa.

## Estructura recomendada

```text
sanramon/
├── config/
│   ├── settings.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
├── usuarios/
│   ├── migrations/
│   ├── templates/
│   │   └── usuarios/
│   │       ├── dashboard.html
│   │       ├── editar_usuario.html
│   │       ├── listado_usuarios.html
│   │       ├── login.html
│   │       └── registro_usuario.html
│   ├── admin.py
│   ├── apps.py
│   ├── forms.py
│   ├── models.py
│   ├── tests.py
│   ├── urls.py
│   └── views.py
├── templates/
│   └── base.html
├── static/
│   └── css/
│       └── styles.css
├── manage.py
├── requirements.txt
└── .gitignore
```

El registro de asistencia, reuniones y consultas de socios se centralizara dentro de la app `usuarios`. No se mantendra una app separada `asistencia_qr`.

## Decision tecnica principal

Se usara un modelo de usuario personalizado basado en `AbstractUser`. Como el proyecto esta en etapa inicial, esta alternativa es simple, mantenible y deja el campo `rut`, el correo unico, el rol y el estado activo dentro del usuario principal sin crear perfiles adicionales.

## Roles

- `ADMINISTRADOR`: puede registrar, listar, editar, activar y desactivar usuarios.
- `ENCARGADO_REGISTRO`: puede iniciar sesion y ver un dashboard operativo futuro.
- `SOCIO`: puede iniciar sesion y queda preparado para consultas futuras.
- Superusuario Django: mantiene acceso exclusivo al admin tradicional.

## Integridad de socios

- Un socio mantiene siempre el rol `SOCIO`; no puede ser promovido a `ADMINISTRADOR` ni a `ENCARGADO_REGISTRO`.
- Las cuentas con rol `SOCIO` no pueden recibir privilegios `is_staff` ni `is_superuser`.
- La regla se valida en el modelo y se refuerza en formularios, vistas y admin de Django para evitar bypasses por canales alternativos.

## Pasos de implementacion

1. Crear app `usuarios`.
2. Configurar `settings.py`:
   - instalar `usuarios`
   - configurar `AUTH_USER_MODEL`
   - activar `crispy_forms` y `crispy_bootstrap5`
   - configurar templates y static
3. Crear modelo `Usuario` con:
   - username
   - first_name
   - last_name
   - rut unico
   - email unico
   - password
   - rol
   - is_active
4. Crear formularios con crispy forms:
   - login
   - registro
   - edicion
5. Crear vistas:
   - login
   - logout
   - dashboard
   - registro de usuario
   - listado de usuarios
   - edicion de usuario
   - activacion/desactivacion
6. Crear reglas de acceso:
   - gestion de usuarios solo para administradores o superusuarios
   - usuarios autenticados pueden entrar al dashboard
   - socios sin acceso al panel interno de administracion
7. Crear templates Bootstrap 5:
   - `base.html`
   - `login.html`
   - `registro_usuario.html`
   - `listado_usuarios.html`
   - `editar_usuario.html`
   - `dashboard.html`
8. Configurar URLs principales y URLs de la app.
9. Agregar estilos CSS propios, livianos y mantenibles.
10. Actualizar dependencias en `requirements.txt`.
11. Generar migraciones.
12. Validar con:
   - `python manage.py check`
   - `python manage.py makemigrations --check --dry-run`
   - `python manage.py test`

## Alcance excluido

- Registro de asistencia.
- Lectura QR.
- Gestion de reuniones.
- Reportes.
- Bloqueos por inasistencia.
- Exportaciones.
- Auditoria completa.

## Decisiones pendientes con cliente

- Recuperacion de contrasena por correo: revisar con el cliente si se implementa y definir el proveedor de envio.
- Alternativas a evaluar:
  - Gmail: opcion simple y gratuita para bajo volumen, usando una cuenta dedicada del sistema y contrasena de aplicacion.
  - Mailgun: opcion mas orientada a correos transaccionales, con plan gratuito de bajo volumen y mejor trazabilidad para produccion.
- Definicion recomendada antes de implementar: confirmar proveedor, correo remitente, dominio si aplica, limites de envio aceptables y si el flujo aplica solo a usuarios internos activos o tambien a socios.

## Pendientes de despliegue y seguridad

- Configurar `DEBUG=False` para el entorno de produccion.
- Reemplazar `SECRET_KEY` por una clave larga, aleatoria y gestionada por variable de entorno.
- Definir si el sitio operara solo por HTTPS y, si corresponde, activar `SECURE_SSL_REDIRECT` o configurar la redireccion en el proxy/load balancer.
- Activar `SESSION_COOKIE_SECURE=True` cuando el sitio use HTTPS.
- Activar `CSRF_COOKIE_SECURE=True` cuando el sitio use HTTPS.
- Evaluar y configurar `SECURE_HSTS_SECONDS` solo cuando HTTPS este validado en todo el dominio.

## Criterio de termino

El sprint termina cuando el sistema permite iniciar sesion, cerrar sesion, mostrar dashboard por rol y administrar usuarios desde vistas propias para administradores, dejando el proyecto listo para el siguiente modulo.
