# Registro de cambios

Los cambios relevantes del proyecto se documentan en este archivo.

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

- Limitacion de intentos de login, recuperacion y reautenticacion.
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
