import json
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
ACCION_CARGA_MASIVA_SOCIOS = 'CARGA_MASIVA_SOCIOS'

ETIQUETAS_ACCIONES_AUDITORIA = {
    ACCION_USUARIO_ACTIVADO: 'Usuario activado',
    ACCION_USUARIO_DESACTIVADO: 'Usuario desactivado',
    ACCION_USUARIO_ELIMINADO: 'Usuario eliminado',
    ACCION_SOCIO_ELIMINADO: 'Socio eliminado',
    ACCION_REUNION_CANCELADA: 'Reunion cancelada',
    ACCION_REUNION_ELIMINADA: 'Reunion eliminada',
    ACCION_RESPALDO_BASE_DATOS: 'Respaldo de base de datos',
    ACCION_CARGA_HISTORICA_REVERTIDA: 'Carga historica revertida',
    ACCION_CARGA_MASIVA_SOCIOS: 'Carga masiva de socios',
}


def obtener_ruta_auditoria():
    """Devuelve la ruta del archivo auditoria.log."""
    ruta = getattr(settings, 'AUDITORIA_LOG_PATH', None)
    if ruta:
        return Path(ruta)
    return Path(settings.BASE_DIR) / 'auditoria.log'


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


def registrar_evento_auditoria(
    usuario,
    accion,
    entidad_tipo='',
    entidad_id='',
    entidad='',
    detalle='',
):
    """Agrega un evento critico al archivo auditoria.log."""
    ahora = timezone.localtime()
    evento = {
        'fecha_hora': ahora.isoformat(),
        'accion': accion,
        'accion_label': ETIQUETAS_ACCIONES_AUDITORIA.get(accion, accion),
        'entidad_tipo': str(entidad_tipo or ''),
        'entidad_id': str(entidad_id or ''),
        'entidad': str(entidad or ''),
        'detalle': str(detalle or ''),
        **_serializar_usuario(usuario),
    }

    ruta = obtener_ruta_auditoria()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open('a', encoding='utf-8') as archivo:
        archivo.write(json.dumps(evento, ensure_ascii=True, sort_keys=True))
        archivo.write('\n')

    return evento


def leer_eventos_auditoria(limite=200):
    """Lee los ultimos eventos validos registrados en auditoria.log."""
    ruta = obtener_ruta_auditoria()
    if not ruta.exists() or not ruta.is_file():
        return []

    eventos = []
    with ruta.open('r', encoding='utf-8') as archivo:
        lineas = archivo.readlines()

    for linea in reversed(lineas):
        if len(eventos) >= limite:
            break
        linea = linea.strip()
        if not linea:
            continue
        try:
            evento = json.loads(linea)
        except json.JSONDecodeError:
            continue

        fecha_hora = parse_datetime(evento.get('fecha_hora', ''))
        if fecha_hora:
            evento['fecha_hora'] = timezone.localtime(fecha_hora)
        evento['accion_label'] = ETIQUETAS_ACCIONES_AUDITORIA.get(
            evento.get('accion'),
            evento.get('accion', ''),
        )
        eventos.append(evento)

    return eventos
