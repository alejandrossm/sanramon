# Memoria de cumplimiento de la Ley N° 21.719

## 1. Control del documento

- Sistema: Sistema de asistencia del Proyecto Valle San Ramón.
- Documento: memoria técnica y organizativa de protección de datos personales.
- Versión inicial: 2026-06-29.
- Rama de implementación: `feature/seguridad-proteccion-datos`.
- Responsable de actualización técnica: equipo mantenedor del sistema.
- Estado: implementación parcial; no constituye certificación de cumplimiento.

Esta memoria debe actualizarse con cada cambio de finalidades, datos, proveedores,
controles, política de privacidad o versión del sistema.

## 2. Marco normativo considerado

La Ley N° 21.719 fue publicada el 13 de diciembre de 2024 y entra en vigor el
1 de diciembre de 2026. Modifica la Ley N° 19.628, regula el tratamiento de
datos personales y crea la Agencia de Protección de Datos Personales.

Fuentes oficiales:

- Ley N° 21.719:
  <https://www.bcn.cl/leychile/navegar?idNorma=1209272>
- Texto de la Ley N° 19.628 con vigencia diferida:
  <https://www.bcn.cl/leychile/navegar?idNorma=141599&idVersion=2026-12-01>
- Balance legislativo:
  <https://www.bcn.cl/balance-legislativo/detalle/ficha_LEY_21719_2024-12-13>

Principios considerados: licitud y lealtad, finalidad, proporcionalidad,
calidad, responsabilidad y seguridad. También se consideran los deberes de
información, confidencialidad, protección desde el diseño, seguridad y reporte
de vulneraciones.

## 3. Alcance del tratamiento

### 3.1 Titulares

- Socios del proyecto.
- Usuarios internos: administradores y encargados de registro.
- Personas que solicitan acceso a la consulta pública, exista o no coincidencia.

### 3.2 Categorías de datos

- Identificación: nombre, apellidos, RUT y nombre de usuario.
- Contacto: correo electrónico y teléfono móvil.
- Relación con el proyecto: rol, estado y fecha de ingreso.
- Asistencia: reuniones, presencia, ausencia, origen y fecha del registro.
- Justificaciones: motivo administrativo y responsable de la gestión.
- Notificaciones: correo de destino, fecha y estado informado.
- Seguridad: contraseñas cifradas, identificador de sesión, huellas HMAC de IP,
  códigos OTP en forma de HMAC, intentos y vencimientos.
- Auditoría: acción, fecha, actor, entidad afectada y detalle.

Los motivos de justificación son texto libre y podrían contener datos sensibles.
Debe instruirse a los operadores para no registrar diagnósticos médicos,
creencias u otros detalles que no sean estrictamente necesarios.

### 3.3 Operaciones principales

- Alta, modificación, desactivación y eliminación limitada de socios.
- Programación de reuniones y registro de asistencia.
- Carga histórica o masiva mediante archivos.
- Cálculo de indicadores y bloqueo por inasistencias.
- Notificación por correo.
- Consulta individual protegida.
- Exportación de reportes y respaldo de la base de datos.
- Registro de eventos de auditoría.

## 4. Decisión de diseño de la consulta individual

### 4.1 Riesgo anterior

La consulta original entregaba nombre, RUT, estado e historial utilizando el RUT
como único dato de entrada. El RUT es un identificador, no una credencial, por lo
que el flujo permitía acceso no autorizado a información personal.

### 4.2 Flujo implementado

1. La persona ingresa RUT y año.
2. La respuesta no confirma si el RUT existe o corresponde a un socio.
3. Si existe coincidencia, se envía un código de seis dígitos al correo registrado.
4. El código vence en 10 minutos, admite cinco intentos y tiene uso único.
5. La verificación crea una autorización de sesión de 15 minutos.
6. Si no existe aceptación para la versión vigente, se presenta el aviso.
7. La aceptación registra socio, versión, huella del texto, fecha, método de
   verificación y una huella HMAC de la IP.
8. Solo entonces se muestra el historial.

La aceptación del aviso no sustituye la verificación de identidad. El control
de acceso se basa en el código enviado al correo.

### 4.3 Controles técnicos

- Código generado con `secrets`.
- El código nunca se almacena ni se incluye en una URL.
- HMAC SHA-256 asociado al UUID de la solicitud.
- Comparación en tiempo constante.
- Cinco intentos por solicitud.
- Tres envíos por socio en una ventana de 15 minutos.
- Diez solicitudes por IP en una ventana de 15 minutos.
- Solicitudes indistinguibles para RUT sin coincidencia o limitados.
- Invalidación de códigos anteriores al emitir uno nuevo.
- Formularios POST con protección CSRF.
- Páginas protegidas con `Cache-Control: no-store`.
- Renovación del identificador de sesión después de verificar.
- Auditoría sin registrar RUT, correo, IP legible ni código.

### 4.4 Accesibilidad

El correo es el primer mecanismo implementado. Para personas sin acceso a correo
debe mantenerse atención asistida. Está pendiente implementar un PIN entregado
presencialmente, con verificación de cédula, límites de intentos y procedimiento
de reposición.

## 5. Evidencias implementadas

| Control | Evidencia |
|---|---|
| Solicitud y OTP | Modelo `SolicitudCodigoConsulta` |
| Aceptación versionada | Modelo `AceptacionPrivacidadConsulta` |
| Lógica criptográfica y límites | `usuarios/privacidad.py` |
| Formularios | `ConsultaPublicaRutForm`, `CodigoConsultaAsistenciaForm` y `AceptacionPrivacidadConsultaForm` |
| Rutas protegidas | vistas de solicitud, verificación, aceptación y resultado |
| Política pública | `/politica-privacidad/` |
| Auditoría | acciones `CONSULTA_PUBLICA_VERIFICADA`, `PRIVACIDAD_CONSULTA_ACEPTADA` y `CONSULTA_PUBLICA_ACCEDIDA` |
| Retención OTP | purga oportunista diaria en `usuarios/privacidad.py` |
| Pruebas | casos de no enumeración, expiración, uso único, intentos, límite de envío y aceptación |

