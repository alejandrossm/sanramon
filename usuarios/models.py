from django.conf import settings
from django.contrib.auth.models import AbstractUser, UserManager
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

from .permisos import (
    GRUPO_POR_ROL,
    GRUPOS_OPERATIVOS,
    PERMISOS_USUARIO,
    ROL_ADMINISTRADOR,
    ROL_ENCARGADO_REGISTRO,
    ROL_SOCIO,
    ROL_SUPERADMINISTRADOR,
)


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

    ADMINISTRADOR = ROL_ADMINISTRADOR
    ENCARGADO_REGISTRO = ROL_ENCARGADO_REGISTRO
    SUPERADMINISTRADOR = ROL_SUPERADMINISTRADOR
    SOCIO = ROL_SOCIO

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
        permissions = PERMISOS_USUARIO
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
            usuario_original = (
                type(self).objects
                .filter(pk=self.pk)
                .values('rol', 'username')
                .first()
            )
            rol_original = usuario_original['rol'] if usuario_original else None
            username_original = usuario_original['username'] if usuario_original else None
            if username_original and self.username != username_original:
                errores['username'] = 'El nombre de usuario no puede modificarse.'
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
        self.sincronizar_grupo_operativo()

    def sincronizar_grupo_operativo(self):
        """Mantiene el grupo Django equivalente al rol operativo actual."""
        if not self.pk:
            return

        from django.contrib.auth.models import Group

        grupos = list(Group.objects.filter(name__in=GRUPOS_OPERATIVOS))
        if not grupos:
            return

        grupo_destino = GRUPO_POR_ROL.get(self.rol)
        grupos_por_nombre = {grupo.name: grupo for grupo in grupos}
        grupos_a_remover = [
            grupo
            for grupo in grupos
            if grupo.name != grupo_destino
        ]
        if grupos_a_remover:
            self.groups.remove(*grupos_a_remover)

        if grupo_destino and grupo_destino in grupos_por_nombre:
            self.groups.add(grupos_por_nombre[grupo_destino])


class Reunion(models.Model):
    """Reunion programada para gestionar asistencia de socios."""

    PROGRAMADA = 'PROGRAMADA'
    ACTIVA = 'ACTIVA'
    FINALIZADA = 'FINALIZADA'
    CANCELADA = 'CANCELADA'
    HISTORICA = 'HISTORICA'

    ESTADOS = [
        (PROGRAMADA, 'Programada'),
        (ACTIVA, 'Activa'),
        (FINALIZADA, 'Finalizada'),
        (CANCELADA, 'Cancelada'),
        (HISTORICA, 'Histórica'),
    ]

    fecha = models.DateField()
    hora = models.TimeField()
    locacion = models.CharField(max_length=150)
    creador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='reuniones_creadas',
    )
    estado = models.CharField(max_length=12, choices=ESTADOS, default=PROGRAMADA)
    es_proxima = models.BooleanField(default=False)
    activada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.PROTECT,
        related_name='reuniones_activadas',
    )
    fecha_activacion = models.DateTimeField(blank=True, null=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Orden y nombres legibles del modelo en Django."""

        ordering = ['-fecha', '-hora', '-fecha_creacion']
        verbose_name = 'reunión'
        verbose_name_plural = 'reuniones'
        constraints = [
            models.UniqueConstraint(
                fields=['estado'],
                condition=models.Q(estado='ACTIVA'),
                name='solo_una_reunion_activa',
            ),
        ]

    def __str__(self):
        """Representa la reunion por fecha, hora y locacion."""
        return f'{self.fecha} {self.hora:%H:%M} - {self.locacion}'

    def clean(self):
        """Normaliza datos minimos antes de guardar."""
        super().clean()
        self.locacion = (self.locacion or '').strip()
        if not self.locacion:
            raise ValidationError({'locacion': 'La locación es obligatoria.'})

    def save(self, *args, **kwargs):
        """Valida la reunion antes de persistirla."""
        self.full_clean()
        super().save(*args, **kwargs)

    def es_historica(self):
        """Indica si la reunion corresponde a carga historica posterior."""
        return self.estado == self.HISTORICA

    def puede_iniciarse(self):
        """Solo las reuniones programadas pueden pasar a activa."""
        return self.estado == self.PROGRAMADA

    def iniciar(self, usuario):
        """Activa una reunion programada y registra el responsable."""
        if not self.puede_iniciarse():
            raise ValidationError({'estado': 'Solo se pueden iniciar reuniones programadas.'})

        if type(self).objects.filter(estado=self.ACTIVA).exclude(pk=self.pk).exists():
            raise ValidationError({'estado': 'Ya existe una reunion activa.'})

        self.estado = self.ACTIVA
        self.activada_por = usuario
        self.fecha_activacion = timezone.now()
        self.save(update_fields=['estado', 'activada_por', 'fecha_activacion'])

    def puede_finalizarse(self):
        """Solo las reuniones activas pueden finalizarse."""
        return self.estado == self.ACTIVA

    def tiene_datos_registrados(self):
        """Punto de extension para asistencias cuando exista el modelo asociado."""
        return False

    def puede_eliminarse(self):
        """Las reuniones historicas se eliminan solo si no tienen datos registrados."""
        if self.es_historica():
            return not self.tiene_datos_registrados()
        return True
