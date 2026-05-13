from functools import wraps

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import (
    LoginView,
    LogoutView,
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST

from .forms import (
    CambioPasswordForm,
    LoginForm,
    RecuperarPasswordForm,
    ReunionCreationForm,
    RestablecerPasswordForm,
    SocioCreationForm,
    SocioUpdateForm,
    UsuarioCreationForm,
    UsuarioUpdateForm,
)
from .models import Usuario
from .permisos import (
    PERM_ACCEDER_ASISTENCIA,
    PERM_ADMINISTRAR_PRIVILEGIOS,
    PERM_EDITAR_SOCIOS,
    PERM_ELIMINAR_SOCIOS,
    PERM_ELIMINAR_USUARIOS,
    PERM_GESTIONAR_USUARIOS,
    PERM_REGISTRAR_SOCIOS,
    PERM_REGISTRAR_USUARIOS,
    ROLES_INTERNOS_GESTIONABLES,
    filtrar_choices_por_roles,
    rol_es_interno_gestionable,
    usuario_es_socio,
    usuario_tiene_permiso,
)


def es_administrador(user):
    """Determina si el usuario tiene privilegios administrativos completos."""
    return usuario_tiene_permiso(user, PERM_ADMINISTRAR_PRIVILEGIOS)


def es_socio(user):
    """Determina si el usuario debe quedar limitado al portal de socio."""
    return usuario_es_socio(user)


def puede_gestionar_usuarios(user):
    """Indica si el usuario puede administrar usuarios sin restricciones."""
    return usuario_tiene_permiso(user, PERM_GESTIONAR_USUARIOS)


def puede_registrar_usuarios(user):
    """Indica si el usuario puede registrar cuentas internas."""
    return usuario_tiene_permiso(user, PERM_REGISTRAR_USUARIOS)


def puede_registrar_socios(user):
    """Indica si el usuario puede registrar cuentas de socio."""
    return usuario_tiene_permiso(user, PERM_REGISTRAR_SOCIOS)


def puede_editar_socios(user):
    """Indica si el usuario puede actualizar datos operativos de socios."""
    return usuario_tiene_permiso(user, PERM_EDITAR_SOCIOS)


def puede_acceder_asistencia(user):
    """Indica si el usuario puede entrar al modulo operativo de asistencia."""
    return usuario_tiene_permiso(user, PERM_ACCEDER_ASISTENCIA)


def puede_modificar_usuario(actor, usuario):
    """Valida si el actor puede editar o cambiar estado del usuario objetivo."""
    return puede_gestionar_usuarios(actor) and not usuario.is_superuser


def puede_eliminar_socios(user):
    """Indica si el usuario puede eliminar socios."""
    return usuario_tiene_permiso(user, PERM_ELIMINAR_SOCIOS)


def puede_eliminar_usuario_interno(actor, usuario):
    """Valida eliminacion de usuarios internos desde gestion propia."""
    if (
        not usuario_tiene_permiso(actor, PERM_ELIMINAR_USUARIOS)
        or usuario.pk == actor.pk
        or usuario.is_superuser
    ):
        return False
    return rol_es_interno_gestionable(usuario.rol)


def obtener_valores_busqueda_rut(valor):
    """Genera variantes de busqueda para RUT con o sin puntos y guion."""
    valor = (valor or '').strip()
    sin_puntos = valor.replace('.', '').replace(' ', '').upper()
    solo_rut = ''.join(caracter for caracter in sin_puntos if caracter.isdigit() or caracter == 'K')
    variantes = [valor, sin_puntos]
    if '-' not in sin_puntos and len(solo_rut) > 1:
        variantes.append(f'{solo_rut[:-1]}-{solo_rut[-1]}')
    return [variante for variante in dict.fromkeys(variantes) if variante]


COLUMNAS_ORDENABLES_USUARIOS = [
    {'key': 'usuario', 'label': 'Usuario', 'field': 'username'},
    {'key': 'nombre', 'label': 'Nombre', 'field': 'first_name'},
    {'key': 'apellido', 'label': 'Apellido', 'field': 'last_name'},
    {'key': 'rut', 'label': 'RUT', 'field': 'rut'},
    {'key': 'email', 'label': 'Email', 'field': 'email'},
    {'key': 'telefono', 'label': 'Teléfono', 'field': 'telefono_movil'},
    {'key': 'rol', 'label': 'Rol', 'field': 'rol'},
    {'key': 'estado', 'label': 'Estado', 'field': 'is_active'},
]

COLUMNAS_ORDENABLES_SOCIOS = [
    {'key': 'rut', 'label': 'RUT', 'field': 'rut'},
    {'key': 'nombre', 'label': 'Nombre', 'field': 'first_name'},
    {'key': 'apellido', 'label': 'Apellido', 'field': 'last_name'},
    {'key': 'email', 'label': 'Email', 'field': 'email'},
    {'key': 'telefono', 'label': 'Teléfono', 'field': 'telefono_movil'},
    {'key': 'estado', 'label': 'Estado', 'field': 'is_active'},
]


ROLES_FILTRABLES_USUARIOS = filtrar_choices_por_roles(
    Usuario.ROLES,
    ROLES_INTERNOS_GESTIONABLES,
)

ESTADOS_FILTRABLES = [
    ('activo', 'Activo'),
    ('inactivo', 'Inactivo'),
]

INDICADORES_FILTRABLES_ASISTENCIA = [
    ('sin_ausencias', 'Sin ausencias'),
    ('una_inasistencia', 'Una inasistencia'),
    ('bloqueado', 'Bloqueado'),
]


def obtener_columnas_ordenables(params, orden_actual, direccion_actual, columnas_base):
    """Construye metadatos de ordenamiento conservando filtros activos."""
    columnas = []
    base_params = params.copy()
    if 'page' in base_params:
        del base_params['page']

    for columna in columnas_base:
        asc_params = base_params.copy()
        asc_params['orden'] = columna['key']
        asc_params['direccion'] = 'asc'

        desc_params = base_params.copy()
        desc_params['orden'] = columna['key']
        desc_params['direccion'] = 'desc'

        columnas.append(
            {
                **columna,
                'asc_query': asc_params.urlencode(),
                'desc_query': desc_params.urlencode(),
                'asc_active': (
                    orden_actual == columna['key'] and direccion_actual == 'asc'
                ),
                'desc_active': (
                    orden_actual == columna['key'] and direccion_actual == 'desc'
                ),
            }
        )

    return columnas


def obtener_columnas_ordenables_usuarios(params, orden_actual, direccion_actual):
    """Construye metadatos de ordenamiento para usuarios internos."""
    return obtener_columnas_ordenables(
        params,
        orden_actual,
        direccion_actual,
        COLUMNAS_ORDENABLES_USUARIOS,
    )


def obtener_columnas_ordenables_socios(params, orden_actual, direccion_actual):
    """Construye metadatos de ordenamiento para socios."""
    return obtener_columnas_ordenables(
        params,
        orden_actual,
        direccion_actual,
        COLUMNAS_ORDENABLES_SOCIOS,
    )


def aplicar_filtros_orden_socios(request, socios, columnas_ordenables):
    """Aplica filtros y ordenamiento comun para listados de socios."""
    campos_ordenables = {
        columna['key']: columna['field']
        for columna in columnas_ordenables
    }
    orden_actual = request.GET.get('orden', '').strip()
    direccion_actual = request.GET.get('direccion', '').strip().lower()
    if orden_actual not in campos_ordenables:
        orden_actual = ''
    if direccion_actual not in ('asc', 'desc'):
        direccion_actual = 'asc'

    filtros = {
        'rut': request.GET.get('rut', '').strip(),
        'nombre': request.GET.get('nombre', '').strip(),
        'apellido': request.GET.get('apellido', '').strip(),
        'estado': request.GET.get('estado', '').strip(),
    }
    estados_permitidos = {estado for estado, _label in ESTADOS_FILTRABLES}
    if filtros['estado'] not in estados_permitidos:
        filtros['estado'] = ''

    if filtros['rut']:
        filtro_rut = Q()
        for valor_rut in obtener_valores_busqueda_rut(filtros['rut']):
            filtro_rut |= Q(rut__icontains=valor_rut)
        socios = socios.filter(filtro_rut)
    if filtros['nombre']:
        socios = socios.filter(first_name__icontains=filtros['nombre'])
    if filtros['apellido']:
        socios = socios.filter(last_name__icontains=filtros['apellido'])
    if filtros['estado']:
        socios = socios.filter(is_active=filtros['estado'] == 'activo')

    if orden_actual:
        campo_base = campos_ordenables[orden_actual]
        campo_orden = campo_base
        if direccion_actual == 'desc':
            campo_orden = f'-{campo_base}'
        campos_secundarios = [
            campo
            for campo in ('last_name', 'first_name', 'username', 'pk')
            if campo != campo_base
        ]
        socios = socios.order_by(campo_orden, *campos_secundarios)

    return {
        'socios': socios,
        'filtros': filtros,
        'filtros_activos': any(filtros.values()),
        'orden_actual': orden_actual,
        'direccion_actual': direccion_actual,
    }


def redireccion_sin_permiso(user):
    """Envia al usuario a la vista permitida cuando intenta acceder sin permisos."""
    if es_socio(user):
        return redirect('usuarios:mis_asistencias')
    return redirect('usuarios:dashboard')


def obtener_resumen_estado_asistencia_socios():
    """Resume socios por estado de ausencias para el grafico del dashboard."""
    socios = Usuario.objects.filter(rol=Usuario.SOCIO)
    total_socios = socios.count()
    sin_falta = 0
    en_riesgo = 0
    bloqueados = 0

    for socio in socios:
        resumen = obtener_resumen_asistencia_socio(socio)
        total_ausencias = resumen['total_ausencias']
        if total_ausencias >= 2:
            bloqueados += 1
        elif total_ausencias == 1:
            en_riesgo += 1
        else:
            sin_falta += 1

    barras = [
        {'label': 'Socios totales', 'total': total_socios, 'class': 'is-total'},
        {'label': 'Sin falta', 'total': sin_falta, 'class': 'is-clear'},
        {'label': 'En riesgo', 'total': en_riesgo, 'class': 'is-risk'},
        {
            'label': 'Bloqueados por inasistencia',
            'total': bloqueados,
            'class': 'is-blocked',
        },
    ]
    maximo = max((barra['total'] for barra in barras), default=0)

    for barra in barras:
        barra['percentage'] = round((barra['total'] / maximo) * 100) if maximo else 0

    return {
        'items': barras,
        'total': total_socios,
    }


def gestor_usuarios_required(view_func):
    """Protege vistas de gestión completa para administradores."""

    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        """Ejecuta la vista protegida o redirige con mensaje de error."""
        if puede_gestionar_usuarios(request.user):
            return view_func(request, *args, **kwargs)
        messages.error(request, 'No tienes permisos para administrar usuarios.')
        return redireccion_sin_permiso(request.user)

    return wrapper


def registro_usuarios_required(view_func):
    """Protege el registro de usuarios internos para administradores."""

    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        """Ejecuta el registro o redirige si el rol no esta autorizado."""
        if puede_registrar_usuarios(request.user):
            return view_func(request, *args, **kwargs)
        messages.error(request, 'No tienes permisos para registrar usuarios internos.')
        return redireccion_sin_permiso(request.user)

    return wrapper


def eliminacion_usuarios_required(view_func):
    """Protege la eliminacion de usuarios internos mediante permiso explicito."""

    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        """Ejecuta la eliminacion o redirige si no esta autorizada."""
        if usuario_tiene_permiso(request.user, PERM_ELIMINAR_USUARIOS):
            return view_func(request, *args, **kwargs)
        messages.error(request, 'No tienes permisos para eliminar usuarios.')
        return redireccion_sin_permiso(request.user)

    return wrapper


def registro_socios_required(view_func):
    """Protege el registro de socios solo para administradores."""

    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        """Ejecuta el registro de socios o redirige si el rol no esta autorizado."""
        if puede_registrar_socios(request.user):
            return view_func(request, *args, **kwargs)
        messages.error(request, 'No tienes permisos para registrar socios.')
        return redireccion_sin_permiso(request.user)

    return wrapper


def edicion_socios_required(view_func):
    """Protege la edicion operativa de socios."""

    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        """Ejecuta la edicion de socios o redirige si el rol no esta autorizado."""
        if puede_editar_socios(request.user):
            return view_func(request, *args, **kwargs)
        messages.error(request, 'No tienes permisos para editar socios.')
        return redireccion_sin_permiso(request.user)

    return wrapper


def eliminacion_socios_required(view_func):
    """Protege la eliminacion de socios mediante permiso explicito."""

    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        """Ejecuta la eliminacion o redirige si no esta autorizada."""
        if puede_eliminar_socios(request.user):
            return view_func(request, *args, **kwargs)
        messages.error(request, 'No tienes permisos para eliminar socios.')
        return redireccion_sin_permiso(request.user)

    return wrapper


def asistencia_required(view_func):
    """Protege vistas operativas de asistencia por permiso explicito."""

    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        """Ejecuta la vista de asistencia o redirige al destino permitido."""
        if puede_acceder_asistencia(request.user):
            return view_func(request, *args, **kwargs)
        messages.error(request, 'No tienes permisos para acceder al modulo de asistencia.')
        return redireccion_sin_permiso(request.user)

    return wrapper


class UsuarioLoginView(LoginView):
    """Vista de login con redireccion por rol despues de autenticar."""

    authentication_form = LoginForm
    template_name = 'usuarios/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        """Redirige socios a asistencias y otros roles al dashboard."""
        if es_socio(self.request.user):
            return reverse_lazy('usuarios:mis_asistencias')
        return reverse_lazy('usuarios:dashboard')


class UsuarioLogoutView(LogoutView):
    """Vista de cierre de sesión que vuelve al login."""

    next_page = reverse_lazy('usuarios:login')


class UsuarioPasswordResetView(PasswordResetView):
    """Solicita un enlace de recuperacion de contrasena por correo."""

    form_class = RecuperarPasswordForm
    template_name = 'usuarios/password_reset_form.html'
    email_template_name = 'usuarios/password_reset_email.html'
    subject_template_name = 'usuarios/password_reset_subject.txt'
    success_url = reverse_lazy('usuarios:password_reset_done')


class UsuarioPasswordResetDoneView(PasswordResetDoneView):
    """Confirma que la solicitud de recuperacion fue recibida."""

    template_name = 'usuarios/password_reset_done.html'


class UsuarioPasswordResetConfirmView(PasswordResetConfirmView):
    """Permite guardar una nueva contrasena usando un token valido."""

    form_class = RestablecerPasswordForm
    template_name = 'usuarios/password_reset_confirm.html'
    success_url = reverse_lazy('usuarios:password_reset_complete')


class UsuarioPasswordResetCompleteView(PasswordResetCompleteView):
    """Muestra el resultado final del restablecimiento de contrasena."""

    template_name = 'usuarios/password_reset_complete.html'


@login_required
def dashboard(request):
    """Muestra el panel principal para roles internos y redirige socios."""
    if es_socio(request.user):
        return redirect('usuarios:mis_asistencias')

    estado_asistencia_socios = obtener_resumen_estado_asistencia_socios()
    usuarios = Usuario.objects.filter(is_superuser=False)
    total_usuarios = usuarios.count()
    usuarios_activos = usuarios.filter(is_active=True).count()
    usuarios_inactivos = total_usuarios - usuarios_activos

    return render(
        request,
        'usuarios/dashboard.html',
        {
            'puede_gestionar_usuarios': puede_gestionar_usuarios(request.user),
            'puede_registrar_usuarios': puede_registrar_usuarios(request.user),
            'puede_registrar_socios': puede_registrar_socios(request.user),
            'puede_acceder_asistencia': puede_acceder_asistencia(request.user),
            'puede_administrar_privilegios': es_administrador(request.user),
            'total_usuarios': total_usuarios,
            'usuarios_activos': usuarios_activos,
            'usuarios_inactivos': usuarios_inactivos,
            'usuarios_admin': usuarios.filter(rol=Usuario.ADMINISTRADOR).count(),
            'usuarios_encargados': usuarios.filter(rol=Usuario.ENCARGADO_REGISTRO).count(),
            'usuarios_socios': usuarios.filter(rol=Usuario.SOCIO).count(),
            'estado_asistencia_socios_items': estado_asistencia_socios['items'],
            'estado_asistencia_socios_total': estado_asistencia_socios['total'],
        },
    )


@login_required
def mis_asistencias(request):
    """Muestra al socio su estado actual de asistencia registrada."""
    if not es_socio(request.user):
        messages.error(request, 'Esta vista solo esta disponible para socios.')
        return redirect('usuarios:dashboard')
    return render(request, 'usuarios/mis_asistencias.html')


@asistencia_required
def listado_socios_asistencia(request):
    """Lista socios disponibles para los futuros flujos de asistencia."""
    socios = Usuario.objects.filter(rol=Usuario.SOCIO)
    total_socios = socios.count()
    socios_activos = socios.filter(is_active=True).count()
    consulta = aplicar_filtros_orden_socios(
        request,
        socios,
        COLUMNAS_ORDENABLES_SOCIOS,
    )
    socios = consulta['socios']
    filtros = consulta['filtros'].copy()
    indicador_actual = request.GET.get('indicador', '').strip()
    indicadores_validos = {
        indicador for indicador, _label in INDICADORES_FILTRABLES_ASISTENCIA
    }
    if indicador_actual not in indicadores_validos:
        indicador_actual = ''
    filtros['indicador'] = indicador_actual
    socios_filtrados_por_indicador = bool(indicador_actual)

    if socios_filtrados_por_indicador:
        socios = [
            socio
            for socio in agregar_resumen_asistencia_socios(socios)
            if socio.indicador_asistencia['key'] == indicador_actual
        ]

    paginator = Paginator(socios, 50)
    page_obj = paginator.get_page(request.GET.get('page'))
    if not socios_filtrados_por_indicador:
        page_obj.object_list = agregar_resumen_asistencia_socios(page_obj.object_list)
    pagination_params = request.GET.copy()
    if 'page' in pagination_params:
        del pagination_params['page']

    return render(
        request,
        'usuarios/listado_socios_asistencia.html',
        {
            'socios': page_obj,
            'page_obj': page_obj,
            'page_numbers': paginator.get_elided_page_range(page_obj.number),
            'pagination_ellipsis': Paginator.ELLIPSIS,
            'pagination_query': pagination_params.urlencode(),
            'filtros': filtros,
            'filtros_activos': consulta['filtros_activos'] or socios_filtrados_por_indicador,
            'estados_filtrables': ESTADOS_FILTRABLES,
            'indicadores_filtrables': INDICADORES_FILTRABLES_ASISTENCIA,
            'columnas_ordenables': obtener_columnas_ordenables_socios(
                request.GET,
                consulta['orden_actual'],
                consulta['direccion_actual'],
            ),
            'orden_actual': consulta['orden_actual'],
            'direccion_actual': consulta['direccion_actual'],
            'total_socios': total_socios,
            'socios_activos': socios_activos,
            'socios_inactivos': total_socios - socios_activos,
            'puede_registrar_socios': puede_registrar_socios(request.user),
            'puede_editar_socios': puede_editar_socios(request.user),
        },
    )


def agregar_resumen_asistencia_socios(socios):
    """Agrega contadores base hasta integrar reuniones y asistencias reales."""
    socios_resumidos = []
    for socio in socios:
        resumen = obtener_resumen_asistencia_socio(socio)
        socio.total_reuniones = resumen['total_reuniones']
        socio.total_asistencias = resumen['total_asistencias']
        socio.total_ausencias = resumen['total_ausencias']
        socio.indicador_asistencia = obtener_indicador_asistencia(socio.total_ausencias)
        socio.puede_eliminar_seguro = not resumen_tiene_asistencias_contabilizadas(resumen)
        socios_resumidos.append(socio)
    return socios_resumidos


def obtener_resumen_asistencia_socio(socio):
    """Devuelve los contadores de asistencia usados por vistas y eliminación segura."""
    return {
        'total_reuniones': 0,
        'total_asistencias': 0,
        'total_ausencias': 0,
    }


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
    """Calcula el indicador visual segun la cantidad de ausencias."""
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


@login_required
def cambiar_mi_password(request):
    """Permite al usuario autenticado actualizar su propia contraseña."""
    if request.method == 'POST':
        form = CambioPasswordForm(user=request.user, data=request.POST)
        if form.is_valid():
            form.save()
            update_session_auth_hash(request, request.user)
            messages.success(request, 'Contraseña actualizada correctamente.')
            if es_socio(request.user):
                return redirect('usuarios:mis_asistencias')
            return redirect('usuarios:dashboard')
    else:
        form = CambioPasswordForm(user=request.user)

    return render(request, 'usuarios/cambiar_mi_password.html', {'form': form})


@gestor_usuarios_required
def crear_reunion(request):
    """Crea reuniones con estado inicial programada."""
    if request.method == 'POST':
        form = ReunionCreationForm(request.POST, creador=request.user)
        if form.is_valid():
            reunion = form.save()
            messages.success(
                request,
                f'Reunion del {reunion.fecha:%d-%m-%Y} creada correctamente.',
            )
            return redirect('usuarios:crear_reunion')
    else:
        form = ReunionCreationForm(creador=request.user)

    return render(request, 'usuarios/crear_reunion.html', {'form': form})


@gestor_usuarios_required
def listado_usuarios(request):
    """Lista cuentas internas sin mezclar socios."""
    usuarios = Usuario.objects.exclude(rol=Usuario.SOCIO).filter(is_superuser=False)
    campos_ordenables = {
        columna['key']: columna['field']
        for columna in COLUMNAS_ORDENABLES_USUARIOS
    }
    orden_actual = request.GET.get('orden', '').strip()
    direccion_actual = request.GET.get('direccion', '').strip().lower()
    if orden_actual not in campos_ordenables:
        orden_actual = ''
    if direccion_actual not in ('asc', 'desc'):
        direccion_actual = 'asc'

    filtros = {
        'rut': request.GET.get('rut', '').strip(),
        'nombre': request.GET.get('nombre', '').strip(),
        'apellido': request.GET.get('apellido', '').strip(),
        'rol': request.GET.get('rol', '').strip(),
    }
    roles_permitidos = {rol for rol, _label in ROLES_FILTRABLES_USUARIOS}
    if filtros['rol'] not in roles_permitidos:
        filtros['rol'] = ''

    if filtros['rut']:
        filtro_rut = Q()
        for valor_rut in obtener_valores_busqueda_rut(filtros['rut']):
            filtro_rut |= Q(rut__icontains=valor_rut)
        usuarios = usuarios.filter(filtro_rut)
    if filtros['nombre']:
        usuarios = usuarios.filter(first_name__icontains=filtros['nombre'])
    if filtros['apellido']:
        usuarios = usuarios.filter(last_name__icontains=filtros['apellido'])
    if filtros['rol']:
        usuarios = usuarios.filter(rol=filtros['rol'])

    if orden_actual:
        campo_base = campos_ordenables[orden_actual]
        campo_orden = campo_base
        if direccion_actual == 'desc':
            campo_orden = f'-{campo_base}'
        campos_secundarios = [
            campo
            for campo in ('last_name', 'first_name', 'username', 'pk')
            if campo != campo_base
        ]
        usuarios = usuarios.order_by(campo_orden, *campos_secundarios)

    paginator = Paginator(usuarios, 50)
    page_obj = paginator.get_page(request.GET.get('page'))
    pagination_params = request.GET.copy()
    if 'page' in pagination_params:
        del pagination_params['page']

    return render(
        request,
        'usuarios/listado_usuarios.html',
        {
            'usuarios': page_obj,
            'page_obj': page_obj,
            'page_numbers': paginator.get_elided_page_range(page_obj.number),
            'pagination_ellipsis': Paginator.ELLIPSIS,
            'pagination_query': pagination_params.urlencode(),
            'filtros': filtros,
            'filtros_activos': any(filtros.values()),
            'roles_filtrables': ROLES_FILTRABLES_USUARIOS,
            'columnas_ordenables': obtener_columnas_ordenables_usuarios(
                request.GET,
                orden_actual,
                direccion_actual,
            ),
            'orden_actual': orden_actual,
            'direccion_actual': direccion_actual,
            'puede_administrar_privilegios': es_administrador(request.user),
        },
    )


@gestor_usuarios_required
def listado_socios(request):
    """Lista socios en una vista administrativa separada de usuarios internos."""
    socios = Usuario.objects.filter(rol=Usuario.SOCIO)
    total_socios = socios.count()
    socios_activos = socios.filter(is_active=True).count()
    consulta = aplicar_filtros_orden_socios(
        request,
        socios,
        COLUMNAS_ORDENABLES_SOCIOS,
    )
    socios = consulta['socios']
    paginator = Paginator(socios, 50)
    page_obj = paginator.get_page(request.GET.get('page'))
    page_obj.object_list = agregar_resumen_asistencia_socios(page_obj.object_list)
    pagination_params = request.GET.copy()
    if 'page' in pagination_params:
        del pagination_params['page']

    return render(
        request,
        'usuarios/listado_socios.html',
        {
            'socios': page_obj,
            'page_obj': page_obj,
            'page_numbers': paginator.get_elided_page_range(page_obj.number),
            'pagination_ellipsis': Paginator.ELLIPSIS,
            'pagination_query': pagination_params.urlencode(),
            'filtros': consulta['filtros'],
            'filtros_activos': consulta['filtros_activos'],
            'estados_filtrables': ESTADOS_FILTRABLES,
            'columnas_ordenables': obtener_columnas_ordenables_socios(
                request.GET,
                consulta['orden_actual'],
                consulta['direccion_actual'],
            ),
            'orden_actual': consulta['orden_actual'],
            'direccion_actual': consulta['direccion_actual'],
            'total_socios': total_socios,
            'socios_activos': socios_activos,
            'socios_inactivos': total_socios - socios_activos,
        },
    )


@registro_usuarios_required
def registro_usuario(request):
    """Crea usuarios internos respetando las restricciones de rol del actor."""
    if request.method == 'POST':
        form = UsuarioCreationForm(request.POST, actor=request.user)
        if form.is_valid():
            usuario = form.save()
            messages.success(request, f'Usuario {usuario.username} creado correctamente.')
            return redirect('usuarios:listado_usuarios')
    else:
        form = UsuarioCreationForm(actor=request.user)

    return render(
        request,
        'usuarios/registro_usuario.html',
        {
            'form': form,
        },
    )


@registro_socios_required
def registro_socio(request):
    """Crea socios sin credenciales tradicionales de username y password."""
    if request.method == 'POST':
        form = SocioCreationForm(request.POST)
        if form.is_valid():
            socio = form.save()
            messages.success(request, f'Socio {socio.nombre_completo} creado correctamente.')
            return redirect('usuarios:listado_socios')
    else:
        form = SocioCreationForm()

    return render(request, 'usuarios/registro_socio.html', {'form': form})


@gestor_usuarios_required
def editar_usuario(request, pk):
    """Edita datos, estado y password de un usuario permitido."""
    usuario = get_object_or_404(Usuario, pk=pk)
    if usuario.rol == Usuario.SOCIO:
        return redirect('usuarios:editar_socio', pk=usuario.pk)

    if not puede_modificar_usuario(request.user, usuario):
        messages.error(request, 'No tienes permisos para modificar este usuario.')
        return redirect('usuarios:listado_usuarios')

    if request.method == 'POST':
        form = UsuarioUpdateForm(request.POST, instance=usuario, actor=request.user)
        if form.is_valid():
            usuario_editado = form.save(commit=False)
            if usuario_editado.pk == request.user.pk and not usuario_editado.is_active:
                messages.error(request, 'No puedes desactivar tu propio usuario.')
            else:
                usuario_editado.save()
                messages.success(request, 'Usuario actualizado correctamente.')
                return redirect('usuarios:listado_usuarios')
    else:
        form = UsuarioUpdateForm(instance=usuario, actor=request.user)

    return render(
        request,
        'usuarios/editar_usuario.html',
        {'form': form, 'usuario_obj': usuario},
    )


@edicion_socios_required
def editar_socio(request, pk):
    """Edita datos propios de un socio sin permitir cambiar su perfil."""
    socio = get_object_or_404(Usuario, pk=pk, rol=Usuario.SOCIO)

    if request.method == 'POST':
        form = SocioUpdateForm(request.POST, instance=socio)
        if form.is_valid():
            form.save()
            messages.success(request, 'Socio actualizado correctamente.')
            return redirect('usuarios:listado_socios')
    else:
        form = SocioUpdateForm(instance=socio)

    return render(
        request,
        'usuarios/editar_socio.html',
        {'form': form, 'socio': socio},
    )


@require_POST
@gestor_usuarios_required
def cambiar_estado_usuario(request, pk):
    """Activa o desactiva un usuario permitido desde una peticion POST."""
    usuario = get_object_or_404(Usuario, pk=pk)
    if not puede_modificar_usuario(request.user, usuario):
        messages.error(request, 'No tienes permisos para cambiar el estado de este usuario.')
        return redirect('usuarios:listado_usuarios')

    if usuario.pk == request.user.pk and usuario.is_active:
        messages.error(request, 'No puedes desactivar tu propio usuario.')
        return redirect('usuarios:listado_usuarios')

    usuario.is_active = not usuario.is_active
    usuario.save(update_fields=['is_active'])

    estado = 'activado' if usuario.is_active else 'desactivado'
    messages.success(request, f'Usuario {usuario.username} {estado} correctamente.')
    if usuario.rol == Usuario.SOCIO:
        return redirect('usuarios:listado_socios')
    return redirect('usuarios:listado_usuarios')


@require_POST
@eliminacion_usuarios_required
def eliminar_usuario(request, pk):
    """Elimina usuarios internos sin permitir autoeliminación."""
    usuario = get_object_or_404(Usuario, pk=pk)

    if usuario.pk == request.user.pk:
        messages.error(request, 'No puedes eliminar tu propio usuario.')
        return redirect('usuarios:listado_usuarios')

    if not puede_eliminar_usuario_interno(request.user, usuario):
        messages.error(
            request,
            'Solo se pueden eliminar usuarios internos.',
        )
        return redirect('usuarios:listado_usuarios')

    nombre_usuario = usuario.nombre_completo
    usuario.delete()
    messages.success(request, f'Usuario {nombre_usuario} eliminado correctamente.')
    return redirect('usuarios:listado_usuarios')


@require_POST
@eliminacion_socios_required
def eliminar_socio(request, pk):
    """Elimina socios solo cuando no tienen asistencias contabilizadas."""
    socio = get_object_or_404(Usuario, pk=pk, rol=Usuario.SOCIO)

    if not puede_eliminar_socio_seguro(socio):
        messages.error(
            request,
            'Solo se pueden eliminar socios sin asistencias contabilizadas. '
            'Si el socio ya tiene historial, debes desactivarlo.',
        )
        return redirect('usuarios:listado_socios')

    nombre_socio = socio.nombre_completo
    socio.delete()
    messages.success(request, f'Socio {nombre_socio} eliminado correctamente.')
    return redirect('usuarios:listado_socios')
