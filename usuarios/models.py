import hashlib
import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser, UserManager
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models, transaction
from django.utils import timezone

from .identificacion import MENSAJE_RUT_INVALIDO, normalizar_rut, validar_rut_chileno
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
    last_name = models.CharField(max_length=150, verbose_name='Apellido paterno')
    apellido_materno = models.CharField(
        max_length=150,
        blank=True,
        verbose_name='Apellido materno',
    )
    rut = models.CharField(
        max_length=12,
        unique=True,
        validators=[
            RegexValidator(
                regex=r'^[0-9kK.\-\s]+$',
                message=MENSAJE_RUT_INVALIDO,
            ),
            validar_rut_chileno,
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
    fecha_ingreso_proyecto = models.DateField(
        default=timezone.localdate,
        verbose_name='Fecha de ingreso al proyecto',
    )
    rol = models.CharField(max_length=20, choices=ROLES, default=SOCIO)

    objects = UsuarioManager()

    REQUIRED_FIELDS = ['email', 'first_name', 'last_name', 'rut']

    class Meta:
        """Orden y nombres legibles del modelo en Django."""

        ordering = ['last_name', 'apellido_materno', 'first_name', 'username']
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

    def get_full_name(self):
        """Devuelve nombre con apellido paterno y materno cuando existe."""
        return ' '.join(
            parte
            for parte in (
                (self.first_name or '').strip(),
                (self.last_name or '').strip(),
                (self.apellido_materno or '').strip(),
            )
            if parte
        )

    def clean_fields(self, exclude=None):
        """Normaliza campos antes de ejecutar validadores de modelo."""
        self.telefono_movil = normalizar_telefono_movil(self.telefono_movil)
        super().clean_fields(exclude=exclude)

    def clean(self):
        """Valida invariantes de identidad y rol fuera de los formularios."""
        super().clean()
        self.username = (self.username or '').strip()
        self.email = (self.email or '').strip().lower()
        self.rut = normalizar_rut(self.rut)

        errores = {}
        otros_usuarios = type(self).objects.exclude(pk=self.pk)
        if self.username:
            if otros_usuarios.filter(username__iexact=self.username).exists():
                errores['username'] = (
                    'Ya existe un usuario con este nombre, sin distinguir mayusculas.'
                )
            elif otros_usuarios.filter(email__iexact=self.username).exists():
                errores['username'] = (
                    'El nombre de usuario coincide con el correo de otra cuenta.'
                )
        if self.email:
            if otros_usuarios.filter(email__iexact=self.email).exists():
                errores['email'] = (
                    'Ya existe un usuario con este correo, sin distinguir mayusculas.'
                )
            elif otros_usuarios.filter(username__iexact=self.email).exists():
                errores['email'] = (
                    'El correo coincide con el nombre de usuario de otra cuenta.'
                )

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
        self.username = (self.username or '').strip()
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
    cancelada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.PROTECT,
        related_name='reuniones_canceladas',
    )
    fecha_cancelacion = models.DateTimeField(blank=True, null=True)
    motivo_cancelacion = models.TextField(blank=True)
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

    def puede_cancelarse(self):
        """Solo las reuniones programadas o activas pueden cancelarse."""
        return self.estado in {self.PROGRAMADA, self.ACTIVA}

    @transaction.atomic
    def finalizar(self, usuario):
        """Finaliza una reunion activa marcando ausentes automaticamente."""
        if not self.puede_finalizarse():
            raise ValidationError({'estado': 'Solo se pueden finalizar reuniones activas.'})

        socios_con_asistencia = self.asistencias.values('socio_id')
        socios_ausentes = Usuario.objects.filter(
            rol=Usuario.SOCIO,
            is_active=True,
        ).exclude(pk__in=socios_con_asistencia).annotate(
            total_ausencias_efectivas=models.Count(
                'asistencias_reunion',
                filter=models.Q(
                    asistencias_reunion__estado=AsistenciaReunion.AUSENTE,
                    asistencias_reunion__justificacion__isnull=True,
                ),
                distinct=True,
            ),
        ).filter(
            total_ausencias_efectivas__lt=AsistenciaReunion.INASISTENCIAS_PARA_BLOQUEO
        )
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

    @transaction.atomic
    def cancelar(self, usuario, motivo):
        """Cancela una reunion y elimina sus asistencias para no contabilizarlas."""
        if not self.puede_cancelarse():
            raise ValidationError({'estado': 'Solo se pueden cancelar reuniones programadas o activas.'})

        motivo_normalizado = (motivo or '').strip()
        if not motivo_normalizado:
            raise ValidationError({'motivo_cancelacion': 'El motivo de cancelacion es obligatorio.'})

        asistencias_eliminadas, _detalle = self.asistencias.all().delete()
        self.estado = self.CANCELADA
        self.cancelada_por = usuario
        self.fecha_cancelacion = timezone.now()
        self.motivo_cancelacion = motivo_normalizado
        self.save(
            update_fields=[
                'estado',
                'cancelada_por',
                'fecha_cancelacion',
                'motivo_cancelacion',
            ]
        )

        return {'asistencias_eliminadas': asistencias_eliminadas}

    def tiene_datos_registrados(self):
        """Indica si la reunion ya tiene asistencia registrada."""
        return self.asistencias.exists()

    def puede_eliminarse(self):
        """Permite eliminar reuniones solo si no tienen asistencias registradas."""
        return not self.tiene_datos_registrados()


class CargaAsistenciaHistorica(models.Model):
    """Lote trazable de una carga historica importada desde planilla."""

    reunion = models.ForeignKey(
        Reunion,
        on_delete=models.CASCADE,
        related_name='cargas_historicas',
    )
    cargado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='cargas_asistencia_historica',
    )
    fecha_carga = models.DateTimeField(default=timezone.now)
    archivo_nombre = models.CharField(max_length=255, blank=True)
    total_registros = models.PositiveIntegerField(default=0)
    total_presentes = models.PositiveIntegerField(default=0)
    total_ausentes = models.PositiveIntegerField(default=0)
    revertida = models.BooleanField(default=False)
    revertida_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.PROTECT,
        related_name='reversiones_carga_asistencia_historica',
    )
    fecha_reversion = models.DateTimeField(blank=True, null=True)
    registros_revertidos = models.PositiveIntegerField(default=0)

    class Meta:
        """Orden y nombres legibles del lote de carga historica."""

        ordering = ['-fecha_carga']
        verbose_name = 'carga historica de asistencia'
        verbose_name_plural = 'cargas historicas de asistencia'

    def __str__(self):
        """Representa la carga por reunion y fecha de importacion."""
        return f'Carga #{self.pk} - {self.reunion}'

    def marcar_revertida(self, usuario, registros_revertidos):
        """Registra la reversion del lote."""
        self.revertida = True
        self.revertida_por = usuario
        self.fecha_reversion = timezone.now()
        self.registros_revertidos = registros_revertidos
        self.save(
            update_fields=[
                'revertida',
                'revertida_por',
                'fecha_reversion',
                'registros_revertidos',
            ]
        )


