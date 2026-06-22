import csv
import io
import unicodedata

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from .identificacion import parsear_lectura_rut
from .models import AsistenciaReunion, Reunion, Usuario
from .reportes_asistencia import construir_csv, construir_xlsx


COLUMNAS_PLANTILLA_CARGA_HISTORICA = [
    'RUT',
    'Nombre',
    'Apellido paterno',
    'Apellido materno',
    'Situaci\u00f3n',
]

ALIAS_COLUMNAS_CARGA_HISTORICA = {
    'situacion': 'estado',
}

ESTADOS_CARGA_HISTORICA = {
    'presente': AsistenciaReunion.PRESENTE,
    'p': AsistenciaReunion.PRESENTE,
    'si': AsistenciaReunion.PRESENTE,
    'asiste': AsistenciaReunion.PRESENTE,
    'asistio': AsistenciaReunion.PRESENTE,
    'ausente': AsistenciaReunion.AUSENTE,
    'a': AsistenciaReunion.AUSENTE,
    'no': AsistenciaReunion.AUSENTE,
    'inasistente': AsistenciaReunion.AUSENTE,
    'inasistencia': AsistenciaReunion.AUSENTE,
    'falta': AsistenciaReunion.AUSENTE,
}


class ErrorCargaAsistenciaHistorica(Exception):
    """Error de validacion al importar asistencia historica."""


def construir_plantilla_carga_historica():
    """Genera plantilla XLSX con socios y columna de estado editable."""
    filas = []
    socios = Usuario.objects.filter(
        rol=Usuario.SOCIO,
        is_active=True,
    ).order_by(
        'last_name',
        'apellido_materno',
        'first_name',
        'username',
    )
    for socio in socios:
        filas.append(
            [
                socio.rut,
                socio.first_name,
                socio.last_name,
                socio.apellido_materno,
                '',
            ]
        )

    return construir_xlsx(
        COLUMNAS_PLANTILLA_CARGA_HISTORICA,
        filas,
        nombre_hoja='Carga historica',
    )


def construir_plantilla_carga_historica_csv():
    """Genera CSV de referencia con los encabezados de carga historica."""
    return construir_csv(COLUMNAS_PLANTILLA_CARGA_HISTORICA, [])


def cargar_asistencia_historica_desde_csv(reunion, archivo_csv, usuario):
    """Carga asistencia historica desde CSV separado por coma o punto y coma."""
    if reunion.estado != Reunion.HISTORICA:
        raise ErrorCargaAsistenciaHistorica(
            'Solo se puede cargar asistencia en reuniones historicas.'
        )

    filas = _leer_filas_csv(archivo_csv)
    if not filas:
        raise ErrorCargaAsistenciaHistorica('El archivo no contiene registros.')

    socios_cargados = set()
    presentes = 0
    ausentes = 0

    with transaction.atomic():
        for numero_fila, fila in filas:
            rut = _obtener_valor(fila, 'rut')
            estado = _obtener_valor(fila, 'estado')

            lectura_rut = parsear_lectura_rut(rut)
            if not lectura_rut:
                raise ErrorCargaAsistenciaHistorica(
                    f'Fila {numero_fila}: RUT invalido.'
                )

            estado_asistencia = _normalizar_estado(estado, numero_fila)
            socio = Usuario.objects.filter(
                rut__iexact=lectura_rut.rut,
                rol=Usuario.SOCIO,
            ).first()
            if not socio:
                raise ErrorCargaAsistenciaHistorica(
                    f'Fila {numero_fila}: socio no encontrado para RUT {rut}.'
                )
            if socio.pk in socios_cargados:
                raise ErrorCargaAsistenciaHistorica(
                    f'Fila {numero_fila}: socio duplicado en el archivo.'
                )
            if AsistenciaReunion.objects.filter(reunion=reunion, socio=socio).exists():
                raise ErrorCargaAsistenciaHistorica(
                    f'Fila {numero_fila}: el socio ya tiene asistencia en esta reunion.'
                )

            asistencia = AsistenciaReunion(
                reunion=reunion,
                socio=socio,
                estado=estado_asistencia,
                origen=AsistenciaReunion.ORIGEN_MANUAL,
                registrada_por=usuario,
            )
            try:
                asistencia.save()
            except ValidationError as error:
                raise ErrorCargaAsistenciaHistorica(
                    f'Fila {numero_fila}: {_formatear_error_validacion(error)}'
                ) from error
            except IntegrityError as error:
                raise ErrorCargaAsistenciaHistorica(
                    f'Fila {numero_fila}: asistencia duplicada.'
                ) from error

            socios_cargados.add(socio.pk)
            if estado_asistencia == AsistenciaReunion.PRESENTE:
                presentes += 1
            else:
                ausentes += 1

    return {
        'total': presentes + ausentes,
        'presentes': presentes,
        'ausentes': ausentes,
    }


