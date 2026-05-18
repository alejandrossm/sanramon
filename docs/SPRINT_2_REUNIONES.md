# Sprint 2 - Reuniones y asistencia

## Rama base

- Rama base del modulo: `feature/reuniones-sprint-2`.
- Cada historia de usuario se trabaja en una rama hija desde la rama base.
- Al completar una HU: implementar, testear, revisar diff, integrar a la rama base y continuar con la siguiente.

## Estrategia de ramas por HU

- `feature/hu-04-crear-reunion`
- `feature/hu-05-iniciar-reunion`
- `feature/hu-08-asistencia-qr`
- `feature/hu-09-asistencia-manual`
- `feature/hu-06-finalizar-reunion`
- `feature/hu-07-cancelar-reunion`
- `feature/hu-10-bloqueo-automatico`
- `feature/hu-11-desbloquear-socio`
- `feature/hu-03-socio-inactivo-sin-asistencia`

## Orden de ejecucion propuesto

1. HU-04 - Crear reunion
   - Base funcional del modulo.
   - Crea el modelo de reunion, formulario, listado y alta.
   - La hora de reunion es obligatoria.
   - La locacion de reunion es obligatoria.
   - El formulario permite crear reuniones en estado `programada` o `historica`.
   - Las reuniones historicas no se pueden iniciar ni finalizar.
   - Las reuniones historicas solo se pueden eliminar si no tienen datos registrados.
   - La fecha de reunion es obligatoria.
   - Solo administrador puede crear reuniones.

2. HU-05 - Iniciar reunion
   - Permite habilitar el registro de asistencia.
   - Solo puede existir una reunion `activa` a la vez.
   - El sistema bloquea el inicio si ya existe otra reunion activa.
   - La reunion cambia a estado `activa`.

3. HU-08 - Registrar asistencia por RUT y QR
   - Primero se implementara el registro ingresando el RUT en un input.
   - La vista dejara preparado el acceso al scanner QR para implementacion posterior.
   - El registro por RUT debe registrar la asistencia correctamente.
   - Requiere una reunion activa.
   - Valida que el socio exista.
   - Valida que el socio este activo.
   - Valida que el socio no este bloqueado.
   - No permite asistencia duplicada en la misma reunion.
   - Muestra confirmacion al registrar.

4. HU-09 - Registrar asistencia manual
   - Usa las mismas validaciones del registro por RUT y QR.
   - Permite registrar asistencia ingresando RUT.
   - El registro manual debe estar siempre disponible mientras exista una reunion activa.
   - Muestra mensaje de exito o error.

5. HU-06 - Finalizar reunion
   - Solo una reunion activa puede finalizarse.
   - Marca ausentes automaticamente a socios activos que no registraron asistencia.
   - Calcula inasistencias del ano.
   - Deja preparado el punto de bloqueo automatico.

6. HU-07 - Cancelar reunion
   - El motivo de cancelacion es obligatorio.
   - La cancelacion queda registrada con usuario, fecha y motivo.
   - Las asistencias de la reunion cancelada se eliminan o invalidan.
   - Una reunion cancelada no genera inasistencias.

7. HU-10 - Bloqueo automatico
   - Se evalua al finalizar una reunion.
   - El conteo de inasistencias es anual.
   - El socio se bloquea automaticamente al llegar a 2 inasistencias anuales.
   - Un socio bloqueado no puede registrar asistencia.

8. HU-11 - Desbloquear socio
   - Solo administrador puede desbloquear socios.
   - El motivo de desbloqueo es obligatorio.
   - El desbloqueo queda registrado con usuario, fecha y motivo.
   - El socio queda habilitado para registrar asistencia si esta activo.

9. HU-03 - Complemento sprint 2 de socio inactivo
   - El socio inactivo no puede registrar asistencia.
   - La informacion historica del socio se conserva.
   - Se valida principalmente dentro de HU-08 y HU-09.

## Modelo de dominio propuesto

### Reunion

- `fecha`
- `hora`
- `locacion`
- `creador`
- `estado`: programada, activa, finalizada, cancelada, historica
- `es_proxima`
- `fecha_creacion`
- `activada_por`
- `fecha_activacion`
- `finalizada_por`
- `fecha_finalizacion`
- `cancelada_por`
- `fecha_cancelacion`
- `motivo_cancelacion`

### AsistenciaReunion

- `reunion`
- `socio`
- `estado`: presente, ausente
- `origen`: qr, manual, automatico
- `registrada_por`
- `fecha_registro`
- Restriccion unica: una asistencia por socio y reunion.

### BloqueoSocio

- `socio`
- `activo`
- `motivo`
- `creado_por`
- `fecha_creacion`
- `levantado_por`
- `fecha_levantamiento`
- `motivo_levantamiento`

## Pruebas por cada HU

- Ejecutar tests unitarios y de vistas de la HU.
- Ejecutar `python manage.py check`.
- Ejecutar `python manage.py makemigrations --check --dry-run` despues de crear migraciones.
- Ejecutar suite completa cuando la HU toque modelos compartidos o reglas de negocio.

## Criterio de avance

- No empezar una HU nueva si la anterior no esta implementada y testeada.
- No mezclar cambios de varias HU en la misma rama hija.
- Mantener actualizados los contadores existentes de asistencia en socios.
- Integrar cada HU a `feature/reuniones-sprint-2` antes de abrir la siguiente.

## Pendientes futuros

- Permitir que un administrador configure varias reuniones futuras, marcando solo una como `proxima reunion`.
- Validar que exista como maximo una reunion marcada como proxima.
- Usar esa reunion destacada para mostrar informacion publica en el landing page solicitado por el cliente.
- Mantener este punto fuera del alcance inicial de Sprint 2, salvo que se planifique como HU adicional.
- Permitir que el administrador elimine reuniones siempre que no tengan asistencias registradas.
- Las reuniones historicas tambien pueden eliminarse por administrador bajo la misma regla: solo si no tienen asistencias registradas.
- Soportar reuniones en estado `historica` para registrar asistencias posteriores mediante carga masiva CSV u otro mecanismo operativo.
- Definir permisos y flujo para carga historica: administrador o socio podran registrar asistencia historica mediante CSV u otro mecanismo validado.
