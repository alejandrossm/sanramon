from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from usuarios.identificacion import calcular_digito_verificador_rut


def construir_rut_demo(cuerpo):
    """Construye RUT demo con digito verificador valido."""
    cuerpo = str(cuerpo)
    return f'{cuerpo}-{calcular_digito_verificador_rut(cuerpo)}'


class Command(BaseCommand):
    """Comando idempotente para preparar usuarios demo de desarrollo."""

    help = 'Crea o actualiza usuarios de prueba para desarrollo local.'

    usuarios = [
        {
            'username': 'admin_demo',
            'email': 'admin.demo@example.com',
            'first_name': 'Admin',
            'last_name': 'Demo',
            'rut': construir_rut_demo('91111111'),
            'rol': 'ADMINISTRADOR',
            'is_staff': False,
            'is_superuser': False,
        },
        {
            'username': 'encargado_demo',
            'email': 'encargado.demo@example.com',
            'first_name': 'Encargado',
            'last_name': 'Demo',
            'rut': construir_rut_demo('92222222'),
            'rol': 'ENCARGADO_REGISTRO',
            'is_staff': False,
            'is_superuser': False,
        },
        {
            'username': 'socio_demo',
            'email': 'socio.demo@example.com',
            'first_name': 'Socio',
            'last_name': 'Demo',
            'rut': construir_rut_demo('93333333'),
            'rol': 'SOCIO',
            'is_staff': False,
            'is_superuser': False,
        },
    ]

    def handle(self, *args, **options):
        """Crea o actualiza usuarios demo con acceso solo para roles internos."""
        User = get_user_model()

        for datos in self.usuarios:
            username = datos['username']
            usuario = User.objects.filter(username=username).first()
            creado = usuario is None
            if creado:
                usuario = User(username=username)
            for campo, valor in datos.items():
                setattr(usuario, campo, valor)
            usuario.is_active = True
            if usuario.rol == User.SOCIO:
                usuario.set_unusable_password()
            else:
                usuario.set_password(username)
            usuario.save()

            accion = 'creado' if creado else 'actualizado'
            credencial = 'sin contrasena de acceso'
            if usuario.has_usable_password():
                credencial = username
            self.stdout.write(
                self.style.SUCCESS(
                    f"Usuario {username} {accion}: {datos['email']} / {credencial}"
                )
            )
