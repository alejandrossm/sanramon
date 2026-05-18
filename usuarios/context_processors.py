"""Contexto global de permisos para navegacion y componentes compartidos."""

from .permisos import (
    PERM_ACCEDER_ASISTENCIA,
    PERM_GESTIONAR_USUARIOS,
    PERM_REGISTRAR_SOCIOS,
    PERM_REGISTRAR_USUARIOS,
    usuario_es_socio,
    usuario_tiene_permiso,
)


def permisos_navegacion(request):
    """Expone permisos de navegacion sin acoplar templates a roles internos."""
    user = getattr(request, 'user', None)
    return {
        'nav_usuario_es_socio': usuario_es_socio(user),
        'nav_puede_gestionar_usuarios': usuario_tiene_permiso(
            user,
            PERM_GESTIONAR_USUARIOS,
        ),
        'nav_puede_registrar_usuarios': usuario_tiene_permiso(
            user,
            PERM_REGISTRAR_USUARIOS,
        ),
        'nav_puede_registrar_socios': usuario_tiene_permiso(
            user,
            PERM_REGISTRAR_SOCIOS,
        ),
        'nav_puede_acceder_asistencia': usuario_tiene_permiso(
            user,
            PERM_ACCEDER_ASISTENCIA,
        ),
    }
