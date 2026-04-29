from functools import wraps

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST

from .forms import (
    CambioPasswordForm,
    LoginForm,
    SocioCreationForm,
    SocioUpdateForm,
    UsuarioCreationForm,
    UsuarioUpdateForm,
)
from .models import Usuario


def es_administrador(user):
    """Determina si el usuario tiene privilegios administrativos completos."""
    return user.is_authenticated and (
        user.is_superuser or getattr(user, 'rol', None) == Usuario.ADMINISTRADOR
    )


def es_encargado_registro(user):
    """Determina si el usuario tiene rol operativo de encargado de registro."""
    return (
        user.is_authenticated
        and getattr(user, 'rol', None) == Usuario.ENCARGADO_REGISTRO
        and not user.is_superuser
    )


def es_socio(user):
    """Determina si el usuario debe quedar limitado al portal de socio."""
    return (
        user.is_authenticated
        and getattr(user, 'rol', None) == Usuario.SOCIO
        and not es_administrador(user)
    )


def puede_gestionar_usuarios(user):
    """Indica si el usuario puede administrar usuarios sin restricciones."""
    return es_administrador(user)


def puede_registrar_usuarios(user):
    """Indica si el usuario puede registrar cuentas internas."""
    return es_administrador(user)


def puede_registrar_socios(user):
    """Indica si el usuario puede registrar cuentas de socio."""
    return es_administrador(user)


def puede_editar_socios(user):
    """Indica si el usuario puede actualizar datos operativos de socios."""
    return es_administrador(user)


def puede_acceder_asistencia(user):
    """Indica si el usuario puede entrar al modulo operativo de asistencia."""
    return es_administrador(user) or es_encargado_registro(user)


def puede_modificar_usuario(actor, usuario):
    """Valida si el actor puede editar o cambiar estado del usuario objetivo."""
    return es_administrador(actor)


def redireccion_sin_permiso(user):
    """Envia al usuario a la vista permitida cuando intenta acceder sin permisos."""
    if es_socio(user):
        return redirect('usuarios:mis_asistencias')
    return redirect('usuarios:dashboard')


def gestor_usuarios_required(view_func):
    """Protege vistas de gestion completa para administradores."""

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


def asistencia_required(view_func):
    """Protege vistas operativas de asistencia para administradores y encargados."""

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
    """Vista de cierre de sesion que vuelve al login."""

    next_page = reverse_lazy('usuarios:login')


@login_required
def dashboard(request):
    """Muestra el panel principal para roles internos y redirige socios."""
    if es_socio(request.user):
        return redirect('usuarios:mis_asistencias')

    usuarios = Usuario.objects.all()
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
            'usuarios_barra_porcentaje': 100 if total_usuarios else 0,
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
    socios = agregar_resumen_asistencia_socios(socios)

    return render(
        request,
        'usuarios/listado_socios_asistencia.html',
        {
            'socios': socios,
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
        socio.total_reuniones = 0
        socio.total_asistencias = 0
        socio.total_ausencias = 0
        socio.indicador_asistencia = obtener_indicador_asistencia(socio.total_ausencias)
        socios_resumidos.append(socio)
    return socios_resumidos


def obtener_indicador_asistencia(total_ausencias):
    """Calcula el indicador visual segun la cantidad de ausencias."""
    if total_ausencias >= 2:
        return {
            'label': 'Bloqueado',
            'badge_class': 'text-bg-danger',
        }
    if total_ausencias == 1:
        return {
            'label': 'Una inasistencia',
            'badge_class': 'text-bg-warning',
        }
    return {
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
def listado_usuarios(request):
    """Lista usuarios visibles segun el nivel de privilegio del actor."""
    usuarios = Usuario.objects.all()
    if not es_administrador(request.user):
        usuarios = usuarios.exclude(is_superuser=True).exclude(rol=Usuario.ADMINISTRADOR)
    return render(
        request,
        'usuarios/listado_usuarios.html',
        {
            'usuarios': usuarios,
            'puede_administrar_privilegios': es_administrador(request.user),
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
            return redirect('usuarios:listado_socios_asistencia')
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
            return redirect('usuarios:listado_socios_asistencia')
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
    return redirect('usuarios:listado_usuarios')