class AsistenciaReunion(models.Model):
    """Registro de asistencia de un socio en una reunion."""

    PRESENTE = 'PRESENTE'
    AUSENTE = 'AUSENTE'
    INASISTENCIAS_PARA_BLOQUEO = 2
    MENSAJE_SOCIO_BLOQUEADO = (
        'El socio esta bloqueado por inasistencias. '
        'Debe tener una inasistencia justificada por un administrador antes de registrar asistencia.'
    )

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
    carga_historica = models.ForeignKey(
        CargaAsistenciaHistorica,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name='asistencias',
    )

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

        if (
            self.estado == self.PRESENTE
            and self.socio_id
            and not self.pk
            and type(self).socio_esta_bloqueado(self.socio)
        ):
            errores['socio'] = self.MENSAJE_SOCIO_BLOQUEADO

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
    def obtener_anio_operativo(cls, anio=None):
        """Normaliza el ano usado por vistas que requieren periodo explicito."""
        return anio or timezone.localdate().year

    @classmethod
    def filtrar_por_anio(cls, queryset, anio=None):
        """Aplica filtro anual solo cuando el llamador lo solicita."""
        if anio is None:
            return queryset
        return queryset.filter(reunion__fecha__year=anio)

    @classmethod
    def contar_inasistencias_socio(cls, socio, anio=None):
        """Cuenta ausencias registradas; si se entrega ano, limita el periodo."""
        queryset = cls.objects.filter(
            socio=socio,
            estado=cls.AUSENTE,
        )
        return cls.filtrar_por_anio(queryset, anio=anio).count()

    @classmethod
    def contar_inasistencias_efectivas_socio(cls, socio, anio=None):
        """Cuenta ausencias sin justificar; si se entrega ano, limita el periodo."""
        return cls.obtener_ausencias_justificables(socio, anio=anio).count()

    @classmethod
    def obtener_firmas_bloqueo_socios(cls, socios_ids, anio=None):
        """Calcula una firma estable del bloqueo vigente para varios socios."""
        queryset = cls.objects.filter(
            socio_id__in=socios_ids,
            estado=cls.AUSENTE,
            justificacion__isnull=True,
        )
        ausencias = cls.filtrar_por_anio(queryset, anio=anio).order_by(
            'socio_id',
            'pk',
        ).values_list('socio_id', 'pk')
        ausencias_por_socio = {}
        for socio_id, asistencia_id in ausencias:
            ausencias_por_socio.setdefault(socio_id, []).append(str(asistencia_id))

        return {
            socio_id: hashlib.sha256(','.join(ids).encode('ascii')).hexdigest()
            for socio_id, ids in ausencias_por_socio.items()
        }

    @classmethod
    def obtener_firma_bloqueo_socio(cls, socio, anio=None):
        """Devuelve la firma del bloqueo vigente de un socio."""
        return cls.obtener_firmas_bloqueo_socios([socio.pk], anio=anio).get(
            socio.pk,
            '',
        )

    @classmethod
    def obtener_ausencias_justificables(cls, socio, anio=None):
        """Lista ausencias del socio pendientes de justificacion."""
        queryset = cls.objects.filter(
            socio=socio,
            estado=cls.AUSENTE,
            justificacion__isnull=True,
        )
        return cls.filtrar_por_anio(queryset, anio=anio).select_related(
            'reunion'
        ).order_by(
            'reunion__fecha',
            'reunion__hora',
            'fecha_registro',
        )

    @classmethod
    def socio_esta_bloqueado(cls, socio, anio=None):
        """Indica si el socio alcanzo el umbral de bloqueo pendiente."""
        return (
            cls.contar_inasistencias_efectivas_socio(socio, anio=anio)
            >= cls.INASISTENCIAS_PARA_BLOQUEO
        )

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

        if cls.socio_esta_bloqueado(socio):
            raise ValidationError({'socio': cls.MENSAJE_SOCIO_BLOQUEADO})

        return cls.objects.create(
            reunion=reunion,
            socio=socio,
            estado=cls.PRESENTE,
            origen=origen,
            registrada_por=usuario,
        )


