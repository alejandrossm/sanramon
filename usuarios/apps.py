from django.apps import AppConfig


class UsuariosConfig(AppConfig):
    """Configuracion de la aplicacion de autenticacion y usuarios."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'usuarios'
