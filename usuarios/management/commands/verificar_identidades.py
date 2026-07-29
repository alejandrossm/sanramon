from collections import defaultdict

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    """Comprueba que cada identificador de login pertenezca a una sola cuenta."""

    help = (
        'Verifica, sin mostrar datos personales, que username y email no '
        'colisionen entre cuentas diferentes.'
    )

    def handle(self, *args, **options):
        """Falla si un identificador normalizado pertenece a mas de una cuenta."""
        User = get_user_model()
        propietarios = defaultdict(set)
        total_usuarios = 0

        for usuario in User.objects.only('pk', 'username', 'email').iterator():
            total_usuarios += 1
            for valor in (usuario.username, usuario.email):
                identificador = (valor or '').strip().casefold()
                if identificador:
                    propietarios[identificador].add(usuario.pk)

        conflictos = sum(
            1
            for usuarios_ids in propietarios.values()
            if len(usuarios_ids) > 1
        )
        if conflictos:
            raise CommandError(
                'Se detectaron '
                f'{conflictos} identificadores asociados a cuentas diferentes. '
                'Corrige las colisiones antes de desplegar.'
            )

        self.stdout.write(
            self.style.SUCCESS(
                f'Identidades verificadas: {total_usuarios} usuarios, sin colisiones.'
            )
        )
