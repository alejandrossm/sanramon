"""Constantes de permisos y grupos operativos del modulo de usuarios."""

APP_LABEL_USUARIOS = 'usuarios'

ROL_ADMINISTRADOR = 'ADMINISTRADOR'
ROL_ENCARGADO_REGISTRO = 'ENCARGADO_REGISTRO'
ROL_SUPERADMINISTRADOR = 'SUPERADMINISTRADOR'
ROL_SOCIO = 'SOCIO'

PERM_GESTIONAR_USUARIOS = 'gestionar_usuarios'
PERM_REGISTRAR_USUARIOS = 'registrar_usuarios'
PERM_REGISTRAR_SOCIOS = 'registrar_socios'
PERM_EDITAR_SOCIOS = 'editar_socios'
PERM_ACCEDER_ASISTENCIA = 'acceder_asistencia'
PERM_ELIMINAR_USUARIOS = 'eliminar_usuarios'
PERM_ELIMINAR_SOCIOS = 'eliminar_socios'
PERM_ADMINISTRAR_PRIVILEGIOS = 'administrar_privilegios'

PERMISOS_USUARIO = (
    (PERM_GESTIONAR_USUARIOS, 'Puede gestionar usuarios internos'),
    (PERM_REGISTRAR_USUARIOS, 'Puede registrar usuarios internos'),
    (PERM_REGISTRAR_SOCIOS, 'Puede registrar socios'),
    (PERM_EDITAR_SOCIOS, 'Puede editar socios'),
    (PERM_ACCEDER_ASISTENCIA, 'Puede acceder al modulo de asistencia'),
    (PERM_ELIMINAR_USUARIOS, 'Puede eliminar usuarios internos'),
    (PERM_ELIMINAR_SOCIOS, 'Puede eliminar socios'),
    (PERM_ADMINISTRAR_PRIVILEGIOS, 'Puede administrar privilegios'),
)

GRUPO_ADMINISTRADOR = 'Administrador'
GRUPO_ENCARGADO_REGISTRO = 'Encargado de registro'
GRUPO_SOCIO = 'Socio'

GRUPO_POR_ROL = {
    ROL_ADMINISTRADOR: GRUPO_ADMINISTRADOR,
    ROL_ENCARGADO_REGISTRO: GRUPO_ENCARGADO_REGISTRO,
    ROL_SOCIO: GRUPO_SOCIO,
}

ROLES_INTERNOS_GESTIONABLES = tuple(
    rol
    for rol in GRUPO_POR_ROL
    if rol != ROL_SOCIO
)
GRUPOS_OPERATIVOS = tuple(GRUPO_POR_ROL.values())

PERMISOS_ADMINISTRADOR = tuple(codename for codename, _label in PERMISOS_USUARIO)
PERMISOS_ENCARGADO_REGISTRO = (PERM_ACCEDER_ASISTENCIA,)
PERMISOS_SOCIO = ()

PERMISOS_POR_GRUPO = {
    GRUPO_ADMINISTRADOR: PERMISOS_ADMINISTRADOR,
    GRUPO_ENCARGADO_REGISTRO: PERMISOS_ENCARGADO_REGISTRO,
    GRUPO_SOCIO: PERMISOS_SOCIO,
}


def permiso_usuario(codename):
    """Devuelve el permiso completo usado por user.has_perm."""
    return f'{APP_LABEL_USUARIOS}.{codename}'


def rol_es_socio(rol):
    """Indica si el rol corresponde al perfil de socio."""
    return rol == ROL_SOCIO


def rol_es_superadministrador(rol):
    """Indica si el rol esta reservado al admin tecnico de Django."""
    return rol == ROL_SUPERADMINISTRADOR


def rol_es_interno_gestionable(rol):
    """Indica si el rol corresponde a una cuenta interna gestionable."""
    return rol in ROLES_INTERNOS_GESTIONABLES


def filtrar_choices_por_roles(choices, roles_permitidos):
    """Filtra choices de rol conservando solo los roles permitidos."""
    roles_permitidos = set(roles_permitidos)
    return [
        choice
        for choice in choices
        if choice[0] in roles_permitidos
    ]


def usuario_es_socio(user):
    """Indica si el usuario pertenece al portal de socio."""
    return bool(
        user
        and user.is_authenticated
        and rol_es_socio(getattr(user, 'rol', None))
        and not user.is_superuser
    )


def usuario_tiene_permiso(user, codename):
    """Evalua permisos operativos bloqueando privilegios accidentales en socios."""
    if not user or not user.is_authenticated or usuario_es_socio(user):
        return False
    return user.has_perm(permiso_usuario(codename))
