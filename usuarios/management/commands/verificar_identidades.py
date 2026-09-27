from collections import defaultdict

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    """Comprueba la unicidad de identidades dentro de cada ámbito."""

    help = (
        'Verifica, sin mostrar datos personales, usernames globales y correos '
        'únicos dentro de los ámbitos interno y socio.'
    )

    def handle(self, *args, **options):
        """Falla si un identificador normalizado pertenece a mas de una cuenta."""
        User = get_user_model()
        usernames = defaultdict(set)
        identificadores_por_ambito = defaultdict(set)
        total_usuarios = 0

        for usuario in User.objects.only('pk', 'username', 'email', 'rol').iterator():
            total_usuarios += 1
            username = (usuario.username or '').strip().casefold()
            if username:
                usernames[username].add(usuario.pk)

            ambito = 'socio' if usuario.rol == User.SOCIO else 'interno'
            for valor in (usuario.username, usuario.email):
                identificador = (valor or '').strip().casefold()
                if identificador:
                    identificadores_por_ambito[(ambito, identificador)].add(
                        usuario.pk
                    )

        conflictos_username = sum(
            1
            for usuarios_ids in usernames.values()
            if len(usuarios_ids) > 1
        )
        conflictos_ambito = sum(
            1
            for usuarios_ids in identificadores_por_ambito.values()
            if len(usuarios_ids) > 1
        )
        conflictos = conflictos_username + conflictos_ambito
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
