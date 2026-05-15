from django.urls import path

from . import views

app_name = 'usuarios'

urlpatterns = [
    path('', views.dashboard, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('login/', views.UsuarioLoginView.as_view(), name='login'),
    path('logout/', views.UsuarioLogoutView.as_view(), name='logout'),
    path(
        'recuperar-contrasena/',
        views.UsuarioPasswordResetView.as_view(),
        name='password_reset',
    ),
    path(
        'recuperar-contrasena/enviado/',
        views.UsuarioPasswordResetDoneView.as_view(),
        name='password_reset_done',
    ),
    path(
        'recuperar-contrasena/<uidb64>/<token>/',
        views.UsuarioPasswordResetConfirmView.as_view(),
        name='password_reset_confirm',
    ),
    path(
        'recuperar-contrasena/completo/',
        views.UsuarioPasswordResetCompleteView.as_view(),
        name='password_reset_complete',
    ),
    path('mis-asistencias/', views.mis_asistencias, name='mis_asistencias'),
    path('asistencia/', views.listado_socios_asistencia, name='listado_socios_asistencia'),
    path('reuniones/', views.listado_reuniones, name='listado_reuniones'),
    path('reuniones/crear/', views.crear_reunion, name='crear_reunion'),
    path(
        'reuniones/limpiar-pruebas/',
        views.limpiar_reuniones_prueba,
        name='limpiar_reuniones_prueba',
    ),
    path('reuniones/<int:pk>/iniciar/', views.iniciar_reunion, name='iniciar_reunion'),
    path(
        'reuniones/<int:pk>/asistencia/',
        views.registrar_asistencia_reunion,
        name='registrar_asistencia_reunion',
    ),
    path('socios/', views.listado_socios, name='listado_socios'),
    path('registrar_socio/', views.registro_socio, name='registro_socio'),
    path('socios/<int:pk>/editar/', views.editar_socio, name='editar_socio'),
    path('socios/<int:pk>/eliminar/', views.eliminar_socio, name='eliminar_socio'),
    path('mi-contrasena/', views.cambiar_mi_password, name='cambiar_mi_password'),
    path('usuarios/', views.listado_usuarios, name='listado_usuarios'),
    path('registrar_usuario/', views.registro_usuario, name='registro_usuario'),
    path('usuarios/<int:pk>/editar/', views.editar_usuario, name='editar_usuario'),
    path('usuarios/<int:pk>/estado/', views.cambiar_estado_usuario, name='cambiar_estado_usuario'),
    path('usuarios/<int:pk>/eliminar/', views.eliminar_usuario, name='eliminar_usuario'),
]
