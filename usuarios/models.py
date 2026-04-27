from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models


def normalizar_rut(rut):
    return (rut or '').replace('.', '').replace(' ', '').upper()


class Usuario(AbstractUser):
    ADMINISTRADOR = 'ADMINISTRADOR'
    ENCARGADO_REGISTRO = 'ENCARGADO_REGISTRO'
    SOCIO = 'SOCIO'

    ROLES = [
        (ADMINISTRADOR, 'Administrador'),
        (ENCARGADO_REGISTRO, 'Encargado de registro'),
        (SOCIO, 'Socio'),
    ]

    first_name = models.CharField(max_length=150, verbose_name='Nombre')
    last_name = models.CharField(max_length=150, verbose_name='Apellido')
    rut = models.CharField(
        max_length=12,
        unique=True,
        validators=[
            RegexValidator(
                regex=r'^[0-9kK.\-\s]+$',
                message='Ingrese un RUT valido.',
            )
        ],
        verbose_name='RUT',
    )
    email = models.EmailField(unique=True, verbose_name='Correo electronico')
    rol = models.CharField(max_length=20, choices=ROLES, default=SOCIO)

    REQUIRED_FIELDS = ['email', 'first_name', 'last_name', 'rut']

    class Meta:
        ordering = ['last_name', 'first_name', 'username']
        verbose_name = 'usuario'
        verbose_name_plural = 'usuarios'

    @property
    def nombre_completo(self):
        return self.get_full_name() or self.username

    def save(self, *args, **kwargs):
        self.email = (self.email or '').strip().lower()
        self.rut = normalizar_rut(self.rut)
        super().save(*args, **kwargs)
