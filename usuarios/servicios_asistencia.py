from django.db.models import Count, Q
from django.utils import timezone

from .models import AsistenciaReunion, DesbloqueoSocio, Reunion, Usuario


def _filtro_anio_asistencia(prefijo, anio):
    """Construye filtros opcionales por ano de reunion."""
    if not anio:
        return Q()
    return Q(**{f'{prefijo}reunion__fecha__year': anio})


def obtener_resumen_asistencia_socio(socio, anio=None):
    """Devuelve contadores de asistencia de un socio, opcionalmente por ano."""
    filtro_anio = _filtro_anio_asistencia('', anio)
    resumen = AsistenciaReunion.objects.filter(
        Q(socio=socio) & filtro_anio
    ).aggregate(
        total_reuniones=Count('pk'),
        total_asistencias=Count(
            'pk',
            filter=Q(estado=AsistenciaReunion.PRESENTE),
        ),
        total_ausencias=Count(
            'pk',
            filter=Q(estado=AsistenciaReunion.AUSENTE),
        ),
        total_ausencias_efectivas=Count(
            'pk',
            filter=Q(
                estado=AsistenciaReunion.AUSENTE,
                justificacion__isnull=True,
            ),
        ),
    )
    resumen['total_justificaciones'] = DesbloqueoSocio.objects.filter(
        Q(socio=socio) & _filtro_anio_asistencia('asistencia__', anio)
    ).count()
    return resumen


def obtener_resumen_anual_asistencia_socio(socio, anio):
    """Devuelve el resumen anual de asistencia usado por consulta publica y reportes."""
    resumen = obtener_resumen_asistencia_socio(socio, anio=anio)
    resumen['anio'] = anio
    return resumen


def obtener_historial_asistencia_socio(socio, anio=None):
    """Devuelve el historial de asistencia de un socio, opcionalmente por ano."""
    return AsistenciaReunion.objects.filter(
        Q(socio=socio) & _filtro_anio_asistencia('', anio)
    ).select_related(
        'reunion',
        'registrada_por',
        'justificacion',
    ).order_by(
        '-reunion__fecha',
        '-reunion__hora',
        '-fecha_registro',
        '-pk',
    )


def anotar_resumen_asistencia_socios(socios, anio=None):
    """Agrega contadores de asistencia al queryset en una consulta agrupada."""
    filtro_anio = _filtro_anio_asistencia('asistencias_reunion__', anio)
    filtro_justificaciones_anio = _filtro_anio_asistencia(
        'desbloqueos_asistencia__asistencia__',
        anio,
    )
    return socios.annotate(
        total_reuniones=Count(
            'asistencias_reunion',
            filter=filtro_anio,
            distinct=True,
        ),
        total_asistencias=Count(
            'asistencias_reunion',
            filter=(
                Q(asistencias_reunion__estado=AsistenciaReunion.PRESENTE)
                & filtro_anio
            ),
            distinct=True,
        ),
        total_ausencias=Count(
            'asistencias_reunion',
            filter=(
                Q(asistencias_reunion__estado=AsistenciaReunion.AUSENTE)
                & filtro_anio
            ),
            distinct=True,
        ),
        total_justificaciones=Count(
            'desbloqueos_asistencia',
            filter=filtro_justificaciones_anio,
            distinct=True,
        ),
        total_ausencias_efectivas=Count(
            'asistencias_reunion',
            filter=(
                Q(
                    asistencias_reunion__estado=AsistenciaReunion.AUSENTE,
                    asistencias_reunion__justificacion__isnull=True,
                )
                & filtro_anio
            ),
            distinct=True,
        ),
    )


def agregar_resumen_asistencia_socios(socios, anio=None):
    """Agrega indicadores derivados de contadores de asistencia anotados."""
    socios_resumidos = []
    for socio in socios:
        if not hasattr(socio, 'total_reuniones'):
            resumen = obtener_resumen_asistencia_socio(socio, anio=anio)
            socio.total_reuniones = resumen['total_reuniones']
            socio.total_asistencias = resumen['total_asistencias']
            socio.total_ausencias = resumen['total_ausencias']
            socio.total_ausencias_efectivas = resumen['total_ausencias_efectivas']
            socio.total_justificaciones = resumen['total_justificaciones']
        if not hasattr(socio, 'total_ausencias_efectivas'):
            socio.total_ausencias_efectivas = AsistenciaReunion.objects.filter(
                Q(socio=socio)
                & Q(estado=AsistenciaReunion.AUSENTE)
                & Q(justificacion__isnull=True)
                & _filtro_anio_asistencia('', anio)
            ).count()
        if not hasattr(socio, 'total_justificaciones'):
            socio.total_justificaciones = DesbloqueoSocio.objects.filter(
                Q(socio=socio) & _filtro_anio_asistencia('asistencia__', anio)
            ).count()
        socio.indicador_asistencia = obtener_indicador_asistencia(
            socio.total_ausencias_efectivas,
        )
        socio.puede_eliminar_seguro = not resumen_tiene_asistencias_contabilizadas(
            {
                'total_reuniones': socio.total_reuniones,
                'total_asistencias': socio.total_asistencias,
                'total_ausencias': socio.total_ausencias,
            }
        )
        socios_resumidos.append(socio)
    return socios_resumidos


def filtrar_socios_por_indicador_asistencia(socios, indicador):
    """Filtra un queryset anotado segun el indicador visual de asistencia."""
    if indicador == 'sin_ausencias':
        return socios.filter(total_ausencias_efectivas__lte=0)
    if indicador == 'una_inasistencia':
        return socios.filter(total_ausencias_efectivas=1)
    if indicador == 'bloqueado':
        return socios.filter(
            total_ausencias_efectivas__gte=AsistenciaReunion.INASISTENCIAS_PARA_BLOQUEO
        )
    return socios


def resumen_tiene_asistencias_contabilizadas(resumen):
    """Indica si el socio ya tiene historial operativo que impide eliminarlo."""
    return any(
        resumen[campo] > 0
        for campo in ('total_reuniones', 'total_asistencias', 'total_ausencias')
    )


def puede_eliminar_socio_seguro(socio):
    """Permite eliminar solo socios sin asistencias, reuniones ni ausencias registradas."""
    if socio.rol != Usuario.SOCIO:
        return False
    return not resumen_tiene_asistencias_contabilizadas(
        obtener_resumen_asistencia_socio(socio)
    )


def obtener_indicador_asistencia(total_ausencias):
    """Calcula el indicador visual segun la cantidad de ausencias efectivas."""
    if total_ausencias >= 2:
        return {
            'key': 'bloqueado',
            'label': 'Bloqueado',
            'badge_class': 'text-bg-danger',
        }
    if total_ausencias == 1:
        return {
            'key': 'una_inasistencia',
            'label': 'Una inasistencia',
            'badge_class': 'text-bg-warning',
        }
    return {
        'key': 'sin_ausencias',
        'label': 'Sin ausencias',
        'badge_class': 'text-bg-success',
    }


def obtener_proxima_reunion(referencia=None):
    """Obtiene la reunion programada mas cercana desde la fecha y hora actual."""
    if referencia is None:
        referencia = timezone.localtime()
    elif timezone.is_aware(referencia):
        referencia = timezone.localtime(referencia)

    return Reunion.objects.filter(
        estado=Reunion.PROGRAMADA,
    ).filter(
        Q(fecha__gt=referencia.date())
        | Q(fecha=referencia.date(), hora__gte=referencia.time())
    ).order_by(
        'fecha',
        'hora',
        'fecha_creacion',
        'pk',
    ).first()
