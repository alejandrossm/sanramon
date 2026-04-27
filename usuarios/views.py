from functools import wraps

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST

from .forms import CambioPasswordForm, LoginForm, UsuarioCreationForm, UsuarioUpdateForm
from .models import Usuario


def es_administrador(user):
    return user.is_authenticated and (
        user.is_superuser or getattr(user, 'rol', None) == Usuario.ADMINISTRADOR
    )


def es_encargado_registro(user):
    return (
        user.is_authenticated
        and getattr(user, 'rol', None) == Usuario.ENCARGADO_REGISTRO
        and not user.is_superuser
    )


def es_socio(user):
    return (
        user.is_authenticated
        and getattr(user, 'rol', None) == Usuario.SOCIO
        and not es_administrador(user)
    )


def puede_gestionar_usuarios(user):
    return es_administrador(user) or es_encargado_registro(user)


def puede_modificar_usuario(actor, usuario):
    if es_administrador(actor):
        return True
    if not es_encargado_registro(actor):
        return False
    return not usuario.is_superuser and usuario.rol != Usuario.ADMINISTRADOR


def redireccion_sin_permiso(user):
    if es_socio(user):
        return redirect('usuarios:mis_asistencias')
    return redirect('usuarios:dashboard')


def gestor_usuarios_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if puede_gestionar_usuarios(request.user):
            return view_func(request, *args, **kwargs)
        messages.error(request, 'No tienes permisos para administrar usuarios.')
        return redireccion_sin_permiso(request.user)

    return wrapper


class UsuarioLoginView(LoginView):
    authentication_form = LoginForm
    template_name = 'usuarios/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        if es_socio(self.request.user):
            return reverse_lazy('usuarios:mis_asistencias')
        return reverse_lazy('usuarios:dashboard')


class UsuarioLogoutView(LogoutView):
    next_page = reverse_lazy('usuarios:login')


@login_required
def dashboard(request):
    if es_socio(request.user):
        return redirect('usuarios:mis_asistencias')
    return render(
        request,
        'usuarios/dashboard.html',
        {
            'puede_gestionar_usuarios': puede_gestionar_usuarios(request.user),
            'puede_administrar_privilegios': es_administrador(request.user),
        },
    )


@login_required
def mis_asistencias(request):
    if not es_socio(request.user):
        messages.error(request, 'Esta vista solo esta disponible para socios.')
        return redirect('usuarios:dashboard')
    return render(request, 'usuarios/mis_asistencias.html')


@login_required
def cambiar_mi_password(request):
    if request.method == 'POST':
        form = CambioPasswordForm(user=request.user, data=request.POST)
        if form.is_valid():
            form.save()
            update_session_auth_hash(request, request.user)
            messages.success(request, 'Contrasena actualizada correctamente.')
            if es_socio(request.user):
                return redirect('usuarios:mis_asistencias')
            return redirect('usuarios:dashboard')
    else:
        form = CambioPasswordForm(user=request.user)

    return render(request, 'usuarios/cambiar_mi_password.html', {'form': form})


@gestor_usuarios_required
def listado_usuarios(request):
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


@gestor_usuarios_required
def registro_usuario(request):
    if request.method == 'POST':
        form = UsuarioCreationForm(request.POST, actor=request.user)
        if form.is_valid():
            usuario = form.save()
            messages.success(request, f'Usuario {usuario.username} creado correctamente.')
            return redirect('usuarios:listado_usuarios')
    else:
        form = UsuarioCreationForm(actor=request.user)

    return render(request, 'usuarios/registro_usuario.html', {'form': form})


@gestor_usuarios_required
def editar_usuario(request, pk):
    usuario = get_object_or_404(Usuario, pk=pk)
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


@require_POST
@gestor_usuarios_required
def cambiar_estado_usuario(request, pk):
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