def _leer_filas_csv(archivo_csv):
    contenido = archivo_csv.read()
    if not contenido:
        return []
    try:
        texto = contenido.decode('utf-8-sig')
    except UnicodeDecodeError:
        texto = contenido.decode('cp1252')

    texto = texto.replace('\r\n', '\n').replace('\r', '\n')
    primera_linea, _separador, resto = texto.partition('\n')
    if primera_linea.lower().startswith('sep=') and len(primera_linea) >= 5:
        delimitador = primera_linea[4]
        texto = resto
    else:
        delimitador = ''

    muestra = texto[:2048]
    if delimitador in {';', ','}:
        dialecto = csv.excel()
        dialecto.delimiter = delimitador
    else:
        try:
            dialecto = csv.Sniffer().sniff(muestra, delimiters=';,')
        except csv.Error:
            dialecto = csv.excel()
            dialecto.delimiter = ';' if muestra.count(';') >= muestra.count(',') else ','

    lector = csv.DictReader(io.StringIO(texto), dialect=dialecto)
    if not lector.fieldnames:
        return []

    campos_normalizados = {}
    for campo in lector.fieldnames:
        clave_normalizada = _normalizar_clave(campo)
        campos_normalizados[campo] = ALIAS_COLUMNAS_CARGA_HISTORICA.get(
            clave_normalizada,
            clave_normalizada,
        )
    if 'rut' not in campos_normalizados.values():
        raise ErrorCargaAsistenciaHistorica('El archivo debe incluir la columna RUT.')
    if 'estado' not in campos_normalizados.values():
        raise ErrorCargaAsistenciaHistorica(
            'El archivo debe incluir la columna Situacion.'
        )

    filas = []
    for numero_fila, fila in enumerate(lector, start=2):
        fila_normalizada = {
            campos_normalizados[campo]: (valor or '').strip()
            for campo, valor in fila.items()
            if campo in campos_normalizados
        }
        if any(fila_normalizada.values()):
            filas.append((numero_fila, fila_normalizada))

    return filas


def _normalizar_estado(valor, numero_fila):
    estado = _normalizar_clave(valor)
    if estado not in ESTADOS_CARGA_HISTORICA:
        raise ErrorCargaAsistenciaHistorica(
            f'Fila {numero_fila}: Estado debe ser Presente o Ausente.'
        )
    return ESTADOS_CARGA_HISTORICA[estado]


def _obtener_valor(fila, clave):
    return fila.get(clave, '').strip()


def _normalizar_clave(valor):
    valor = valor or ''
    valor = unicodedata.normalize('NFKD', valor.strip().lower())
    valor = ''.join(caracter for caracter in valor if not unicodedata.combining(caracter))
    return valor.replace(' ', '_')


def _formatear_error_validacion(error):
    if hasattr(error, 'message_dict'):
        mensajes = []
        for errores in error.message_dict.values():
            mensajes.extend(errores)
        return ' '.join(mensajes)
    return ' '.join(error.messages)
