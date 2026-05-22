# Sprint 3 - Reuniones, reportes y carga historica

## Objetivo

Completar el alcance diferido desde Sprint 2 para mejorar la planificacion de reuniones, exponer informacion publica y preparar reportes/carga historica.

## Alcance propuesto

1. HU-12 - Proxima reunion y landing publica
   - Permitir que un administrador configure varias reuniones futuras.
   - Marcar solo una reunion como `proxima reunion`.
   - Validar que exista como maximo una reunion marcada como proxima.
   - Usar la reunion destacada para mostrar informacion publica en el landing page solicitado por el cliente.

2. HU-13 - Reporte exportable de reuniones
   - Crear reporte exportable a Excel con todas las reuniones.
   - Incluir datos base de reunion, estado y responsables operativos cuando correspondan.
   - Definir filtros minimos antes de implementar: periodo, estado y locacion.

3. HU-14 - Carga historica de asistencias
   - Soportar reuniones en estado `historica` para registrar asistencias posteriores mediante carga masiva CSV u otro mecanismo operativo.
   - Definir permisos y flujo para carga historica.
   - Validar si el registro historico podra ser realizado por administrador, socio o ambos.
   - Mantener trazabilidad del usuario que carga la informacion historica.

## Fuera del alcance de Sprint 3

- Seguridad de produccion: se realizara antes de subir a produccion, no como parte de este sprint funcional.
- Activacion publica de cuentas de socios: los socios podran recuperar contrasena, pero no activar su cuenta por autoservicio.
