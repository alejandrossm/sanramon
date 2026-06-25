import csv
import io
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.utils import timezone

from .identificacion import parsear_lectura_rut
from .models import (
    TELEFONO_MOVIL_MENSAJE_CHILE,
    TELEFONO_MOVIL_REGEX_CHILE,
    Usuario,
    normalizar_telefono_movil,
)
from .reportes_asistencia import construir_csv


COLUMNAS_PLANTILLA_CARGA_MASIVA_SOCIOS = [
    'nombre',
    'apellido_paterno',
    'apellido_materno',
    'rut',
    'correo_electronico',
    'telefono_movil',
    'fecha_ingreso_proyecto',
]

COLUMNAS_REQUERIDAS_CARGA_MASIVA_SOCIOS = {
    'nombre',
    'apellido_paterno',
    'rut',
    'correo_electronico',
}

ALIAS_COLUMNAS_CARGA_MASIVA_SOCIOS = {
    'apellido': 'apellido_paterno',
    'apellidos': 'apellido_paterno',
    'celular': 'telefono_movil',
    'correo': 'correo_electronico',
    'email': 'correo_electronico',
    'fecha_ingreso': 'fecha_ingreso_proyecto',
    'fecha_de_ingreso': 'fecha_ingreso_proyecto',
    'telefono': 'telefono_movil',
}


@dataclass(frozen=True)
class ErrorFilaCargaSocio:
    """Detalle legible de un error detectado en la planilla."""

    fila: str
    socio: str
    mensaje: str


class ErrorCargaMasivaSocios(Exception):
    """Error de validacion al importar socios por planilla."""

    def __init__(self, errores):
        self.errores = list(errores)
        super().__init__('La planilla contiene errores. No se creo ningun socio.')


def construir_plantilla_carga_masiva_socios():
    """Genera CSV con encabezados y socios actuales para respaldo/importacion."""
    filas = []
    socios = Usuario.objects.filter(rol=Usuario.SOCIO).order_by(
        'last_name',
        'apellido_materno',
        'first_name',
        'username',
    )
    for socio in socios:
        filas.append(
            [
                socio.first_name,
                socio.last_name,
                socio.apellido_materno,
                socio.rut,
                socio.email,
                socio.telefono_movil or '',
                (
                    socio.fecha_ingreso_proyecto.isoformat()
                    if socio.fecha_ingreso_proyecto
                    else ''
                ),
            ]
        )

    return construir_csv(COLUMNAS_PLANTILLA_CARGA_MASIVA_SOCIOS, filas)


def cargar_socios_desde_csv(archivo_csv):
    """Crea socios desde CSV validando todo el lote antes de persistir."""
    filas = _leer_filas_csv(archivo_csv)
    if not filas:
        raise ErrorCargaMasivaSocios(
            [
                ErrorFilaCargaSocio(
                    fila='Archivo',
                    socio='',
                    mensaje='El archivo no contiene registros.',
                )
            ]
        )

    errores = []
    usuarios = []
    ruts_archivo = set()
    correos_archivo = set()
    ruts_existentes = {
        (rut or '').lower()
        for rut in Usuario.objects.values_list('rut', flat=True)
    }
    correos_existentes = {
        (email or '').lower()
        for email in Usuario.objects.values_list('email', flat=True)
    }
    usernames_existentes = {
        (username or '').lower()
        for username in Usuario.objects.values_list('username', flat=True)
    }

    for numero_fila, fila in filas:
        usuario = _construir_usuario_desde_fila(
            numero_fila,
            fila,
            errores,
            ruts_archivo,
            correos_archivo,
            ruts_existentes,
            correos_existentes,
            usernames_existentes,
        )
        if usuario is not None:
            usuarios.append(usuario)

    if errores:
        raise ErrorCargaMasivaSocios(errores)

    try:
        with transaction.atomic():
            for usuario in usuarios:
                usuario.save()
    except (IntegrityError, ValidationError) as error:
        raise ErrorCargaMasivaSocios(
            [
                ErrorFilaCargaSocio(
                    fila='General',
                    socio='',
                    mensaje=_formatear_error_validacion(error),
                )
            ]
        ) from error

    return {
        'total': len(usuarios),
        'socios': usuarios,
    }


