# Memoria del proyecto

Archivo para registrar detalles importantes que conviene conservar entre sesiones de trabajo.

## Contexto general

- Proyecto ubicado en `c:\Develop\app_asistencia\entorno\sanramon`.
- Aplicacion de asistencia con estructura Django: `manage.py`, `config`, `usuarios`, `templates` y `static`.

## Decisiones importantes

- En adelante, usar solo elementos y utilidades de Bootstrap 5 siempre que sea posible.
- Evitar al maximo CSS personalizado cuando Bootstrap 5 ya pueda construir el mismo resultado.
- En tablas, las columnas de acciones deben usar botones de solo icono para mantener alineacion estable.
- En tablas, los encabezados de columnas de datos deben ir en mayusculas; encabezados operativos como `Acciones` y `Eliminar` se mantienen capitalizados.
- Los botones de solo icono deben incluir `title` y `aria-label` descriptivos; usar `title` para mostrar ayuda al pasar el mouse.
- Cuando exista un toggle junto a texto, preferir que el texto descriptivo quede antes del switch si asi se definio en la vista.
- Los botones de estado deben comunicar visualmente el estado actual: encendido para activos y apagado para inactivos.
- En columnas de eliminacion controladas por switch, mostrar los iconos muted cuando la eliminacion este desactivada; al activarla, usar danger para los eliminables y outline para los no eliminables.
- La carpeta `usuarios/management/` contiene comandos auxiliares de desarrollo/pruebas y no es necesaria para el funcionamiento normal en produccion.

## Pendientes

- 

## Vista usuarios

- Usar Bootstrap 5 para construir layout y controles; evitar CSS personalizado si Bootstrap resuelve el caso.
- Header: titulo y descripcion a la izquierda; a la derecha van `Registrar usuario` y `Activar eliminacion`, en ese orden.
- `Activar eliminacion` debe ser un switch Bootstrap (`form-switch`), con texto antes del toggle.
- Filtros bajo el header: `RUT`, `Nombre` y `Apellido`.
- La tabla separa `Nombre` y `Apellido` en columnas distintas para mejorar usabilidad y lectura.
- En pantallas pequeñas, no usar tabla horizontal para usuarios; mostrar una lista tipo `list-group` por usuario con datos apilados y acciones visibles.
- Mantener la tabla tradicional solo desde breakpoint `md` hacia arriba.
- La vista pagina usuarios internos en bloques de 50 items por pagina.
- La paginacion debe conservar filtros y ordenamiento activos.
- Columnas de datos en mayusculas: `USUARIO`, `NOMBRE`, `APELLIDO`, `RUT`, `EMAIL`, `ROL`, `ESTADO`.
- Columnas operativas capitalizadas: `Acciones` y `Eliminar`.
- Encabezados de columnas de datos tienen ordenamiento por columna con una flecha direccional sutil: arriba para ascendente, abajo para descendente; al hacer click alterna direccion.
- Acciones de fila deben usar solo iconos para mantener alineacion estable.
- Botones de solo icono deben incluir `title` y `aria-label`.
- Boton de estado: activo se ve encendido (`btn-success`) e inactivo apagado (`btn-outline-secondary`).
- Botones de eliminar: cuando eliminacion esta desactivada, se ven muted; al activar el switch, los eliminables pasan a danger y los no eliminables permanecen outline.

## Notas cronologicas

### 2026-05-03

- Se creo este archivo para centralizar contexto, decisiones, pendientes y notas relevantes.
- El listado de usuarios internos usa paginacion de 50 items por pagina.
- El listado de usuarios internos filtra por RUT, nombre y apellido; en la tabla, nombre y apellido se muestran en columnas separadas.
- La tabla de usuarios internos permite ordenar columnas con botones ascendente/descendente en los encabezados, conservando filtros y paginacion.
- Para cargar datos de prueba de paginacion, usar `python manage.py cargar_encargados_paginacion`. Crea/actualiza 100 encargados por defecto con operaciones bulk, sin ejecutar `save()`, `full_clean()` ni hashing de contrasenas.
