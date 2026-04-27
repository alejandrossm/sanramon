from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """Comando idempotente para preparar usuarios demo de desarrollo."""

    help = 'Crea o actualiza usuarios de prueba para desarrollo local.'

    usuarios = [
        {
            'username': 'admin_demo',
            'email': 'admin.demo@example.com',
            'first_name': 'Admin',
            'last_name': 'Demo',
            'rut': '91.111.111-1',
            'rol': 'ADMINISTRADOR',
            'is_staff': True,
            'is_superuser': False,
        },
        {
            'username': 'encargado_demo',
            'email': 'encargado.demo@example.com',
            'first_name': 'Encargado',
            'last_name': 'Demo',
            'rut': '92.222.222-2',
            'rol': 'ENCARGADO_REGISTRO',
            'is_staff': False,
            'is_superuser': False,
        },
        {
            'username': 'socio_demo',
            'email': 'socio.demo@example.com',
            'first_name': 'Socio',
            'last_name': 'Demo',
            'rut': '93.333.333-3',
            'rol': 'SOCIO',
            'is_staff': False,
            'is_superuser': False,
        },
    ]

    def handle(self, *args, **options):
        """Crea o actualiza usuarios demo usando username como contraseña."""
        User = get_user_model()

        for datos in self.usuarios:
            username = datos['username']
            usuario, creado = User.objects.get_or_create(username=username)
            for campo, valor in datos.items():
                setattr(usuario, campo, valor)
            usuario.is_active = True
            usuario.set_password(username)
            usuario.save()

            accion = 'creado' if creado else 'actualizado'
            self.stdout.write(
                self.style.SUCCESS(
                    f"Usuario {username} {accion}: {datos['email']} / {username}"
                )
            )