class DesbloqueoSocio(models.Model):
    """Registro administrativo que justifica una inasistencia de un socio."""

    socio = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='desbloqueos_asistencia',
        verbose_name='socio',
    )
    asistencia = models.OneToOneField(
        AsistenciaReunion,
        on_delete=models.PROTECT,
        related_name='justificacion',
        verbose_name='inasistencia justificada',
    )
    motivo = models.TextField()
    desbloqueado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='desbloqueos_socios_realizados',
        verbose_name='justificado por',
    )
    fecha_desbloqueo = models.DateTimeField(
        'fecha de justificacion',
        default=timezone.now,
    )
    inasistencias_al_desbloquear = models.PositiveIntegerField(
        'inasistencias al justificar',
    )

    class Meta:
        """Orden e invariantes del historial de justificaciones."""

        ordering = ['-fecha_desbloqueo']
        verbose_name = 'justificacion de inasistencia'
        verbose_name_plural = 'justificaciones de inasistencias'

    def __str__(self):
        """Representa la justificacion por socio y fecha."""
        return f'{self.socio.nombre_completo} - {self.fecha_desbloqueo:%d-%m-%Y %H:%M}'

    def clean(self):
        """Valida que la justificacion sea para un socio con motivo real."""
        super().clean()
        errores = {}

        if self.socio_id and self.socio.rol != Usuario.SOCIO:
            errores['socio'] = 'Solo se pueden justificar inasistencias de socios.'

        if self.asistencia_id:
            if self.asistencia.estado != AsistenciaReunion.AUSENTE:
                errores['asistencia'] = 'Solo se pueden justificar ausencias.'
            if self.socio_id and self.asistencia.socio_id != self.socio_id:
                errores['asistencia'] = 'La inasistencia debe pertenecer al socio justificado.'

        self.motivo = (self.motivo or '').strip()
        if not self.motivo:
            errores['motivo'] = 'El motivo de justificacion es obligatorio.'

        if errores:
            raise ValidationError(errores)

    def save(self, *args, **kwargs):
        """Valida la justificacion antes de persistirla."""
        self.full_clean()
        super().save(*args, **kwargs)

    @classmethod
    def registrar(cls, socio, usuario, motivo, asistencia, anio=None):
        """Justifica una inasistencia si el socio esta bloqueado."""
        anio_operativo = int(anio) if anio not in (None, '') else None
        total_inasistencias = AsistenciaReunion.contar_inasistencias_socio(
            socio,
            anio=anio_operativo,
        )
        total_efectivas = AsistenciaReunion.contar_inasistencias_efectivas_socio(
            socio,
            anio=anio_operativo,
        )
        if total_efectivas < AsistenciaReunion.INASISTENCIAS_PARA_BLOQUEO:
            raise ValidationError({'socio': 'El socio no esta bloqueado por inasistencias.'})
        if asistencia is None:
            raise ValidationError({'asistencia': 'Debe seleccionar una inasistencia.'})
        if asistencia.socio_id != socio.pk:
            raise ValidationError({'asistencia': 'La inasistencia debe pertenecer al socio justificado.'})
        if (
            anio_operativo is not None
            and asistencia.reunion.fecha.year != anio_operativo
        ):
            raise ValidationError({'asistencia': 'La inasistencia no pertenece al ano operativo.'})
        if asistencia.estado != AsistenciaReunion.AUSENTE:
            raise ValidationError({'asistencia': 'Solo se pueden justificar ausencias.'})
        if cls.objects.filter(asistencia=asistencia).exists():
            raise ValidationError({'asistencia': 'La inasistencia seleccionada ya fue justificada.'})

        return cls.objects.create(
            socio=socio,
            asistencia=asistencia,
            motivo=motivo,
            desbloqueado_por=usuario,
            fecha_desbloqueo=timezone.now(),
            inasistencias_al_desbloquear=total_inasistencias,
        )


