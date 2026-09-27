# Cambio futuro: identidad separada para usuarios internos y socios

## Estado

Implementado en la rama del hotfix `1.0.1`. La migracion y las pruebas deben
validarse antes de desplegarlo en produccion.

Rama sugerida:

```text
hotfix/1.0.1
```

## Motivo

El cliente confirmó que una misma persona puede actuar como usuario interno
(`ADMINISTRADOR` o `ENCARGADO_REGISTRO`) y también participar como `SOCIO`.
Para el negocio no es necesario relacionar ambas representaciones ni demostrar
que corresponden a la misma persona.

El usuario interno representa a quien opera el sistema y queda identificado en
la auditoría por su nombre de usuario. El socio representa a quien registra
asistencia y consulta su historial, y queda identificado mediante su RUT.

## Decisión

Se mantendrán dos registros independientes cuando una persona cumpla ambas
funciones:

```text
Usuario interno
  username: jperez
  rol: ENCARGADO_REGISTRO
  rut: NULL
  email: juan@example.com
  password: utilizable

Socio
  username técnico: juan@example.com
  rol: SOCIO
  rut: 12345678-5
  email: juan@example.com
  password: no utilizable
```

No se agregará una relación entre estos registros, un indicador `es_socio` ni
un sistema de roles múltiples.

Cuando `jperez` registre una asistencia, la auditoría identificará a `jperez`
como actor y la asistencia quedará asociada al registro independiente de socio
encontrado por RUT.

## Reglas funcionales

### Nombre de usuario

- El nombre de usuario seguirá siendo obligatorio y único globalmente.
- Los usuarios internos iniciarán sesión con su nombre de usuario.
- Los socios conservarán el nombre de usuario técnico generado por el flujo de
  alta vigente y no tendrán una contraseña utilizable.
- El nombre de usuario de una cuenta existente continuará siendo inmutable.

### RUT

- El RUT será obligatorio, válido y único para cuentas con rol `SOCIO`.
- El RUT no se solicitará a `ADMINISTRADOR`, `ENCARGADO_REGISTRO` ni
  `SUPERADMINISTRADOR`.
- Las cuentas internas almacenarán `NULL`, no una cadena vacía, en el campo
  RUT.
- La unicidad se aplicará a los RUT informados. Varias cuentas internas podrán
  tener `rut=NULL`.
- Los flujos de asistencia, consulta pública, cargas y reportes seguirán
  operando exclusivamente sobre registros con rol `SOCIO`.

### Correo electrónico

- El correo seguirá siendo obligatorio para socios y usuarios internos.
- El correo será único, sin distinguir mayúsculas, dentro del ámbito de socios.
- El correo será único, sin distinguir mayúsculas, dentro del ámbito de
  usuarios internos.
- Se permitirá que un registro `SOCIO` y un registro interno compartan el mismo
  correo.
- `ADMINISTRADOR`, `ENCARGADO_REGISTRO` y `SUPERADMINISTRADOR` forman un único
  ámbito interno. Por lo tanto, no podrán compartir correo entre ellos.
- Dos socios tampoco podrán compartir correo.
- Los correos se continuarán normalizando a minúsculas antes de persistirlos.

La combinación permitida es:

| Cuenta A | Cuenta B | Mismo correo |
| --- | --- | --- |
| Socio | Encargado | Sí |
| Socio | Administrador | Sí |
| Socio | Superadministrador | Sí |
| Socio | Socio | No |
| Encargado | Encargado | No |
| Encargado | Administrador | No |
| Administrador | Superadministrador | No |

### Recuperación y consulta

- La recuperación de contraseña buscará únicamente usuarios internos activos
  con contraseña utilizable.
- Un socio con el mismo correo no deberá recibir ni habilitar recuperación de
  contraseña.
- La consulta pública seguirá buscando primero al socio por RUT y enviará el
  código temporal al correo de ese registro `SOCIO`.
- Compartir el correo no mezclará permisos, sesiones, asistencias ni estados de
  ambas cuentas.

## Alcance técnico previsto

### Modelo `Usuario`

1. Cambiar `rut` para aceptar `null=True` y `blank=True`, conservando la
   unicidad de los valores informados.
2. Retirar `rut` de `REQUIRED_FIELDS`.
3. Agregar validación condicional que rechace un socio sin RUT.
4. Evitar que la normalización transforme `None` en `''`.
5. Retirar la unicidad global de `email`.
6. Incorporar unicidad de correo por ámbito:
   - una restricción para `rol='SOCIO'`;
   - una restricción para `rol!='SOCIO'`.
7. Mantener una validación equivalente en el modelo y los formularios para
   entregar mensajes comprensibles antes de llegar a la base de datos.
