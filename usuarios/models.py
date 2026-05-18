from django.conf import settings
from django.contrib.auth.models import AbstractUser, UserManager
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models, transaction
from django.utils import timezone

from .identificacion import normalizar_rut
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
    finalizada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.PROTECT,
        related_name='reuniones_finalizadas',
    )
    fecha_finalizacion = models.DateTimeField(blank=True, null=True)
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

    @transaction.atomic
    def finalizar(self, usuario):
        """Finaliza una reunion activa marcando ausentes automaticamente."""
        if not self.puede_finalizarse():
            raise ValidationError({'estado': 'Solo se pueden finalizar reuniones activas.'})

        socios_con_asistencia = self.asistencias.values('socio_id')
        socios_ausentes = Usuario.objects.filter(
            rol=Usuario.SOCIO,
            is_active=True,
        ).exclude(pk__in=socios_con_asistencia)
        ausencias = [
            AsistenciaReunion(
                reunion=self,
                socio=socio,
                estado=AsistenciaReunion.AUSENTE,
                origen=AsistenciaReunion.ORIGEN_AUTOMATICO,
                registrada_por=usuario,
            )
            for socio in socios_ausentes
        ]

        for ausencia in ausencias:
            ausencia.full_clean()

        AsistenciaReunion.objects.bulk_create(ausencias)

        self.estado = self.FINALIZADA
        self.finalizada_por = usuario
        self.fecha_finalizacion = timezone.now()
        self.save(update_fields=['estado', 'finalizada_por', 'fecha_finalizacion'])

        return {
            'ausencias_creadas': len(ausencias),
            'inasistencias_anuales': AsistenciaReunion.obtener_inasistencias_anuales(
                self.fecha.year,
            ),
        }

    def tiene_datos_registrados(self):
        """Indica si la reunion ya tiene asistencia registrada."""
        return self.asistencias.exists()

    def puede_eliminarse(self):
        """Las reuniones historicas se eliminan solo si no tienen datos registrados."""
        if self.es_historica():
            return not self.tiene_datos_registrados()
        return True


class AsistenciaReunion(models.Model):
    """Registro de asistencia de un socio en una reunion."""

    PRESENTE = 'PRESENTE'
    AUSENTE = 'AUSENTE'

    ESTADOS = [
        (PRESENTE, 'Presente'),
        (AUSENTE, 'Ausente'),
    ]

    ORIGEN_RUT = 'RUT'
    ORIGEN_QR = 'QR'
    ORIGEN_MANUAL = 'MANUAL'
    ORIGEN_AUTOMATICO = 'AUTOMATICO'

    ORIGENES = [
        (ORIGEN_RUT, 'RUT'),
        (ORIGEN_QR, 'QR'),
        (ORIGEN_MANUAL, 'Manual'),
        (ORIGEN_AUTOMATICO, 'Automatico'),
    ]

    reunion = models.ForeignKey(
        Reunion,
        on_delete=models.PROTECT,
        related_name='asistencias',
    )
    socio = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='asistencias_reunion',
    )
    estado = models.CharField(max_length=10, choices=ESTADOS, default=PRESENTE)
    origen = models.CharField(max_length=10, choices=ORIGENES)
    registrada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.PROTECT,
        related_name='asistencias_registradas',
    )
    fecha_registro = models.DateTimeField(default=timezone.now)

    class Meta:
        """Orden e invariantes del registro de asistencia."""

        ordering = ['-fecha_registro']
        verbose_name = 'asistencia de reunion'
        verbose_name_plural = 'asistencias de reuniones'
        constraints = [
            models.UniqueConstraint(
                fields=['reunion', 'socio'],
                name='asistencia_unica_por_socio_reunion',
            ),
        ]

    def __str__(self):
        """Representa la asistencia por reunion y socio."""
        return f'{self.reunion} - {self.socio.nombre_completo}'

    def clean(self):
        """Valida que la asistencia corresponda a un socio valido."""
        super().clean()
        errores = {}

        if self.socio_id and self.socio.rol != Usuario.SOCIO:
            errores['socio'] = 'Solo se pueden registrar socios.'

        if self.estado == self.PRESENTE and self.socio_id and not self.socio.is_active:
            errores['socio'] = 'El socio esta inactivo.'

        if errores:
            raise ValidationError(errores)

    def save(self, *args, **kwargs):
        """Valida la asistencia antes de persistirla."""
        self.full_clean()
        super().save(*args, **kwargs)

    @classmethod
    def obtener_inasistencias_anuales(cls, anio):
        """Cuenta ausencias de socios por ano de reunion para bloqueo futuro."""
        return {
            item['socio']: item['total']
            for item in cls.objects.filter(
                estado=cls.AUSENTE,
                reunion__fecha__year=anio,
                socio__rol=Usuario.SOCIO,
            ).values('socio').annotate(total=models.Count('id'))
        }

    @classmethod
    def registrar_presente(cls, reunion, socio, usuario, origen):
        """Registra un socio presente en una reunion activa."""
        if reunion.estado != Reunion.ACTIVA:
            raise ValidationError({'reunion': 'Solo se puede registrar asistencia en una reunion activa.'})

        if socio.rol != Usuario.SOCIO:
            raise ValidationError({'socio': 'Solo se pueden registrar socios existentes.'})

        if not socio.is_active:
            raise ValidationError({'socio': 'El socio esta inactivo.'})

        if cls.objects.filter(reunion=reunion, socio=socio).exists():
            raise ValidationError({'socio': 'El socio ya tiene asistencia registrada en esta reunion.'})

        return cls.objects.create(
            reunion=reunion,
            socio=socio,
            estado=cls.PRESENTE,
            origen=origen,
            registrada_por=usuario,
        )
