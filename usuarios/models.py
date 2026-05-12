from django.contrib.auth.models import AbstractUser, UserManager
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models


class UsuarioManager(UserManager):
    """Manager que separa superusuarios del rol administrativo web."""

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        """Crea superusuarios con el rol reservado para el admin de Django."""
        extra_fields.setdefault('rol', self.model.SUPERADMINISTRADOR)
        return super().create_superuser(username, email, password, **extra_fields)


def normalizar_rut(rut):
    """Normaliza el RUT al formato cuerpo-digito, sin puntos."""
    valor = ''.join(
        caracter
        for caracter in (rut or '').upper()
        if caracter not in '.-' and not caracter.isspace()
    )
    if len(valor) <= 1:
        return valor
    return f'{valor[:-1]}-{valor[-1]}'


TELEFONO_MOVIL_PREFIJO_CHILE = '+56'
TELEFONO_MOVIL_REGEX_CHILE = r'^\+56\d{9}$'
TELEFONO_MOVIL_MENSAJE_CHILE = (
    'Ingrese un teléfono móvil chileno con formato +56 seguido de 9 dígitos.'
)


def normalizar_telefono_movil(telefono):
    """Normaliza el teléfono móvil chileno al formato +56 y 9 dígitos."""
    valor = (telefono or '').strip()
    if not valor:
        return ''

    separadores = {' ', '\t', '\r', '\n', '-', '(', ')'}
    compacto = ''.join(caracter for caracter in valor if caracter not in separadores)
    if compacto == TELEFONO_MOVIL_PREFIJO_CHILE:
        return ''
    if compacto.startswith('56') and not compacto.startswith(TELEFONO_MOVIL_PREFIJO_CHILE):
        compacto = f'+{compacto}'
    return compacto


class Usuario(AbstractUser):
    """Usuario principal del sistema con RUT, correo único y rol operativo."""

    ADMINISTRADOR = 'ADMINISTRADOR'
    ENCARGADO_REGISTRO = 'ENCARGADO_REGISTRO'
    SUPERADMINISTRADOR = 'SUPERADMINISTRADOR'
    SOCIO = 'SOCIO'

    ROLES = [
        (ADMINISTRADOR, 'Administrador'),
        (ENCARGADO_REGISTRO, 'Encargado de registro'),
        (SUPERADMINISTRADOR, 'Superadministrador Django'),
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
                message='Ingrese un RUT válido.',
            )
        ],
        verbose_name='RUT',
    )
    email = models.EmailField(unique=True, verbose_name='Correo electrónico')
    telefono_movil = models.CharField(
        max_length=12,
        blank=True,
        verbose_name='Teléfono móvil',
        validators=[
            RegexValidator(
                regex=TELEFONO_MOVIL_REGEX_CHILE,
                message=TELEFONO_MOVIL_MENSAJE_CHILE,
            )
        ],
    )
    rol = models.CharField(max_length=20, choices=ROLES, default=SOCIO)

    objects = UsuarioManager()

    REQUIRED_FIELDS = ['email', 'first_name', 'last_name', 'rut']

    class Meta:
        """Orden y nombres legibles del modelo en Django."""

        ordering = ['last_name', 'first_name', 'username']
        verbose_name = 'usuario'
        verbose_name_plural = 'usuarios'
        constraints = [
            models.CheckConstraint(
                condition=(
                    ~models.Q(rol='SOCIO')
                    | (models.Q(is_staff=False) & models.Q(is_superuser=False))
                ),
                name='usuario_socio_sin_privilegios_admin',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(is_superuser=False)
                    | models.Q(rol='SUPERADMINISTRADOR')
                ),
                name='usuario_superuser_rol_superadmin',
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(rol='SUPERADMINISTRADOR')
                    | models.Q(is_superuser=True)
                ),
                name='usuario_rol_superadmin_requiere_superuser',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(is_staff=False)
                    | models.Q(is_superuser=True)
                ),
                name='usuario_staff_requiere_superuser',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(is_superuser=False)
                    | models.Q(is_staff=True)
                ),
                name='usuario_superuser_requiere_staff',
            ),
        ]

    @property
    def nombre_completo(self):
        """Devuelve el nombre completo o el username cuando no hay nombres cargados."""
        return self.get_full_name() or self.username

    def clean_fields(self, exclude=None):
        """Normaliza campos antes de ejecutar validadores de modelo."""
        self.telefono_movil = normalizar_telefono_movil(self.telefono_movil)
        super().clean_fields(exclude=exclude)

    def clean(self):
        """Valida invariantes de rol que no deben depender solo de formularios."""
        super().clean()
        self.email = (self.email or '').strip().lower()
        self.rut = normalizar_rut(self.rut)

        errores = {}
        if self.rol == self.SOCIO and (self.is_staff or self.is_superuser):
            errores['rol'] = 'Un socio no puede tener permisos administrativos.'
        if self.is_superuser and self.rol != self.SUPERADMINISTRADOR:
            errores['rol'] = 'Un superadministrador de Django debe usar el rol reservado.'
        if self.rol == self.SUPERADMINISTRADOR and not self.is_superuser:
            errores['rol'] = 'El rol superadministrador solo puede usarse con superusuarios.'
        if self.is_staff and not self.is_superuser:
            errores['is_staff'] = 'Solo los superadministradores pueden tener acceso staff.'
        if self.is_superuser and not self.is_staff:
            errores['is_staff'] = 'Un superadministrador debe tener acceso staff.'

        if self.pk:
            rol_original = (
                type(self).objects.filter(pk=self.pk).values_list('rol', flat=True).first()
            )
            if rol_original == self.SOCIO and self.rol != self.SOCIO:
                errores['rol'] = 'Un socio no puede cambiar a un rol interno.'
            elif rol_original != self.SOCIO and self.rol == self.SOCIO:
                errores['rol'] = 'Usa el formulario de registro de socios.'

        if errores:
            raise ValidationError(errores)

    def save(self, *args, **kwargs):
        """Normaliza email y RUT antes de persistir el usuario."""
        self.email = (self.email or '').strip().lower()
        self.rut = normalizar_rut(self.rut)
        self.telefono_movil = normalizar_telefono_movil(self.telefono_movil)
        self.full_clean()
        super().save(*args, **kwargs)
