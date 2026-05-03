from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """Carga encargados de prueba para validar paginacion sin validar modelos."""

    help = (
        'Crea o actualiza encargados de prueba para paginacion usando carga directa, '
        'sin ejecutar save(), full_clean() ni hashing de contrasenas.'
    )

    def add_arguments(self, parser):
        """Permite ajustar la cantidad de encargados de prueba."""
        parser.add_argument(
            '--cantidad',
            type=int,
            default=100,
            help='Cantidad de encargados de paginacion a crear o actualizar.',
        )

    def handle(self, *args, **options):
        """Crea o actualiza encargados usando operaciones bulk directas."""
        cantidad = options['cantidad']
        if cantidad < 1:
            self.stderr.write(self.style.ERROR('La cantidad debe ser mayor a 0.'))
            return

        User = get_user_model()
        usernames = [
            f'encargado_paginacion_{indice:03d}'
            for indice in range(1, cantidad + 1)
        ]
        existentes = {
            usuario.username: usuario
            for usuario in User.objects.filter(username__in=usernames)
        }
        nuevos = []
        actualizados = []

        for indice, username in enumerate(usernames, start=1):
            datos = {
                'email': f'encargado.paginacion.{indice:03d}@example.com',
                'first_name': 'Encargado',
                'last_name': f'Paginacion {indice:03d}',
                'rut': f'90.001.{indice:03d}-{indice % 10}',
                'rol': User.ENCARGADO_REGISTRO,
                'is_active': True,
                'is_staff': False,
                'is_superuser': False,
                'password': f'!{username}',
            }
            usuario = existentes.get(username)
            if usuario is None:
                nuevos.append(User(username=username, **datos))
                continue

            for campo, valor in datos.items():
                setattr(usuario, campo, valor)
            actualizados.append(usuario)

        if nuevos:
            User.objects.bulk_create(nuevos)
        if actualizados:
            User.objects.bulk_update(
                actualizados,
                [
                    'email',
                    'first_name',
                    'last_name',
                    'rut',
                    'rol',
                    'is_active',
                    'is_staff',
                    'is_superuser',
                    'password',
                ],
            )

        total_internos = User.objects.exclude(rol=User.SOCIO).count()
        self.stdout.write(
            self.style.SUCCESS(
                f'Encargados creados: {len(nuevos)}; '
                f'actualizados: {len(actualizados)}; '
                f'total internos: {total_internos}'
            )
        )
