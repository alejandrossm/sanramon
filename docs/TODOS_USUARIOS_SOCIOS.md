# TODOs usuarios y socios

Pendientes para una siguiente iteracion del modulo de usuarios, socios y asistencia.

## Pendientes inmediatos

- [ ] Completar la validacion manual del candidato `1.0.1`: autenticacion,
  recuperacion de contrasena, consulta con OTP, gestion de usuarios y socios,
  reuniones, asistencias, cargas, exportaciones y auditoria. Checklist detallado
  en `docs/RELEASE_1.0.1.md`.
- [ ] Validar el despliegue sobre una copia de la base de produccion, ejecutar
  `python manage.py verificar_identidades` y comprobar una restauracion desde un
  respaldo cifrado reciente.

## Despues de estabilizar el candidato

- [ ] Restablecer los limites definitivos de recuperacion de contrasena
  (ventana de 60 minutos, 3 solicitudes por identificador y 10 por IP) y
  ejecutar las pruebas asociadas.
- [ ] Revisar y cerrar formalmente las brechas organizativas y juridicas
  registradas en `docs/MEMORIA_CUMPLIMIENTO_LEY_21719.md`.

## Hotfix proxima version (`1.0.1`)

- [x] Corregir la separacion entre identidad interna y socio: usuarios internos
  sin RUT, RUT obligatorio solo para socios y correo unico por ambito,
  permitiendo que un socio y un usuario interno compartan el mismo correo.
  Diseno, migracion y criterios en
  `docs/CAMBIO_IDENTIDAD_USUARIOS_SOCIOS.md`.
- [x] Asegurar que un correo compartido no mezcle cuentas ni repita el problema
  anterior: la recuperacion de contrasena debe seleccionar exclusivamente al
  usuario interno activo con contrasena utilizable, mientras que la consulta
  publica y su codigo OTP deben operar sobre el socio localizado por RUT.
- [x] Normalizar a mayusculas los nombres y apellidos de todos los socios,
  incluyendo una migracion para los registros existentes y normalizacion en
  altas, ediciones y cargas masivas futuras.
  - [x] Datos de produccion normalizados el 2026-08-02: 549 socios revisados,
    469 modificados y 80 que ya se encontraban en mayusculas. Se genero
    previamente un respaldo cifrado desde la aplicacion.
  - [x] Aplicar la normalizacion automaticamente en nuevas altas, ediciones y
    cargas masivas.
- [ ] Ejecutar el hotfix primero sobre una copia de la base de produccion,
  comprobar duplicados de correo por ambito y verificar el respaldo y el plan
  de restauracion antes del despliegue.
- [x] Agregar pruebas de regresion para correos compartidos, recuperacion de
  contrasena, envio de OTP y normalizacion de nombres con tildes y letra `ñ`.
- [x] Evitar registros duplicados por doble clic: al enviar un formulario de
  alta, deshabilitar inmediatamente sus botones de envio, marcar el formulario
  con `aria-busy` y mostrar `Guardando...` hasta recibir la respuesta. Reutilizar
  de forma global el bloqueo existente en `static/js/reuniones.js`, con un
  timeout de recuperacion si la navegacion falla; no introducir una espera
  artificial antes de enviar la solicitud.
- [x] Reforzar en el servidor las operaciones de registro que no esten
  protegidas por restricciones de unicidad, mediante una clave de idempotencia
  o una restriccion de base de datos, para que dos solicitudes simultaneas,
  incluso desde usuarios o sesiones distintas, no creen registros duplicados
  aunque JavaScript este deshabilitado. Capturar el conflicto de integridad y
  mostrar un mensaje controlado en vez de responder con un error `500`.
- [x] Corregir la redireccion posterior a la reautenticacion: despues de
  confirmar correctamente la contrasena, no debe permanecer en la pagina de
  confirmacion. Debe redirigir a Configuracion o al destino seguro solicitado
  originalmente mediante `next`, con una prueba de regresion para ambos casos.
- [x] Evaluar e implementar para el registro de asistencia un unico campo
  visible que reciba indistintamente el RUT manual o la lectura completa del
  QR, eliminando el selector entre modo QR y modo manual. La pistola debe
  completar la lectura y enviar con `Enter` (automatico si esta configurado o
  presionado por el operador), sin usar el envio temporizado actual. Despues de
  cada intento, el campo debe quedar limpio y recuperar el foco.
  - [x] Detectar automaticamente el origen: un RUT aislado se registra como
    ingreso manual y una URL o carga con bloque `RUN` como lectura QR.
  - [x] Hacer tolerante la extraccion del RUN a las variaciones de teclado que
    alteran caracteres como `=`, `-`, `:`, `?` y `&`, validando siempre el
    digito verificador.
  - [ ] Probar el flujo con cedulas antiguas y nuevas, lectores configurados con
    teclado espanol e ingles, perdida y recuperacion del foco, sufijo `Enter` y
    lecturas incompletas.
  - [x] Conservar como caso de prueba anonimizado el formato observado en las
    cedulas nuevas, sin almacenar datos reales:
    `https://portal.sidiv.registrocivil.cl/docstatus?RUN={rut}&type=CEDULA&serial={numero_documento_alfanumerico}&mrz={cadena_mrz}&name={nombre_codificado}`.
    El formato puede incluir nombres con caracteres acentuados representados
    mediante secuencias `%XX`; la extraccion del RUN no debe depender del
    contenido, orden o codificacion de los parametros posteriores.

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
- [x] Endurecer configuracion HTTPS: `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` y `SECURE_HSTS_SECONDS` se configuran por entorno y fallan cerrado con `DEBUG=False`.
- [ ] Antes de subir a produccion, activar `Force HTTPS` en PythonAnywhere para que `http://alejandrossm.pythonanywhere.com/` redirija a `https://alejandrossm.pythonanywhere.com/`.
- [x] Agregar limitacion de intentos en login, recuperacion y reautenticacion.
  Durante las pruebas de correo, la recuperacion usa temporalmente una ventana
  de 1 minuto y limites de 100 solicitudes por identificador y por IP; ajustar
  los parametros antes de produccion definitiva.
- [x] Bloquear con `DEBUG=False` los comandos que crean usuarios o datos demo.
- [x] Validar `username` global y correo unico por ambito, sin distinguir
  mayusculas, permitiendo compartir correo entre una cuenta interna y un socio.

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
  - [x] Refuerzo 2026-06-29: el RUT solo inicia la solicitud; el acceso exige codigo temporal enviado al correo, aceptacion versionada y sesion limitada.
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
