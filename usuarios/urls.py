from django.urls import path

from . import views

app_name = 'usuarios'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('login/', views.UsuarioLoginView.as_view(), name='login'),
    path('logout/', views.UsuarioLogoutView.as_view(), name='logout'),
    path('mis-asistencias/', views.mis_asistencias, name='mis_asistencias'),
    path('mi-contrasena/', views.cambiar_mi_password, name='cambiar_mi_password'),
    path('usuarios/', views.listado_usuarios, name='listado_usuarios'),
    path('usuarios/registrar/', views.registro_usuario, name='registro_usuario'),
    path('usuarios/<int:pk>/editar/', views.editar_usuario, name='editar_usuario'),
    path('usuarios/<int:pk>/estado/', views.cambiar_estado_usuario, name='cambiar_estado_usuario'),
]
