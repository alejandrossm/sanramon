from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST

from .forms import LoginForm, UsuarioCreationForm, UsuarioUpdateForm
from .models import Usuario


def es_administrador(user):
    return user.is_authenticated and (
        user.is_superuser or getattr(user, 'rol', None) == Usuario.ADMINISTRADOR
    )


def administrador_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if es_administrador(request.user):
            return view_func(request, *args, **kwargs)
        messages.error(request, 'No tienes permisos para administrar usuarios.')
        return redirect('usuarios:dashboard')

    return wrapper


class UsuarioLoginView(LoginView):
    authentication_form = LoginForm
    template_name = 'usuarios/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse_lazy('usuarios:dashboard')


class UsuarioLogoutView(LogoutView):
    next_page = reverse_lazy('usuarios:login')


@login_required
def dashboard(request):
    return render(
        request,
        'usuarios/dashboard.html',
        {'puede_gestionar_usuarios': es_administrador(request.user)},
    )


@administrador_required
def listado_usuarios(request):
    usuarios = Usuario.objects.all()
    return render(request, 'usuarios/listado_usuarios.html', {'usuarios': usuarios})


@administrador_required
def registro_usuario(request):
    if request.method == 'POST':
        form = UsuarioCreationForm(request.POST)
        if form.is_valid():
            usuario = form.save()
            messages.success(request, f'Usuario {usuario.username} creado correctamente.')
            return redirect('usuarios:listado_usuarios')
    else:
        form = UsuarioCreationForm()

    return render(request, 'usuarios/registro_usuario.html', {'form': form})


@administrador_required
def editar_usuario(request, pk):
    usuario = get_object_or_404(Usuario, pk=pk)
    if request.method == 'POST':
        form = UsuarioUpdateForm(request.POST, instance=usuario)
        if form.is_valid():
            usuario_editado = form.save(commit=False)
            if usuario_editado.pk == request.user.pk and not usuario_editado.is_active:
                messages.error(request, 'No puedes desactivar tu propio usuario.')
            else:
                usuario_editado.save()
                messages.success(request, 'Usuario actualizado correctamente.')
                return redirect('usuarios:listado_usuarios')
    else:
        form = UsuarioUpdateForm(instance=usuario)

    return render(
        request,
        'usuarios/editar_usuario.html',
        {'form': form, 'usuario_obj': usuario},
    )


@require_POST
@administrador_required
def cambiar_estado_usuario(request, pk):
    usuario = get_object_or_404(Usuario, pk=pk)
    if usuario.pk == request.user.pk and usuario.is_active:
        messages.error(request, 'No puedes desactivar tu propio usuario.')
        return redirect('usuarios:listado_usuarios')

    usuario.is_active = not usuario.is_active
    usuario.save(update_fields=['is_active'])

    estado = 'activado' if usuario.is_active else 'desactivado'
    messages.success(request, f'Usuario {usuario.username} {estado} correctamente.')
    return redirect('usuarios:listado_usuarios')
