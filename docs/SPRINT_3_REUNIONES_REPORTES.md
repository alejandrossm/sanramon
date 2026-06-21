# Sprint 3 - Consulta publica, reportes y auditoria

## Objetivo

Completar el alcance diferido desde Sprint 2 para exponer informacion publica a socios, preparar reportes exportables y registrar trazabilidad operativa de acciones relevantes.

## Preparacion tecnica

- [x] Revisar modelos actuales involucrados: `Usuario`, `Reunion`, `AsistenciaReunion`, `DesbloqueoSocio` y `NotificacionBloqueoSocio`.
- [x] Centralizar la logica de asistencia en `usuarios/servicios_asistencia.py` para reutilizarla en vistas publicas, reportes y vistas internas.
- [x] Crear resumen reutilizable por socio y por ano con reuniones, asistencias, ausencias, ausencias efectivas y justificaciones.
- [x] Crear historial reutilizable de asistencia por socio, filtrable por ano.
- [x] Calcular la proxima reunion automaticamente desde reuniones `PROGRAMADA`, usando fecha y hora mas cercana a la fecha actual.
- [x] Mantener las vistas existentes usando los nuevos servicios sin cambiar el comportamiento visible.
- [x] Cubrir la preparacion con pruebas automatizadas.
- [x] Habilitar carga historica de asistencia para reuniones `HISTORICA` mediante plantilla XLSX y CSV separado por `;` o `,`.

## Alcance propuesto

### HU-12 - Consulta de informacion

- Modulo: Consulta de informacion.
- Accion: Consultar asistencia.
- Actor: Socio.
- Historia: Como socio, quiero consultar mi informacion de asistencia.
- Beneficio: Conocer mi estado e historial.
- Prioridad: Media.
- Sprint: Sprint 3.
- Estado: Completada.

#### Criterios de aceptacion

- [x] La consulta requiere RUT.
- [x] Solo se muestra informacion si el RUT es valido.
- [x] El sistema muestra el estado del socio.
- [x] El sistema muestra historial de asistencia.
- [x] El sistema muestra resumen anual.
- [x] Si los datos no coinciden, se muestra un mensaje generico.

#### Notas de alcance

- La consulta debe estar disponible desde un landing page publico tipo `index`, con estructura visual similar a la referencia entregada por el cliente.
- El landing funciona como punto de inicio de navegacion del sistema, con informacion del proyecto, imagenes referenciales, menu superior y footer.
- El menu del landing incluye acceso al sistema interno y acceso de socios a la consulta publica por RUT.
- La vista de socios debe mostrar reuniones totales, asistencias y ausencias.
- El calculo de proxima reunion queda disponible como servicio reutilizable; por ajuste de interfaz no se muestra en la vista publica.
- Si se muestra historial, debe ser una vista acotada para el socio consultado por RUT; no corresponde a un reporte publico masivo.

#### Implementacion

- Ruta publica `home` (`/`) como landing del proyecto San Ramon, con navbar, secciones informativas, imagenes y footer con contacto/redes.
- Ruta publica `consulta_publica_asistencia` (`/consulta-asistencia/`) para consultar por RUT.
- Los usuarios autenticados que entran al index publico se redirigen al destino interno correspondiente.
- La consulta muestra estado del socio, totales generales, resumen anual e historial anual.

### HU-13 - Reportes

- Modulo: Reportes.
- Accion: Exportar resumen anual.
- Actor: Administrador.
- Historia: Como administrador, quiero exportar resumen anual de asistencia.
- Beneficio: Analizar participacion de socios.
- Prioridad: Media.
- Sprint: Sprint 3.
- Estado: Completada.

#### Criterios de aceptacion

- [x] El sistema genera archivo `xlsx`, `csv` y `pdf` desde el listado operativo de asistencia.
- [x] El reporte incluye datos completos del socio y reuniones realizadas.
- [x] El reporte incluye asistencias e inasistencias por socio.
- [x] El reporte incluye estado actual del socio.
- [x] El reporte corresponde al ano seleccionado.

#### Notas de alcance

- Definir filtros minimos antes de implementar. Base esperada: ano, estado del socio y estado de reunion si aplica.
- El reporte debe respetar las reglas vigentes de bloqueo y justificacion: ausencias justificadas no deben contarse como ausencias efectivas.

#### Implementacion

- El listado operativo de asistencia y el listado administrativo de socios permiten filtrar por ano de reporte y estado del socio.
- Los administradores pueden descargar el resumen anual filtrado en `csv`, `xlsx` y `pdf` desde ambos listados.
- Los archivos exportan el conjunto completo filtrado, no solo la pagina visible.
- Los reportes incluyen datos completos de usuario del socio, correo, telefono, estado, totales anuales e indicador.

### HU-14 - Auditoria

- Modulo: Auditoria.
- Accion: Registrar acciones del sistema.
- Actor: Sistema.
- Historia: Como sistema, quiero registrar acciones relevantes.
- Beneficio: Mantener trazabilidad.
- Prioridad: Alta.
- Sprint: Transversal.
- Estado: Completada.

#### Criterios de aceptacion

- [x] El sistema registra usuario que ejecuta la accion.
- [x] El sistema registra tipo de accion.
- [x] El sistema registra fecha y hora.
- [x] El sistema registra entidad afectada cuando corresponda.
- [x] Aplica a las acciones criticas definidas para esta entrega: desactivacion/activacion de usuarios, cancelacion de reuniones, borrado de reuniones, borrado de usuarios/socios y respaldo de base de datos.

#### Notas de alcance

- La auditoria se registra en `auditoria.log` como eventos JSON Lines para conservar usuario ejecutor, accion, fecha/hora, entidad afectada y detalle.
- No se duplican en este log los eventos que ya quedan trazados en vistas operativas, como registros de asistencia y justificaciones.

## Fuera del alcance de Sprint 3

- Seguridad de produccion: se realizara antes de subir a produccion, no como parte de este sprint funcional.
- Reportes publicos masivos: el acceso publico del socio debe limitarse a la informacion correspondiente al RUT consultado.