## 6. Conservación

Matriz operativa inicial:

| Registro | Plazo inicial | Acción |
|---|---:|---|
| Solicitudes y códigos OTP | 30 días | Purga oportunista al recibir una nueva solicitud |
| Sesión de consulta | 15 minutos | Expiración automática |
| Aceptación del aviso | Mientras exista la relación y la necesidad de acreditar la aceptación | Revisar al terminar la relación |
| Auditoría | Pendiente de aprobación | Definir rotación, integridad y eliminación |
| Asistencia y justificaciones | Pendiente de aprobación jurídica/operativa | Eliminar o anonimizar al vencer la finalidad |
| Respaldos | Pendiente de aprobación | Definir ciclo, cifrado y destrucción |
| Reportes descargados | Fuera del control técnico una vez descargados | Definir procedimiento y responsabilidad del receptor |

La purga se intenta como máximo una vez al día por proceso cuando se recibe una
nueva solicitud OTP. Si no existen nuevas consultas, no se generan nuevos
registros y la limpieza pendiente se realizará con la siguiente solicitud.
Cambiar el plazo exige actualizar esta memoria, la política pública y la
configuración operacional correspondiente.

## 7. Derechos de los titulares

La política informa los derechos de acceso, rectificación, supresión, oposición,
portabilidad y bloqueo. La Ley N° 21.719 establece, como regla general, respuesta
dentro de 30 días corridos, prorrogable una vez, y dos días hábiles para resolver
una solicitud de bloqueo temporal.

Pendiente organizativo:

- Designar a la persona que recibe y resuelve solicitudes.
- Crear registro de fecha de ingreso, verificación de identidad, decisión,
  comunicaciones y cierre.
- Definir criterios de aceptación o rechazo con asesoría jurídica.
- Implementar exportación individual estructurada.
- Comunicar rectificaciones o supresiones a destinatarios cuando corresponda.
- Preparar canal presencial para personas sin acceso digital.

## 8. Encargados y transferencias

Proveedores identificados:

- PythonAnywhere: alojamiento de aplicación y base de datos.
- Proveedor SMTP configurado, actualmente compatible con Gmail: envío de códigos,
  notificaciones y recuperación de contraseña.

Pendiente:

- Confirmar la identidad contractual del responsable de datos.
- Identificar ubicación efectiva de almacenamiento y tratamiento.
- Revisar contratos, subencargados, medidas de seguridad, eliminación y soporte
  ante incidentes.
- Documentar si existen transferencias internacionales y su mecanismo jurídico.

## 9. Incidentes de seguridad

Debe existir un procedimiento que permita:

1. Contener el incidente y preservar evidencia.
2. Identificar datos, titulares, volumen, origen y consecuencias.
3. Evaluar el riesgo para derechos y libertades.
4. Registrar cronología, decisiones y medidas correctivas.
5. Reportar a la Agencia sin dilaciones indebidas cuando corresponda.
6. Comunicar a los titulares en los casos exigidos por la ley.
7. Probar restauración y corregir la causa raíz.

Este procedimiento aún no está implementado como flujo dentro del sistema.

## 10. Brechas pendientes priorizadas

### Prioridad crítica

- Completar razón social o identidad jurídica, representante y domicilio del
  responsable en la política.
- Validar jurídicamente la base de licitud para cada finalidad.
- Forzar HTTPS y cookies seguras en producción.
- Incorporar protección de fuerza bruta en el inicio de sesión interno.
- Restringir, cifrar y exigir reautenticación para respaldos completos.
- Registrar y revisar todas las exportaciones masivas.

### Prioridad alta

- Aprobar matriz completa de conservación y anonimización.
- Formalizar contratos con encargados y transferencias internacionales.
- Implementar gestión trazable de derechos.
- Definir y probar el plan de incidentes.
- Proteger la integridad, rotación y acceso del archivo de auditoría.
- Incorporar MFA para administradores.
- Revisar permisos con criterio de mínimo privilegio.

### Prioridad media

- Implementar PIN presencial para consulta accesible.
- Sustituir motivos libres por categorías mínimas y observación opcional.
- Evaluar formalmente el cálculo automático de bloqueo y documentar revisión
  humana y reclamación.
- Ejecutar análisis de vulnerabilidades y pruebas de recuperación periódicas.

## 11. Reglas de mantenimiento

- No modificar el texto de aceptación sin cambiar
  `POLITICA_PRIVACIDAD_VERSION`.
- No registrar códigos OTP, RUT, correos ni IP legibles en logs nuevos.
- No enviar historial o datos adicionales dentro del correo OTP.
- No aumentar duración, intentos o límites sin una evaluación de riesgo.
- Toda nueva exportación o integración debe agregarse al inventario.
- Toda migración de proveedor debe revisar ubicación y subencargados.
- Las pruebas de privacidad deben ejecutarse antes de cada despliegue.

## 12. Validación pendiente

Antes de declarar cumplimiento se requiere revisión jurídica chilena de:

- Identidad y naturaleza legal del responsable.
- Bases de licitud y consentimiento.
- Aplicación de reglas especiales para organizaciones sin fines de lucro.
- Plazos de conservación.
- Contratos y transferencias internacionales.
- Texto definitivo de la política y mecanismo de ejercicio de derechos.

La existencia de esta memoria y de controles técnicos no reemplaza esa revisión.
