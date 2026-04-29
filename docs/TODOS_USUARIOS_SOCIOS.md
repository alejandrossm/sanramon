# TODOs usuarios y socios

Pendientes para una siguiente iteracion del modulo de usuarios, socios y asistencia.

## Interfaz

- [x] Implementar SweetAlert para reemplazar o complementar mensajes de confirmacion, exito y error.
- [x] Aplicar formateo visual del RUT en el formulario, del lado del cliente, para mejorar la lectura mientras se escribe.

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