8. Ajustar la regla que actualmente impide que el `username` o el `email`
   coincidan con identificadores de cualquier otra cuenta. Debe permitirse el
   caso específico en que el correo interno coincide con el correo y nombre de
   usuario técnico del socio.

Las restricciones condicionales deberán verificarse contra el motor utilizado
en producción antes de elegir su implementación definitiva. Si el motor no
soporta índices únicos parciales, la validación por ámbito deberá reforzarse con
una estrategia compatible que también proteja escrituras concurrentes.

### Formularios y administración

- Quitar el campo RUT del alta y edición de usuarios internos.
- Mantener el RUT obligatorio en el alta, edición y carga masiva de socios.
- Validar el correo contra cuentas del mismo ámbito y excluir la instancia
  actual durante una edición.
- Ajustar el alta y edición del admin de Django para que las cuentas internas no
  requieran RUT.
- Mantener separados el formulario de usuarios internos y el formulario de
  socios.

### Listado de usuarios

- Retirar el filtro, columna y detalle de RUT del listado de usuarios internos.
- Mantener RUT en listados, filtros, detalles y reportes de socios.
- No mostrar ninguna indicación que intente vincular un usuario interno con un
  socio que tenga el mismo correo.

### Migración de datos

La migración deberá ejecutarse en este orden lógico:

1. Revisar duplicados de correo existentes, normalizados a minúsculas.
2. Modificar el esquema para permitir RUT nulo.
3. Convertir a `NULL` el RUT de las cuentas internas:
   `ADMINISTRADOR`, `ENCARGADO_REGISTRO` y `SUPERADMINISTRADOR`.
4. Retirar la unicidad global del correo.
5. Crear las restricciones de unicidad por ámbito.
6. Verificar que todos los socios conservan RUT válido y que no existen RUT
   duplicados.
7. Verificar que todas las cuentas internas activas destinadas a recuperación
   mantienen correo y contraseña utilizable.

Antes de limpiar los RUT internos deberá generarse un respaldo recuperable. La
eliminación de esos valores es intencional y responde a minimización de datos.

Los RUT de cuentas internas existentes no necesitan trasladarse a un socio. Si
la persona también participa como socio, su registro de socio se administrará
independientemente mediante el flujo habitual.

## Pruebas requeridas

### Modelo y restricciones

- Crear varios usuarios internos con `rut=None`.
- Rechazar un socio sin RUT.
- Rechazar RUT inválido o repetido entre socios.
- Permitir el mismo correo para un socio y un usuario interno.
- Rechazar el mismo correo entre dos socios.
- Rechazar el mismo correo entre dos usuarios internos, aunque tengan roles
  internos diferentes.
- Comprobar las reglas sin distinguir mayúsculas.
- Comprobar que las validaciones también se aplican fuera de los formularios.

### Formularios e interfaz

- Confirmar que el alta y edición de usuarios internos no muestran RUT.
- Confirmar que el alta y edición de socios sí exigen RUT.
- Confirmar que el listado interno no ofrece filtro ni columna RUT.
- Confirmar que los listados y reportes de socios conservan el RUT.

### Autenticación y recuperación

- Iniciar sesión con la cuenta interna cuando comparte correo con un socio.
- Recuperar la contraseña de la cuenta interna usando el correo compartido.
- Confirmar que la cuenta de socio, al no tener contraseña utilizable, no entra
  al flujo de recuperación.
- Confirmar que el código de consulta pública llega al correo del socio.

### Asistencia y auditoría

- Registrar asistencia con un encargado que comparte correo con el socio
  asistente.
- Confirmar que la asistencia se asocia al socio localizado por RUT.
- Confirmar que la auditoría conserva como actor el `username` del encargado.
- Confirmar que no se crea una relación implícita entre ambos registros.

## Criterios de aceptación

- Se puede crear un administrador o encargado sin RUT.
- Se pueden crear múltiples usuarios internos sin RUT.
- No se puede crear ni conservar un socio sin RUT válido.
- Un socio y un usuario interno pueden compartir correo.
- No se puede repetir el correo dentro del mismo ámbito.
- La recuperación de contraseña opera únicamente sobre la cuenta interna.
- La consulta pública y la asistencia continúan operando sobre la cuenta de
  socio.
- Los permisos y estados de una cuenta no afectan a la otra.
- No se incorpora una relación entre ambas cuentas.
- Las pruebas existentes de socios, asistencias, reportes y consulta pública
  continúan aprobando.

## Fuera de alcance

- Unificar las dos cuentas.
- Detectar automáticamente que ambas representan a la misma persona.
- Mostrar al administrador posibles coincidencias por nombre o correo.
- Permitir múltiples roles en una misma cuenta.
- Trasladar asistencias entre registros.
- Usar el RUT como credencial de un usuario interno.
