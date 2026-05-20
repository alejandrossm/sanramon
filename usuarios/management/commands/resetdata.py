from argparse import ArgumentTypeError

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from usuarios.models import AsistenciaReunion, DesbloqueoSocio, Reunion


class Command(BaseCommand):
    """Borra datos operativos de asistencia para pruebas locales."""

    help = (
        'Borra reuniones, asistencias y justificaciones de inasistencia '
        'para reiniciar pruebas locales sin eliminar usuarios ni socios.'
    )

    def add_arguments(self, parser):
        """Exige confirmacion explicita para evitar ejecuciones accidentales."""
        parser.add_argument(
            '--confirmar',
            '--confirm',
            '--yes',
            '-y',
            nargs='?',
            const=True,
            default=False,
            type=self.parsear_confirmacion,
            help=(
                'Confirma el borrado de reuniones, asistencias y justificaciones. '
                'Acepta --confirmar, --confirmar=true, --yes o -y.'
            ),
        )

    @staticmethod
    def parsear_confirmacion(valor):
        """Acepta variantes comunes de confirmacion por consola."""
        if valor is True:
            return True

        valor_normalizado = str(valor).strip().lower()
        if valor_normalizado in {'1', 'true', 't', 'yes', 'y', 'si', 's'}:
            return True
        if valor_normalizado in {'0', 'false', 'f', 'no', 'n'}:
            return False
        raise ArgumentTypeError(
            'Valor de confirmacion invalido. Usa --confirmar, --confirmar=true, --yes o -y.'
        )

    @transaction.atomic
    def handle(self, *args, **options):
        """Reinicia los datos derivados de reuniones y asistencia."""
        if not settings.DEBUG:
            raise CommandError(
                'Este comando solo puede ejecutarse con DEBUG=True.'
            )

        if not options['confirmar']:
            raise CommandError(
                'Operacion cancelada. Ejecuta con --confirmar para borrar datos de prueba.'
            )

        justificaciones, _detalle_justificaciones = DesbloqueoSocio.objects.all().delete()
        asistencias, _detalle_asistencias = AsistenciaReunion.objects.all().delete()
        reuniones, _detalle_reuniones = Reunion.objects.all().delete()

        self.stdout.write(
            self.style.SUCCESS(
                'Reset de asistencia completado: '
                f'reuniones eliminadas: {reuniones}; '
                f'asistencias eliminadas: {asistencias}; '
                f'justificaciones eliminadas: {justificaciones}.'
            )
        )
