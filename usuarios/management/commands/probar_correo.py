from smtplib import SMTPException

from django.conf import settings
from django.core.mail import BadHeaderError, send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    """Envia un correo de prueba usando la configuracion SMTP activa."""

    help = 'Prueba la configuracion de correo sin imprimir credenciales.'

    def add_arguments(self, parser):
        parser.add_argument(
            'destinatario',
            help='Correo que recibira el mensaje de prueba.',
        )
        parser.add_argument(
            '--asunto',
            default='Prueba de correo - Sistema San Ramon',
            help='Asunto del mensaje de prueba.',
        )

    def handle(self, *args, **options):
        destinatario = options['destinatario']
        asunto = options['asunto']

        self.stdout.write('Configuracion SMTP activa:')
        self.stdout.write(f'  EMAIL_BACKEND={settings.EMAIL_BACKEND}')
        self.stdout.write(f'  EMAIL_HOST={settings.EMAIL_HOST}')
        self.stdout.write(f'  EMAIL_PORT={settings.EMAIL_PORT}')
        self.stdout.write(f'  EMAIL_USE_TLS={settings.EMAIL_USE_TLS}')
        self.stdout.write(f'  EMAIL_USE_SSL={settings.EMAIL_USE_SSL}')
        self.stdout.write(f'  EMAIL_HOST_USER={self._enmascarar(settings.EMAIL_HOST_USER)}')
        self.stdout.write(f'  DEFAULT_FROM_EMAIL={self._enmascarar_from(settings.DEFAULT_FROM_EMAIL)}')

        try:
            enviados = send_mail(
                asunto,
                (
                    'Este es un correo de prueba enviado desde la configuracion '
                    'SMTP activa del Sistema San Ramon.'
                ),
                None,
                [destinatario],
                fail_silently=False,
            )
        except (BadHeaderError, OSError, SMTPException) as exc:
            raise CommandError(
                f'Fallo el envio SMTP: {exc.__class__.__name__}: {exc}'
            ) from exc

        if enviados != 1:
            raise CommandError(f'Django informo {enviados} correos enviados.')

        self.stdout.write(self.style.SUCCESS('Correo de prueba enviado correctamente.'))

    def _enmascarar(self, valor):
        if not valor:
            return '<vacio>'
        if '@' not in valor:
            return '<definido>'
        nombre, dominio = valor.split('@', 1)
        prefijo = nombre[:2] if len(nombre) > 2 else nombre[:1]
        return f'{prefijo}***@{dominio}'

    def _enmascarar_from(self, valor):
        if '<' not in valor or '>' not in valor:
            return self._enmascarar(valor)
        inicio = valor.find('<')
        fin = valor.find('>', inicio)
        if fin == -1:
            return '<definido>'
        return f'{valor[:inicio + 1]}{self._enmascarar(valor[inicio + 1:fin])}>'
