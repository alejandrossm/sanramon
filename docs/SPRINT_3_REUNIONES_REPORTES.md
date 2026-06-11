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

## Alcance propuesto

### HU-12 - Consulta de informacion

- Modulo: Consulta de informacion.
- Accion: Consultar asistencia.
- Actor: Socio.
- Historia: Como socio, quiero consultar mi informacion de asistencia.
- Beneficio: Conocer mi estado e historial.
- Prioridad: Media.
- Sprint: Sprint 3.
- Estado: Pendiente.

#### Criterios de aceptacion

- [ ] La consulta requiere RUT.
- [ ] Solo se muestra informacion si el RUT es valido.
- [ ] El sistema muestra el estado del socio.
- [ ] El sistema muestra historial de asistencia.
- [ ] El sistema muestra resumen anual.
- [ ] Si los datos no coinciden, se muestra un mensaje generico.

#### Notas de alcance

- La consulta debe estar disponible desde un landing page publico tipo `index`, con estructura visual similar a la referencia entregada por el cliente.
- El landing debe redirigir a administradores y encargados al sistema interno de asistencia.
- El landing debe redirigir a socios a la consulta publica por RUT.
- La vista de socios debe mostrar reuniones totales, asistencias y ausencias.
- La vista de socios debe incluir un recordatorio de la proxima reunion.
- La proxima reunion no se marca manualmente: se asume la reunion en estado `programada` con fecha y hora mas cercana a la fecha actual.
- Si se muestra historial, debe ser una vista acotada para el socio consultado por RUT; no corresponde a un reporte publico masivo.

### HU-13 - Reportes

- Modulo: Reportes.
- Accion: Exportar resumen anual.
- Actor: Administrador.
- Historia: Como administrador, quiero exportar resumen anual de asistencia.
- Beneficio: Analizar participacion de socios.
- Prioridad: Media.
- Sprint: Sprint 3.
- Estado: Pendiente.

#### Criterios de aceptacion

- [ ] El sistema genera archivo `xlsx`, `csv` y `pdf`.
- [ ] El reporte incluye datos completos del socio y reuniones realizadas.
- [ ] El reporte incluye asistencias e inasistencias por socio.
- [ ] El reporte incluye estado actual del socio.
- [ ] El reporte corresponde al ano seleccionado.

#### Notas de alcance

- Definir filtros minimos antes de implementar. Base esperada: ano, estado del socio y estado de reunion si aplica.
- El reporte debe respetar las reglas vigentes de bloqueo y justificacion: ausencias justificadas no deben contarse como ausencias efectivas.

### HU-14 - Auditoria

- Modulo: Auditoria.
- Accion: Registrar acciones del sistema.
- Actor: Sistema.
- Historia: Como sistema, quiero registrar acciones relevantes.
- Beneficio: Mantener trazabilidad.
- Prioridad: Alta.
- Sprint: Transversal.
- Estado: Pendiente.

#### Criterios de aceptacion

- [ ] El sistema registra usuario que ejecuta la accion.
- [ ] El sistema registra tipo de accion.
- [ ] El sistema registra fecha y hora.
- [ ] El sistema registra entidad afectada cuando corresponda.
- [ ] Aplica a acciones criticas como asistencia, cancelacion, desbloqueo y edicion.

#### Notas de alcance

- La auditoria debe disenarse como capacidad transversal para flujos actuales y futuros.
- Definir si se implementara como modelo propio de eventos, integracion con senales de Django o registros explicitos por caso de uso.

## Fuera del alcance de Sprint 3

- Seguridad de produccion: se realizara antes de subir a produccion, no como parte de este sprint funcional.
- Reportes publicos masivos: el acceso publico del socio debe limitarse a la informacion correspondiente al RUT consultado.
