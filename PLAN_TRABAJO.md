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

La app `asistencia_qr` se conserva en el proyecto como espacio reservado para el modulo de registro de asistencia futuro. En este sprint no se registra en `INSTALLED_APPS` ni se implementa logica dentro de ella.

## Decision tecnica principal

Se usara un modelo de usuario personalizado basado en `AbstractUser`. Como el proyecto esta en etapa inicial, esta alternativa es simple, mantenible y deja el campo `rut`, el correo unico, el rol y el estado activo dentro del usuario principal sin crear perfiles adicionales.

## Roles

- `ADMINISTRADOR`: puede registrar, listar, editar, activar y desactivar usuarios.
- `ENCARGADO_REGISTRO`: puede iniciar sesion y ver un dashboard operativo futuro.
- `SOCIO`: puede iniciar sesion y queda preparado para consultas futuras.
- Superusuario Django: mantiene acceso al admin tradicional.

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

## Criterio de termino

El sprint termina cuando el sistema permite iniciar sesion, cerrar sesion, mostrar dashboard por rol y administrar usuarios desde vistas propias para administradores, dejando el proyecto listo para el siguiente modulo.