class NotificacionBloqueoSocio(models.Model):
    """Trazabilidad del aviso enviado para un bloqueo puntual por inasistencias."""

    socio = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='notificaciones_bloqueo',
        verbose_name='socio',
    )
    enviada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='notificaciones_bloqueo_enviadas',
        verbose_name='enviada por',
    )
    firma_bloqueo = models.CharField(
        max_length=64,
        verbose_name='firma del bloqueo',
    )
    email_destino = models.EmailField(verbose_name='correo notificado')
    fecha_envio = models.DateTimeField(
        'fecha de notificacion',
        default=timezone.now,
    )
    total_inasistencias_efectivas = models.PositiveIntegerField(
        'inasistencias efectivas notificadas',
    )

    class Meta:
        """Orden e invariantes del historial de notificaciones de bloqueo."""

        ordering = ['-fecha_envio']
        verbose_name = 'notificacion de bloqueo'
        verbose_name_plural = 'notificaciones de bloqueo'
        constraints = [
            models.UniqueConstraint(
                fields=['socio', 'firma_bloqueo'],
                name='notificacion_bloqueo_unica_por_socio_firma',
            ),
        ]

    def __str__(self):
        """Representa el envio por socio y fecha."""
        return f'{self.socio.nombre_completo} - {self.fecha_envio:%d-%m-%Y %H:%M}'

    def clean(self):
        """Valida que la notificacion corresponda a un socio bloqueado real."""
        super().clean()
        errores = {}

        if self.socio_id and self.socio.rol != Usuario.SOCIO:
            errores['socio'] = 'Solo se pueden notificar bloqueos de socios.'

        self.email_destino = (self.email_destino or '').strip().lower()
        if not self.email_destino:
            errores['email_destino'] = 'El correo del socio es obligatorio.'

        if (
            self.total_inasistencias_efectivas
            < AsistenciaReunion.INASISTENCIAS_PARA_BLOQUEO
        ):
            errores['total_inasistencias_efectivas'] = (
                'La notificacion solo aplica a socios bloqueados por inasistencias.'
            )

        if not self.firma_bloqueo:
            errores['firma_bloqueo'] = 'La firma del bloqueo es obligatoria.'

        if errores:
            raise ValidationError(errores)

    def save(self, *args, **kwargs):
        """Valida la notificacion antes de persistirla."""
        self.full_clean()
        super().save(*args, **kwargs)

    @classmethod
    def obtener_firmas_notificadas_socios(cls, socios_ids):
        """Devuelve las firmas ya notificadas para varios socios."""
        return set(
            cls.objects.filter(socio_id__in=socios_ids).values_list(
                'socio_id',
                'firma_bloqueo',
            )
        )

    @classmethod
    def bloqueo_actual_ya_notificado(cls, socio, anio=None):
        """Indica si el bloqueo vigente anual del socio ya fue notificado."""
        if not AsistenciaReunion.socio_esta_bloqueado(socio, anio=anio):
            return False

        firma_bloqueo = AsistenciaReunion.obtener_firma_bloqueo_socio(
            socio,
            anio=anio,
        )
        if not firma_bloqueo:
            return False

        return cls.objects.filter(
            socio=socio,
            firma_bloqueo=firma_bloqueo,
        ).exists()

    @classmethod
    def registrar_bloqueo_actual(cls, socio, usuario, anio=None):
        """Registra la trazabilidad del aviso para el bloqueo vigente anual."""
        total_efectivas = AsistenciaReunion.contar_inasistencias_efectivas_socio(
            socio,
            anio=anio,
        )
        if total_efectivas < AsistenciaReunion.INASISTENCIAS_PARA_BLOQUEO:
            raise ValidationError(
                {'socio': 'El socio no esta bloqueado por inasistencias.'}
            )

        firma_bloqueo = AsistenciaReunion.obtener_firma_bloqueo_socio(
            socio,
            anio=anio,
        )
        if not firma_bloqueo:
            raise ValidationError(
                {'socio': 'No fue posible determinar el bloqueo vigente del socio.'}
            )

        if cls.objects.filter(socio=socio, firma_bloqueo=firma_bloqueo).exists():
            raise ValidationError(
                {
                    'socio': (
                        'La notificacion de bloqueo ya fue enviada '
                        'para el bloqueo actual.'
                    )
                }
            )

        return cls.objects.create(
            socio=socio,
            enviada_por=usuario,
            firma_bloqueo=firma_bloqueo,
            email_destino=socio.email,
            fecha_envio=timezone.now(),
            total_inasistencias_efectivas=total_efectivas,
        )


