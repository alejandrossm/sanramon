# Plantilla de carga masiva de socios

La plantilla CSV usa encabezados en espanol para facilitar la revision previa:

```csv
nombre,apellido_paterno,apellido_materno,rut,correo_electronico,telefono_movil,fecha_ingreso_proyecto
```

Mapeo hacia el modelo `Usuario`:

| columna csv | atributo |
| --- | --- |
| nombre | first_name |
| apellido_paterno | last_name |
| apellido_materno | apellido_materno |
| rut | rut |
| correo_electronico | email |
| telefono_movil | telefono_movil |
| fecha_ingreso_proyecto | fecha_ingreso_proyecto |

## Implementacion

- En Configuracion existe una opcion de carga masiva de socios.
- La descarga de plantilla genera el CSV con encabezados y socios actuales.
- La vista recibe un CSV subido por el administrador y valida toda la planilla antes de guardar.
- Si todas las filas son validas, crea los socios dentro de una transaccion.
- Si existe cualquier error, no persiste ningun socio.
- Cuando hay errores, muestra un modal con las filas y socios observados.
- El modal tiene scroll para listas largas de errores.
- Validaciones aplicadas: encabezados requeridos, RUT valido y unico, correo valido y unico, telefono movil valido, fecha de ingreso valida, nombre y apellido paterno no vacios.
