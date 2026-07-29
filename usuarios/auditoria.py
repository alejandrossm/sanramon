"""Auditoria JSONL con integridad HMAC, rotacion y retencion controlada."""

import gzip
import hashlib
import hmac
import json
import os
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime


ACCION_USUARIO_ACTIVADO = 'USUARIO_ACTIVADO'
ACCION_USUARIO_DESACTIVADO = 'USUARIO_DESACTIVADO'
ACCION_USUARIO_ELIMINADO = 'USUARIO_ELIMINADO'
ACCION_SOCIO_ELIMINADO = 'SOCIO_ELIMINADO'
ACCION_REUNION_CANCELADA = 'REUNION_CANCELADA'
ACCION_REUNION_ELIMINADA = 'REUNION_ELIMINADA'
ACCION_RESPALDO_BASE_DATOS = 'RESPALDO_BASE_DATOS'
ACCION_CARGA_HISTORICA_REVERTIDA = 'CARGA_HISTORICA_REVERTIDA'
ACCION_CARGA_HISTORICA = 'CARGA_HISTORICA'
ACCION_CARGA_MASIVA_SOCIOS = 'CARGA_MASIVA_SOCIOS'
ACCION_CONSULTA_PUBLICA_VERIFICADA = 'CONSULTA_PUBLICA_VERIFICADA'
ACCION_PRIVACIDAD_CONSULTA_ACEPTADA = 'PRIVACIDAD_CONSULTA_ACEPTADA'
ACCION_CONSULTA_PUBLICA_ACCEDIDA = 'CONSULTA_PUBLICA_ACCEDIDA'
ACCION_LOGIN_BLOQUEADO = 'LOGIN_BLOQUEADO'
ACCION_RECUPERACION_LIMITADA = 'RECUPERACION_LIMITADA'
ACCION_REAUTENTICACION_EXITOSA = 'REAUTENTICACION_EXITOSA'
ACCION_REAUTENTICACION_FALLIDA = 'REAUTENTICACION_FALLIDA'
ACCION_REPORTE_EXPORTADO = 'REPORTE_EXPORTADO'
ACCION_LOG_AUDITORIA_DESCARGADO = 'LOG_AUDITORIA_DESCARGADO'

ETIQUETAS_ACCIONES_AUDITORIA = {
    ACCION_USUARIO_ACTIVADO: 'Usuario activado',
    ACCION_USUARIO_DESACTIVADO: 'Usuario desactivado',
    ACCION_USUARIO_ELIMINADO: 'Usuario eliminado',
    ACCION_SOCIO_ELIMINADO: 'Socio eliminado',
    ACCION_REUNION_CANCELADA: 'Reunion cancelada',
    ACCION_REUNION_ELIMINADA: 'Reunion eliminada',
    ACCION_RESPALDO_BASE_DATOS: 'Respaldo cifrado de base de datos',
    ACCION_CARGA_HISTORICA_REVERTIDA: 'Carga historica revertida',
    ACCION_CARGA_HISTORICA: 'Carga historica registrada',
    ACCION_CARGA_MASIVA_SOCIOS: 'Carga masiva de socios',
    ACCION_CONSULTA_PUBLICA_VERIFICADA: 'Consulta publica verificada',
    ACCION_PRIVACIDAD_CONSULTA_ACEPTADA: 'Privacidad de consulta aceptada',
    ACCION_CONSULTA_PUBLICA_ACCEDIDA: 'Consulta publica accedida',
    ACCION_LOGIN_BLOQUEADO: 'Inicio de sesion bloqueado',
    ACCION_RECUPERACION_LIMITADA: 'Recuperacion limitada',
    ACCION_REAUTENTICACION_EXITOSA: 'Reautenticacion exitosa',
    ACCION_REAUTENTICACION_FALLIDA: 'Reautenticacion fallida',
    ACCION_REPORTE_EXPORTADO: 'Reporte exportado',
    ACCION_LOG_AUDITORIA_DESCARGADO: 'Log de auditoria descargado',
}


def obtener_ruta_auditoria():
    """Devuelve la ruta del archivo activo de auditoria."""
    ruta = getattr(settings, 'AUDITORIA_LOG_PATH', None)
    if ruta:
        return Path(ruta)
    return Path(settings.BASE_DIR) / 'auditoria.log'


def _clave_hmac():
    return str(getattr(settings, 'AUDITORIA_HMAC_KEY', settings.SECRET_KEY)).encode(
        'utf-8'
    )