def _construir_usuario_desde_fila(
    numero_fila,
    fila,
    errores,
    ruts_archivo,
    correos_archivo,
    ruts_existentes,
    correos_existentes,
    usernames_existentes,
):
    nombre = _obtener_valor(fila, 'nombre')
    apellido_paterno = _obtener_valor(fila, 'apellido_paterno')
    apellido_materno = _obtener_valor(fila, 'apellido_materno')
    rut_original = _obtener_valor(fila, 'rut')
    correo_original = _obtener_valor(fila, 'correo_electronico')
    telefono_original = _obtener_valor(fila, 'telefono_movil')
    fecha_original = _obtener_valor(fila, 'fecha_ingreso_proyecto')
    socio_observado = _construir_socio_observado(
        nombre,
        apellido_paterno,
        apellido_materno,
        rut_original,
        correo_original,
    )
    errores_iniciales = len(errores)

    if not nombre:
        _agregar_error(errores, numero_fila, socio_observado, 'El nombre es obligatorio.')
    if not apellido_paterno:
        _agregar_error(
            errores,
            numero_fila,
            socio_observado,
            'El apellido paterno es obligatorio.',
        )

    rut = _validar_rut(
        numero_fila,
        socio_observado,
        rut_original,
        errores,
        ruts_archivo,
        ruts_existentes,
    )
    correo = _validar_correo(
        numero_fila,
        socio_observado,
        correo_original,
        errores,
        correos_archivo,
        correos_existentes,
        usernames_existentes,
    )
    telefono = _validar_telefono(
        numero_fila,
        socio_observado,
        telefono_original,
        errores,
    )
    fecha_ingreso = _validar_fecha_ingreso(
        numero_fila,
        socio_observado,
        fecha_original,
        errores,
    )

    if len(errores) > errores_iniciales:
        return None

    usuario = Usuario(
        username=correo,
        email=correo,
        first_name=nombre,
        last_name=apellido_paterno,
        apellido_materno=apellido_materno,
        rut=rut,
        telefono_movil=telefono,
        fecha_ingreso_proyecto=fecha_ingreso,
        rol=Usuario.SOCIO,
        is_active=True,
        is_staff=False,
        is_superuser=False,
    )
    usuario.set_unusable_password()

    try:
        usuario.full_clean()
    except ValidationError as error:
        _agregar_error(
            errores,
            numero_fila,
            socio_observado,
            _formatear_error_validacion(error),
        )
        return None

    return usuario


def _validar_rut(
    numero_fila,
    socio_observado,
    rut_original,
    errores,
    ruts_archivo,
    ruts_existentes,
):
    if not rut_original:
        _agregar_error(errores, numero_fila, socio_observado, 'El RUT es obligatorio.')
        return ''

    lectura_rut = parsear_lectura_rut(rut_original)
    if not lectura_rut:
        _agregar_error(errores, numero_fila, socio_observado, 'El RUT no es valido.')
        return ''

    rut = lectura_rut.rut
    clave = rut.lower()
    if clave in ruts_archivo:
        _agregar_error(
            errores,
            numero_fila,
            socio_observado,
            'El RUT esta duplicado en la planilla.',
        )
    elif clave in ruts_existentes:
        _agregar_error(
            errores,
            numero_fila,
            socio_observado,
            'Ya existe un usuario con este RUT.',
        )
    else:
        ruts_archivo.add(clave)

    return rut


