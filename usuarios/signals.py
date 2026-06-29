"""Senales de sesion para reconocer un login reciente."""

from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from .seguridad import marcar_reautenticacion


@receiver(user_logged_in)
def registrar_login_reciente(sender, request, user, **kwargs):
    """Considera el login correcto como reautenticacion inicial."""
    if request is not None:
        marcar_reautenticacion(request)
