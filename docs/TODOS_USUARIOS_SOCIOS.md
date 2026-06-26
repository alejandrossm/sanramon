# TODOs usuarios y socios

Pendientes para una siguiente iteracion del modulo de usuarios, socios y asistencia.

## Interfaz

- [x] Implementar SweetAlert para reemplazar o complementar mensajes de confirmacion, exito y error.
- [x] Aplicar formateo visual del RUT en el formulario, del lado del cliente, para mejorar la lectura mientras se escribe.
- [x] Ajustar en el listado de usuarios el boton de desactivacion del usuario autenticado: debe verse con estilo deshabilitado, ya que no se permite desactivar la propia cuenta.
- [x] Agregar filtro por rol en el listado de usuarios.
- [x] Documentar la correccion de estilos del admin de Django en PythonAnywhere: ejecutar `collectstatic`, mapear `/static/` a `staticfiles` y verificar `/static/admin/css/base.css`.
- [x] Corregir tildes faltantes en etiquetas, ayudas y mensajes de los formularios.
- [x] Sprint 3 HU-12: crear landing page publica tipo index, con informacion del proyecto, imagenes, navbar, acceso al sistema interno, acceso de socios a consulta por RUT y footer con contacto/redes.
- [x] Revisar estilos de placeholder en inputs: el texto de ayuda se percibe como valor ingresado por el usuario y debe diferenciarse visualmente.

## Seguridad antes de produccion

- [x] Separar administradores web de superadministradores Django: `ADMINISTRADOR` queda para el sistema web y `SUPERADMINISTRADOR` queda reservado para cuentas `is_staff` e `is_superuser`.
- [x] Ocultar superadministradores del listado web de usuarios e impedir que se editen, desactiven o eliminen desde las vistas del sistema.
- [x] Recuperacion de contrasena por Gmail para usuarios internos activos con contrasena utilizable: administradores y encargados.
- [ ] Antes de subir a produccion, endurecer configuracion HTTPS: activar `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` y evaluar `SECURE_HSTS_SECONDS` despues de confirmar que todo el sitio opera solo por HTTPS.
- [ ] Antes de subir a produccion, activar `Force HTTPS` en PythonAnywhere para que `http://alejandrossm.pythonanywhere.com/` redirija a `https://alejandrossm.pythonanywhere.com/`.
- [ ] Antes de subir a produccion, agregar proteccion contra fuerza bruta en login, por ejemplo `django-axes` o rate limiting equivalente.
- [ ] Antes de subir a produccion, bloquear los comandos demo que crean usuarios con passwords predecibles, especialmente `crear_usuarios_prueba`.
- [ ] Antes de subir a produccion, validar globalmente que ningun `username` coincida con el `email` de cualquier cuenta, y que ningun `email` coincida con el `username` de otra cuenta, para evitar ambiguedades en el login por usuario o correo.

## Socios

- [x] Usar el correo electronico registrado como usuario tecnico del socio.
- [x] Editar socios exclusivamente mediante un formulario especifico de socio.
- [x] Impedir cambios de perfil en socios: un socio siempre debe conservar el rol `SOCIO`.
- [x] Mostrar en la vista de socios el total de reuniones, total de asistencias y total de ausencias.
- [x] Agregar indicador visual por socio:
  - Verde: sin ausencias.
  - Amarillo: una inasistencia.
  - Rojo: bloqueado por dos inasistencias.
- [x] Agregar un campo de telefono movil a usuarios y socios para registrar un numero de contacto operativo.
- [x] Definido: los socios consultaran sus asistencias por RUT en una vista publica futura, sin contrasena propia.
- [x] Ajustar el alta de socios para no solicitar contrasena inicial y crear la cuenta tecnica sin password utilizable.
- [x] Implementar bloqueo operativo de socios por inasistencias: un socio con 2 o mas ausencias no puede registrar nuevas asistencias.
- [x] Agregar flujo de justificacion administrativa de inasistencias de socios bloqueados, con motivo obligatorio, usuario responsable y fecha.
- [x] Mostrar la causa de las justificaciones de inasistencia en una vista operativa o historica, para que el administrador pueda revisar el motivo registrado.
- [x] Revisar que un socio bloqueado no contabilice nuevas asistencias como ausente.
- [x] Sprint 3 HU-12: consulta publica por RUT para socios, mostrando estado del socio, historial de asistencia, resumen anual, reuniones totales, asistencias y ausencias.
- [x] Sprint 3 HU-12: calcular la proxima reunion automaticamente como servicio reutilizable; por ajuste de interfaz no se muestra en la vista publica.
- [x] Carga masiva de socios: agregar opcion en Configuracion bajo Registro de logs para recibir CSV del administrador, validar toda la planilla antes de persistir, crear socios solo si todos los datos son correctos, y mostrar en un modal con scroll los socios/filas con errores cuando la planilla no sea valida.

## Reportes

- [x] Sprint 3 HU-13: exportar resumen anual para administradores en `xlsx`, `csv` y `pdf`, con datos del socio, reuniones realizadas, asistencias, inasistencias, estado actual y ano seleccionado.
  - [x] Primera entrega: listados de asistencia y socios con botones de descarga `csv`, `xlsx` y `pdf`, filtro de ano/estado, datos completos y exportacion del conjunto filtrado completo.
- [x] Carga historica: permitir cargar asistencias de reuniones `HISTORICA` desde CSV separado por `;` o `,`, con plantilla base XLSX exportable y lectura registro por registro.

## Auditoria

- [x] Sprint 3 HU-14: registrar acciones relevantes en `auditoria.log` con usuario ejecutor, tipo de accion, fecha y hora, entidad afectada y cobertura para desactivacion/activacion de usuarios, cancelacion de reuniones, borrado de reuniones, borrado de usuarios/socios y respaldo de base de datos.

## Pendientes por definir

- [x] Modo seguro de eliminacion: solo se pueden eliminar socios sin asistencias contabilizadas; los encargados de registro solo se activan o desactivan.
- [x] Afinar regla de bloqueo operativo persistente de socios:
  - Mantener separados `Activo/Inactivo` y `Bloqueado`: `is_active` representa el estado administrativo del socio; `Bloqueado` es un estado operativo derivado de inasistencias no justificadas.
  - Un socio puede estar `Activo` y `Bloqueado` al mismo tiempo. En ese estado no puede registrar nuevas asistencias.
  - Si un socio queda bloqueado por inasistencias en un ano anterior, el cambio de ano no debe desbloquearlo automaticamente.
  - El desbloqueo solo ocurre cuando un administrador justifica las inasistencias necesarias para bajar bajo el umbral operativo.
  - El filtro por ano debe servir para reportes, indicadores y revision historica del periodo seleccionado, pero no debe borrar ni ocultar el bloqueo operativo vigente para registrar asistencia.