def _validar_correo(
    numero_fila,
    socio_observado,
    correo_original,
    errores,
    correos_archivo,
    correos_existentes,
    usernames_existentes,
):
    correo = (correo_original or '').strip().lower()
    if not correo:
        _agregar_error(
            errores,
            numero_fila,
            socio_observado,
            'El correo electronico es obligatorio.',
        )
        return ''

    try:
        validate_email(correo)
    except ValidationError:
        _agregar_error(
            errores,
            numero_fila,
            socio_observado,
            'El correo electronico no es valido.',
        )
        return correo

    if correo in correos_archivo:
        _agregar_error(
            errores,
            numero_fila,
            socio_observado,
            'El correo electronico esta duplicado en la planilla.',
        )
    elif correo in correos_existentes:
        _agregar_error(
            errores,
            numero_fila,
            socio_observado,
            'Ya existe un usuario con este correo.',
        )
    elif correo in usernames_existentes:
        _agregar_error(
            errores,
            numero_fila,
            socio_observado,
            'Ya existe un usuario tecnico con este correo.',
        )
    else:
        correos_archivo.add(correo)

    return correo


def _validar_telefono(numero_fila, socio_observado, telefono_original, errores):
    telefono = normalizar_telefono_movil(telefono_original)
    if telefono and not re.fullmatch(TELEFONO_MOVIL_REGEX_CHILE, telefono):
        _agregar_error(
            errores,
            numero_fila,
            socio_observado,
            TELEFONO_MOVIL_MENSAJE_CHILE,
        )
    return telefono


def _validar_fecha_ingreso(numero_fila, socio_observado, fecha_original, errores):
    if not fecha_original:
        return timezone.localdate()

    try:
        return datetime.strptime(fecha_original, '%Y-%m-%d').date()
    except ValueError:
        _agregar_error(
            errores,
            numero_fila,
            socio_observado,
            'La fecha de ingreso debe usar formato YYYY-MM-DD.',
        )
        return None


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

    campos_normalizados = _normalizar_encabezados(lector.fieldnames)
    campos_presentes = set(campos_normalizados.values())
    faltantes = COLUMNAS_REQUERIDAS_CARGA_MASIVA_SOCIOS - campos_presentes
    if faltantes:
        errores = [
            ErrorFilaCargaSocio(
                fila='Encabezados',
                socio='',
                mensaje=f'Falta la columna obligatoria {columna}.',
            )
            for columna in sorted(faltantes)
        ]
        raise ErrorCargaMasivaSocios(errores)

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


def _normalizar_encabezados(fieldnames):
    campos_normalizados = {}
    columnas_usadas = set()
    errores = []
    for campo in fieldnames:
        clave_normalizada = _normalizar_clave(campo)
        clave = ALIAS_COLUMNAS_CARGA_MASIVA_SOCIOS.get(
            clave_normalizada,
            clave_normalizada,
        )
        if clave not in COLUMNAS_PLANTILLA_CARGA_MASIVA_SOCIOS:
            continue
        if clave in columnas_usadas:
            errores.append(
                ErrorFilaCargaSocio(
                    fila='Encabezados',
                    socio='',
                    mensaje=f'La columna {clave} esta duplicada.',
                )
            )
            continue
        columnas_usadas.add(clave)
        campos_normalizados[campo] = clave

    if errores:
        raise ErrorCargaMasivaSocios(errores)
    return campos_normalizados


def _obtener_valor(fila, clave):
    return (fila.get(clave) or '').strip()


def _normalizar_clave(valor):
    valor = unicodedata.normalize('NFKD', (valor or '').strip().lower())
    valor = ''.join(caracter for caracter in valor if not unicodedata.combining(caracter))
    valor = re.sub(r'[^a-z0-9]+', '_', valor)
    return valor.strip('_')


def _construir_socio_observado(nombre, apellido_paterno, apellido_materno, rut, correo):
    nombre_completo = ' '.join(
        parte
        for parte in (nombre, apellido_paterno, apellido_materno)
        if parte
    )
    return nombre_completo or rut or correo or 'Sin identificar'


def _agregar_error(errores, numero_fila, socio_observado, mensaje):
    errores.append(
        ErrorFilaCargaSocio(
            fila=str(numero_fila),
            socio=socio_observado,
            mensaje=mensaje,
        )
    )


def _formatear_error_validacion(error):
    if hasattr(error, 'message_dict'):
        mensajes = []
        for errores in error.message_dict.values():
            mensajes.extend(errores)
        return ' '.join(mensajes)
    if hasattr(error, 'messages'):
        return ' '.join(error.messages)
    return str(error)