class SolicitudCodigoConsulta(models.Model):
    """Solicitud efimera para verificar por correo una consulta de asistencia."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    socio = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.CASCADE,
        related_name='solicitudes_codigo_consulta',
    )
    codigo_hash = models.CharField(max_length=64)
    ip_hash = models.CharField(max_length=64, db_index=True)
    fecha_solicitud = models.DateTimeField(default=timezone.now, db_index=True)
    fecha_expiracion = models.DateTimeField()
    intentos_fallidos = models.PositiveSmallIntegerField(default=0)
    fecha_uso = models.DateTimeField(blank=True, null=True)
    email_enviado = models.BooleanField(default=False)

    class Meta:
        """Orden e indices para expiracion y limites de solicitudes."""

        ordering = ['-fecha_solicitud']
        verbose_name = 'solicitud de codigo de consulta'
        verbose_name_plural = 'solicitudes de codigo de consulta'
        indexes = [
            models.Index(
                fields=['ip_hash', 'fecha_solicitud'],
                name='consulta_ip_fecha_idx',
            ),
            models.Index(
                fields=['socio', 'fecha_solicitud'],
                name='consulta_socio_fecha_idx',
            ),
        ]

    def __str__(self):
        """Evita exponer RUT o correo en representaciones administrativas."""
        return f'Solicitud {self.pk}'

    def esta_vigente(self, ahora=None):
        """Indica si el codigo aun puede validarse."""
        ahora = ahora or timezone.now()
        return (
            self.email_enviado
            and self.socio_id is not None
            and self.fecha_uso is None
            and self.fecha_expiracion > ahora
        )


class AceptacionPrivacidadConsulta(models.Model):
    """Evidencia versionada del aviso aceptado para la consulta digital."""

    METODO_EMAIL_OTP = 'EMAIL_OTP'
    METODOS = [
        (METODO_EMAIL_OTP, 'Codigo de un solo uso enviado por correo'),
    ]

    socio = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='aceptaciones_privacidad_consulta',
    )
    version_politica = models.CharField(max_length=20)
    texto_hash = models.CharField(max_length=64)
    metodo_verificacion = models.CharField(max_length=20, choices=METODOS)
    fecha_aceptacion = models.DateTimeField(default=timezone.now)
    ip_hash = models.CharField(max_length=64)

    class Meta:
        """Conserva una sola evidencia por socio y version informada."""

        ordering = ['-fecha_aceptacion']
        verbose_name = 'aceptacion de privacidad para consulta'
        verbose_name_plural = 'aceptaciones de privacidad para consulta'
        constraints = [
            models.UniqueConstraint(
                fields=['socio', 'version_politica'],
                name='aceptacion_privacidad_unica_socio_version',
            ),
        ]

    def __str__(self):
        """Representa la evidencia sin incluir identificadores personales."""
        return f'Aceptacion socio #{self.socio_id} - {self.version_politica}'


class IntentoAcceso(models.Model):
    """Evidencia seudonimizada para limitar intentos de autenticacion."""

    LOGIN = 'LOGIN'
    RECUPERACION = 'RECUPERACION'
    REAUTENTICACION = 'REAUTENTICACION'
    TIPOS = [
        (LOGIN, 'Inicio de sesion'),
        (RECUPERACION, 'Recuperacion de contrasena'),
        (REAUTENTICACION, 'Reautenticacion sensible'),
    ]

    tipo = models.CharField(max_length=20, choices=TIPOS)
    identificador_hash = models.CharField(max_length=64, db_index=True)
    ip_hash = models.CharField(max_length=64, db_index=True)
    fecha = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        """Indices para ventanas de limitacion por identidad e IP."""

        ordering = ['-fecha']
        verbose_name = 'intento de acceso'
        verbose_name_plural = 'intentos de acceso'
        indexes = [
            models.Index(
                fields=['tipo', 'identificador_hash', 'fecha'],
                name='acceso_tipo_id_fecha_idx',
            ),
            models.Index(
                fields=['tipo', 'ip_hash', 'fecha'],
                name='acceso_tipo_ip_fecha_idx',
            ),
        ]

    def __str__(self):
        """No expone el identificador original."""
        return f'{self.tipo} - {self.fecha:%Y-%m-%d %H:%M:%S}'