def _serializar_usuario(usuario):
    if not usuario or not getattr(usuario, 'is_authenticated', False):
        return {
            'usuario_id': '',
            'usuario': 'Sistema',
            'usuario_nombre': 'Sistema',
        }
    return {
        'usuario_id': usuario.pk,
        'usuario': usuario.username,
        'usuario_nombre': usuario.nombre_completo,
    }


def _contenido_firmable(evento):
    datos = {
        clave: valor
        for clave, valor in evento.items()
        if clave != 'integridad_hmac'
    }
    return json.dumps(
        datos,
        ensure_ascii=True,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')


def _firmar_evento(evento):
    return hmac.new(
        _clave_hmac(),
        _contenido_firmable(evento),
        hashlib.sha256,
    ).hexdigest()


def _abrir_lectura(ruta):
    if ruta.suffix == '.gz':
        return gzip.open(ruta, 'rt', encoding='utf-8')
    return ruta.open('r', encoding='utf-8')


def _restringir_permisos(ruta):
    """Limita lectura/escritura al usuario del proceso cuando el SO lo permite."""
    try:
        os.chmod(ruta, 0o600)
    except OSError:
        pass


def _leer_eventos_archivo(ruta):
    if not ruta.exists() or not ruta.is_file():
        return []
    eventos = []
    with _abrir_lectura(ruta) as archivo:
        for linea in archivo:
            try:
                eventos.append(json.loads(linea))
            except json.JSONDecodeError:
                continue
    return eventos


def _ultimo_hash_archivo(ruta):
    for evento in reversed(_leer_eventos_archivo(ruta)):
        firma = evento.get('integridad_hmac')
        if firma:
            return firma
    return ''


def _rutas_archivadas(ruta_activa):
    patron = f'{ruta_activa.stem}-*.log.gz'
    return sorted(ruta_activa.parent.glob(patron))


def _ultimo_hash_global(ruta_activa):
    firma = _ultimo_hash_archivo(ruta_activa)
    if firma:
        return firma
    for ruta in reversed(_rutas_archivadas(ruta_activa)):
        firma = _ultimo_hash_archivo(ruta)
        if firma:
            return firma
    return ''


@contextmanager
def _bloqueo_archivo(ruta):
    """Serializa escrituras entre procesos en Windows y Unix."""
    ruta_bloqueo = ruta.with_suffix(f'{ruta.suffix}.lock')
    ruta_bloqueo.parent.mkdir(parents=True, exist_ok=True)
    with ruta_bloqueo.open('a+b') as archivo:
        archivo.seek(0, os.SEEK_END)
        if archivo.tell() == 0:
            archivo.write(b'0')
            archivo.flush()
        archivo.seek(0)
        if os.name == 'nt':
            import msvcrt

            msvcrt.locking(archivo.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(archivo.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            archivo.seek(0)
            if os.name == 'nt':
                msvcrt.locking(archivo.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(archivo.fileno(), fcntl.LOCK_UN)


def _mes_del_archivo(ruta):
    for evento in _leer_eventos_archivo(ruta):
        fecha = parse_datetime(evento.get('fecha_hora', ''))
        if fecha:
            return fecha.strftime('%Y-%m')
    if ruta.exists():
        return datetime.fromtimestamp(
            ruta.stat().st_mtime,
            tz=timezone.get_current_timezone(),
        ).strftime('%Y-%m')
    return timezone.localdate().strftime('%Y-%m')


def _debe_rotar(ruta, ahora):
    if not ruta.exists() or ruta.stat().st_size == 0:
        return False
    if not verificar_integridad_archivo(ruta):
        return True
    maximo = int(getattr(settings, 'AUDITORIA_ROTACION_BYTES', 10 * 1024 * 1024))
    if ruta.stat().st_size >= maximo:
        return True
    return _mes_del_archivo(ruta) != ahora.strftime('%Y-%m')


def _ruta_archivo_disponible(ruta_activa, mes):
    base = ruta_activa.parent / f'{ruta_activa.stem}-{mes}.log.gz'
    if not base.exists():
        return base
    indice = 2
    while True:
        candidata = ruta_activa.parent / (
            f'{ruta_activa.stem}-{mes}_{indice:02d}.log.gz'
        )
        if not candidata.exists():
            return candidata
        indice += 1


def _rotar_archivo(ruta):
    mes = _mes_del_archivo(ruta)
    destino = _ruta_archivo_disponible(ruta, mes)
    temporal = destino.with_suffix(f'{destino.suffix}.tmp')
    with ruta.open('rb') as origen, gzip.open(temporal, 'wb') as comprimido:
        while bloque := origen.read(1024 * 1024):
            comprimido.write(bloque)
    os.replace(temporal, destino)
    _restringir_permisos(destino)
    ruta.unlink(missing_ok=True)
    return destino


def _eliminar_archivos_vencidos(ruta_activa, ahora):
    meses = int(getattr(settings, 'AUDITORIA_RETENCION_MESES', 12))
    if meses <= 0:
        return
    limite = ahora - timedelta(days=meses * 31)
    for ruta in _rutas_archivadas(ruta_activa):
        modificado = datetime.fromtimestamp(
            ruta.stat().st_mtime,
            tz=timezone.get_current_timezone(),
        )
        if modificado < limite:
            ruta.unlink(missing_ok=True)


def registrar_evento_auditoria(
    usuario,
    accion,
    entidad_tipo='',
    entidad_id='',
    entidad='',
    detalle='',
):
    """Agrega un evento firmado y rota el archivo cuando corresponde."""
    ahora = timezone.localtime()
    ruta = obtener_ruta_auditoria()
    ruta.parent.mkdir(parents=True, exist_ok=True)

    with _bloqueo_archivo(ruta):
        hash_anterior = _ultimo_hash_global(ruta)
        if _debe_rotar(ruta, ahora):
            _rotar_archivo(ruta)
        _eliminar_archivos_vencidos(ruta, ahora)

        evento = {
            'fecha_hora': ahora.isoformat(),
            'accion': accion,
            'accion_label': ETIQUETAS_ACCIONES_AUDITORIA.get(accion, accion),
            'entidad_tipo': str(entidad_tipo or ''),
            'entidad_id': str(entidad_id or ''),
            'entidad': str(entidad or ''),
            'detalle': str(detalle or ''),
            **_serializar_usuario(usuario),
            'integridad_version': 1,
            'integridad_anterior': hash_anterior,
        }
        evento['integridad_hmac'] = _firmar_evento(evento)
        with ruta.open('a', encoding='utf-8') as archivo:
            archivo.write(json.dumps(evento, ensure_ascii=True, sort_keys=True))
            archivo.write('\n')
        _restringir_permisos(ruta)
    return evento


def verificar_integridad_archivo(ruta):
    """Verifica firmas y encadenamiento interno de un archivo."""
    eventos = _leer_eventos_archivo(ruta)
    if not eventos:
        return False
    anterior = None
    for evento in eventos:
        firma = evento.get('integridad_hmac', '')
        if not firma or not hmac.compare_digest(firma, _firmar_evento(evento)):
            return False
        if anterior is not None and evento.get('integridad_anterior') != anterior:
            return False
        anterior = firma
    return True


def listar_archivos_auditoria():
    """Lista solo el archivo activo y archivos rotados con nombre controlado."""
    ruta_activa = obtener_ruta_auditoria()
    rutas = []
    if ruta_activa.exists() and ruta_activa.is_file():
        rutas.append(('actual', 'Log actual', ruta_activa, False))
    for ruta in reversed(_rutas_archivadas(ruta_activa)):
        periodo = ruta.name.removeprefix(f'{ruta_activa.stem}-').removesuffix(
            '.log.gz'
        )
        rutas.append((ruta.name, periodo, ruta, True))
    return [
        {
            'id': identificador,
            'label': etiqueta,
            'ruta': ruta,
            'comprimido': comprimido,
            'tamano': ruta.stat().st_size,
            'integridad_valida': verificar_integridad_archivo(ruta),
        }
        for identificador, etiqueta, ruta, comprimido in rutas
    ]


def obtener_archivo_auditoria_autorizado(identificador):
    """Resuelve un identificador exclusivamente desde la lista permitida."""
    return next(
        (
            archivo
            for archivo in listar_archivos_auditoria()
            if archivo['id'] == identificador
        ),
        None,
    )


def leer_eventos_auditoria(limite=200):
    """Lee los ultimos eventos del log activo e informa su integridad."""
    eventos = []
    for evento in reversed(_leer_eventos_archivo(obtener_ruta_auditoria())):
        if len(eventos) >= limite:
            break
        firma = evento.get('integridad_hmac', '')
        evento['integridad_valida'] = bool(
            firma and hmac.compare_digest(firma, _firmar_evento(evento))
        )
        fecha_hora = parse_datetime(evento.get('fecha_hora', ''))
        if fecha_hora:
            evento['fecha_hora'] = timezone.localtime(fecha_hora)
        evento['accion_label'] = ETIQUETAS_ACCIONES_AUDITORIA.get(
            evento.get('accion'),
            evento.get('accion', ''),
        )
        eventos.append(evento)
    return eventos
