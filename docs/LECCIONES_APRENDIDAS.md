# Lecciones aprendidas

Notas reutilizables para futuras implementaciones del sistema.

## Separacion entre administracion web y Django admin

### Contexto

El rol `ADMINISTRADOR` del sistema web no debe confundirse con el superusuario de Django. Son responsabilidades distintas:

- `ADMINISTRADOR`: administra usuarios, socios y flujos propios de la aplicacion web.
- `SUPERADMINISTRADOR`: cuenta tecnica especializada para entrar a `/admin/` de Django.

### Riesgo detectado

Si ambos conceptos se mezclan, un administrador web podria ver, editar, desactivar o eliminar cuentas tecnicas de Django desde vistas del sistema. Tambien podria quedar expuesto el superusuario en listados, metricas o acciones masivas.

### Regla aplicada

- El acceso a `/admin/` exige `is_active=True`, `is_staff=True` e `is_superuser=True`.
- Todo `is_superuser=True` debe usar rol `SUPERADMINISTRADOR`.
- El rol `SUPERADMINISTRADOR` solo puede existir en cuentas `is_superuser=True`.
- Todo `is_staff=True` debe ser tambien `is_superuser=True`.
- El rol `ADMINISTRADOR` queda reservado para permisos del sistema web, sin acceso staff al admin de Django.

### Visibilidad y acciones

- Las cuentas superadministradoras no se muestran en el listado web de usuarios.
- Las cuentas superadministradoras no se cuentan en las metricas del dashboard web.
- Las vistas web deben bloquear edicion, cambio de estado y eliminacion de superusuarios aunque se intente acceder por URL directa.
- Los formularios web no deben ofrecer `SUPERADMINISTRADOR` como opcion de rol.

### Migraciones y datos existentes

Cuando se agregue una restriccion de seguridad sobre datos ya existentes:

- Primero migrar los datos actuales a un estado valido.
- Despues agregar las restricciones de base de datos.
- Cubrir el caso de superusuarios existentes con una migracion de datos.
- Normalizar flags heredados como `is_staff` antes de crear constraints.

### Pruebas minimas esperadas

- `createsuperuser` asigna automaticamente `SUPERADMINISTRADOR`.
- Un usuario no superuser no puede guardar rol `SUPERADMINISTRADOR`.
- Un usuario con rol `ADMINISTRADOR` no puede convertirse en `is_superuser`.
- Un usuario `is_staff=True` sin `is_superuser=True` queda rechazado.
- El listado web oculta superadministradores.
- Un administrador web no puede editar, desactivar ni eliminar un superadministrador por URL directa.
- `/admin/` acepta solo superusuarios activos con staff.

### Checklist para futuros modulos

- Separar roles de negocio de permisos tecnicos de framework.
- No usar `is_superuser` como sinonimo de administrador funcional.
- No mostrar cuentas tecnicas en listados operativos.
- Validar permisos tanto en la interfaz como en la vista backend.
- Agregar constraints de modelo/base de datos para invariantes de seguridad.
- Probar los caminos directos por URL, no solo los botones visibles.

## Revision de seguridad antes de publicar

### Puntos pendientes detectados

- Forzar HTTPS en la plataforma y en Django cuando `DEBUG=False`.
- Marcar cookies de sesion y CSRF como `Secure` en produccion.
- Evaluar HSTS solo despues de confirmar que todo el sitio funciona por HTTPS.
- Agregar proteccion contra fuerza bruta en el formulario de login.
- Bloquear comandos demo en produccion si crean usuarios con credenciales predecibles.
- Evitar colisiones globales entre `username` y `email` porque el login acepta ambos identificadores.

### Ejemplo de colision de login

El backend autentica con `username` o `email`. Por eso debe impedirse este escenario:

- Usuario A tiene `username="persona@correo.com"`.
- Usuario B tiene `email="persona@correo.com"`.

En ese caso el backend puede encontrar mas de una cuenta y rechazar el inicio de sesion para ese identificador.
