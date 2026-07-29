# Candidato de release 1.0.0

Este documento define la puerta de salida para crear el tag anotado `v1.0.0`.
El tag solo debe crearse cuando todos los controles tecnicos y operativos
aplicables esten aprobados sobre el mismo commit.

## Controles automatizados

- [ ] El workflow CI pasa en Python 3.13.
- [x] Las pruebas de Django pasan localmente.
- [x] `python manage.py makemigrations --check --dry-run` no detecta cambios.
- [x] `python manage.py check --deploy` no presenta advertencias no aceptadas.
- [x] `python manage.py collectstatic --noinput --dry-run` pasa.
- [x] `pip check` pasa.
- [x] La auditoria de dependencias no detecta vulnerabilidades conocidas.

## Seguridad y datos

- [x] Los comandos que generan datos demo fallan con `DEBUG=False`.
- [x] El modelo impide colisiones, sin distinguir mayusculas, entre `username`
  y `email` de cuentas diferentes.
- [x] La base local no contiene colisiones de identidad.
- [x] Existe un preflight reutilizable: `python manage.py verificar_identidades`.
- [x] El cifrado, descifrado e integridad SQLite de un respaldo local fueron
  comprobados.
- [ ] La base de datos que sera desplegada no contiene colisiones de identidad.
- [ ] `DEBUG=False` y los secretos de produccion estan configurados fuera de Git.
- [ ] Existe un respaldo cifrado reciente y se comprobo su restauracion.
- [ ] Se revisaron permisos de administrador, encargado, socio y superusuario.

## Validacion manual del candidato

- [ ] Login y cierre de sesion.
- [ ] Recuperacion de contrasena y entrega real de correo.
- [ ] Consulta publica, codigo OTP, expiracion y limite de intentos.
- [ ] Alta y edicion de usuarios y socios.
- [ ] Ciclo de reunion y registro de asistencia.
- [ ] Bloqueo por inasistencia y justificacion.
- [ ] Cargas CSV y exportaciones CSV, XLSX y PDF.
- [ ] Auditoria y descarga o rotacion de registros.

## Despliegue

- [ ] Se valido el candidato en un entorno equivalente a PythonAnywhere.
- [ ] Las migraciones se probaron sobre una copia de la base de produccion.
- [ ] `Force HTTPS` esta activo y HTTP redirige a HTTPS.
- [ ] Login, correo y archivos estaticos funcionan bajo HTTPS.
- [ ] HSTS comienza con el periodo documentado y sin incluir subdominios ni
  preload hasta validarlos expresamente.
- [x] Existe un procedimiento documentado de retorno al commit y respaldo
  anteriores.

## Gobierno y cumplimiento

La revision tecnica no sustituye las decisiones organizativas y juridicas
registradas en `MEMORIA_CUMPLIMIENTO_LEY_21719.md`. Antes de produccion, el
responsable del proyecto debe aceptar o cerrar formalmente esas brechas.

## Creacion del tag

Con todos los controles aprobados, desde `main` y sobre el commit desplegado:

```bash
git tag -a v1.0.0 -m "Release 1.0.0"
git push origin v1.0.0
```
