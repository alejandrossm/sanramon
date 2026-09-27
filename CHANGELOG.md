# Registro de cambios

Los cambios relevantes del proyecto se documentan en este archivo.

## [1.0.1] - Sin publicar

### Correcciones

- Separacion de identidad entre usuarios internos y socios: RUT exclusivo para
  socios y correo unico dentro de cada ambito.
- Recuperacion de contrasena y autenticacion seguras cuando un usuario interno
  comparte correo con un socio.
- Normalizacion Unicode a mayusculas de nombres y apellidos de socios.
- Campo unico para registrar asistencia mediante RUT o lectura QR completa, con
  envio explicito mediante `Enter`.
- Redireccion segura despues de la reautenticacion.
- Prevencion de envios duplicados en altas y control de conflictos concurrentes
  en el servidor.

### Pruebas

- Regresiones para correos compartidos, OTP, recuperacion, nombres con tildes y
  `ñ`, variantes de lectores QR, reautenticacion e idempotencia.

## [1.0.0] - Sin publicar

### Funcionalidad

- Gestion de usuarios internos y socios con roles y permisos separados.
- Programacion, activacion, finalizacion y cancelacion de reuniones.
- Registro manual y por lectura de RUT para la asistencia.
- Bloqueo operativo por inasistencias y justificaciones trazables.
- Carga masiva de socios y carga historica de asistencias.
- Reportes anuales en CSV, XLSX y PDF.
- Consulta publica protegida por codigo temporal enviado por correo.
- Recuperacion de contrasena para usuarios internos.

### Seguridad y operacion

- Limitacion de intentos de login, recuperacion y reautenticacion. La
  recuperacion queda temporalmente configurada con una ventana de un minuto y
  limites de cien solicitudes para pruebas funcionales.
- Separacion entre administradores web y superadministradores Django.
- Cookies seguras, redireccion HTTPS y HSTS configurables por entorno.
- Auditoria con verificacion de integridad y respaldos cifrados.
- Actualizacion a Django 6.0.7 para incorporar tres correcciones de seguridad
  publicadas para la rama 6.0.
- Bloqueo de comandos de datos demo cuando `DEBUG=False`.
- Prevencion global de colisiones entre nombres de usuario y correos.
- CI sobre Python 3.13 con pruebas, migraciones, comprobaciones de despliegue
  y auditoria de dependencias.
- Paquete ZIP reproducible con una lista cerrada de archivos requeridos en
  produccion, sin pruebas, documentacion ni herramientas internas.

### Compatibilidad

- Python 3.13.
- Django 6.0.7.
