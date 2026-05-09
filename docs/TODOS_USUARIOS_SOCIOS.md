# TODOs usuarios y socios

Pendientes para una siguiente iteracion del modulo de usuarios, socios y asistencia.

## Interfaz

- [x] Implementar SweetAlert para reemplazar o complementar mensajes de confirmacion, exito y error.
- [x] Aplicar formateo visual del RUT en el formulario, del lado del cliente, para mejorar la lectura mientras se escribe.
- [ ] Ajustar en el listado de usuarios el boton de desactivacion del usuario autenticado: debe verse con estilo deshabilitado, ya que no se permite desactivar la propia cuenta.
- [x] Documentar la correccion de estilos del admin de Django en PythonAnywhere: ejecutar `collectstatic`, mapear `/static/` a `staticfiles` y verificar `/static/admin/css/base.css`.

## Seguridad

- [x] Separar administradores web de superadministradores Django: `ADMINISTRADOR` queda para el sistema web y `SUPERADMINISTRADOR` queda reservado para cuentas `is_staff` e `is_superuser`.
- [x] Ocultar superadministradores del listado web de usuarios e impedir que se editen, desactiven o eliminen desde las vistas del sistema.
- [ ] Endurecer configuracion HTTPS de produccion: activar `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` y evaluar `SECURE_HSTS_SECONDS` despues de confirmar que todo el sitio opera solo por HTTPS.
- [ ] Activar `Force HTTPS` en PythonAnywhere para que `http://alejandrossm.pythonanywhere.com/` redirija a `https://alejandrossm.pythonanywhere.com/`.
- [ ] Agregar proteccion contra fuerza bruta en login, por ejemplo `django-axes` o rate limiting equivalente.
- [ ] Bloquear en produccion los comandos demo que crean usuarios con passwords predecibles, especialmente `crear_usuarios_prueba`.
- [ ] Validar globalmente que ningun `username` coincida con el `email` de cualquier cuenta, y que ningun `email` coincida con el `username` de otra cuenta, para evitar ambiguedades en el login por usuario o correo.

## Socios

- [x] Usar el correo electronico registrado como usuario tecnico del socio.
- [x] Editar socios exclusivamente mediante un formulario especifico de socio.
- [x] Impedir cambios de perfil en socios: un socio siempre debe conservar el rol `SOCIO`.
- [x] Mostrar en la vista de socios el total de reuniones, total de asistencias y total de ausencias.
- [x] Agregar indicador visual por socio:
  - Verde: sin ausencias.
  - Amarillo: una inasistencia.
  - Rojo: bloqueado por dos inasistencias.

## Pendientes por definir

- [x] Modo seguro de eliminacion: solo se pueden eliminar socios sin asistencias contabilizadas; los encargados de registro solo se activan o desactivan.
