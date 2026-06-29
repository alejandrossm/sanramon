from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    AceptacionPrivacidadConsulta,
    AsistenciaReunion,
    DesbloqueoSocio,
    NotificacionBloqueoSocio,
    Reunion,
    SolicitudCodigoConsulta,
    Usuario,
)


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    """Configuracion del modelo Usuario dentro del admin de Django."""

    list_display = (
        'username',
        'email',
        'first_name',
        'last_name',
        'apellido_materno',
        'rut',
        'telefono_movil',
        'fecha_ingreso_proyecto',
        'rol',
        'is_active',
        'is_staff',
    )
    list_filter = ('rol', 'is_active', 'is_staff', 'is_superuser')
    search_fields = (
        'username',
        'email',
        'first_name',
        'last_name',
        'apellido_materno',
        'rut',
        'telefono_movil',
    )
    ordering = ('last_name', 'apellido_materno', 'first_name', 'username')

    fieldsets = UserAdmin.fieldsets + (
        (
            'Datos del sistema',
            {
                'fields': (
                    'apellido_materno',
                    'rut',
                    'telefono_movil',
                    'fecha_ingreso_proyecto',
                    'rol',
                )
            },
        ),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (
            'Datos del sistema',
            {
                'fields': (
                    'email',
                    'first_name',
                    'last_name',
                    'apellido_materno',
                    'rut',
                    'telefono_movil',
                    'fecha_ingreso_proyecto',
                    'rol',
                )
            },
        ),
    )

    def get_readonly_fields(self, request, obj=None):
        """Bloquea cambios de rol y privilegios para cuentas de socio."""
        readonly_fields = list(super().get_readonly_fields(request, obj))
        if obj:
            readonly_fields.append('username')
        if obj and obj.rol == Usuario.SOCIO:
            readonly_fields.extend(('rol', 'is_staff', 'is_superuser'))
        return tuple(readonly_fields)


@admin.register(Reunion)
class ReunionAdmin(admin.ModelAdmin):
    """Configuracion de reuniones dentro del admin de Django."""

    list_display = (
        'fecha',
        'hora',
        'locacion',
        'estado',
        'es_proxima',
        'creador',
        'activada_por',
        'fecha_activacion',
        'finalizada_por',
        'fecha_finalizacion',
        'cancelada_por',
        'fecha_cancelacion',
        'fecha_creacion',
    )
    list_filter = ('estado', 'es_proxima', 'fecha')
    search_fields = (
        'locacion',
        'motivo_cancelacion',
        'creador__username',
        'creador__email',
    )
    readonly_fields = (
        'fecha_creacion',
        'fecha_activacion',
        'fecha_finalizacion',
        'fecha_cancelacion',
    )
    ordering = ('-fecha', '-fecha_creacion')


@admin.register(AsistenciaReunion)
class AsistenciaReunionAdmin(admin.ModelAdmin):
    """Configuracion de asistencias de reuniones dentro del admin de Django."""

    list_display = (
        'reunion',
        'socio',
        'estado',
        'origen',
        'registrada_por',
        'fecha_registro',
    )
    list_filter = ('estado', 'origen', 'reunion__fecha')
    search_fields = (
        'socio__rut',
        'socio__first_name',
        'socio__last_name',
        'socio__apellido_materno',
        'registrada_por__username',
    )
    readonly_fields = ('fecha_registro',)
    ordering = ('-fecha_registro',)


@admin.register(DesbloqueoSocio)
class DesbloqueoSocioAdmin(admin.ModelAdmin):
    """Configuracion del historial de justificaciones de inasistencia."""

    list_display = (
        'socio',
        'asistencia',
        'desbloqueado_por',
        'fecha_desbloqueo',
        'inasistencias_al_desbloquear',
        'motivo',
    )
    list_filter = ('fecha_desbloqueo', 'asistencia__reunion__fecha')
    search_fields = (
        'socio__rut',
        'socio__first_name',
        'socio__last_name',
        'socio__apellido_materno',
        'asistencia__reunion__locacion',
        'desbloqueado_por__username',
        'motivo',
    )
    readonly_fields = ('fecha_desbloqueo',)
    ordering = ('-fecha_desbloqueo',)


@admin.register(NotificacionBloqueoSocio)
class NotificacionBloqueoSocioAdmin(admin.ModelAdmin):
    """Configuracion del historial de notificaciones de bloqueo."""

    list_display = (
        'socio',
        'email_destino',
        'enviada_por',
        'fecha_envio',
        'total_inasistencias_efectivas',
    )
    list_filter = ('fecha_envio',)
    search_fields = (
        'socio__rut',
        'socio__first_name',
        'socio__last_name',
        'socio__apellido_materno',
        'email_destino',
        'enviada_por__username',
    )
    readonly_fields = ('fecha_envio', 'firma_bloqueo')
    ordering = ('-fecha_envio',)


@admin.register(SolicitudCodigoConsulta)
class SolicitudCodigoConsultaAdmin(admin.ModelAdmin):
    """Consulta tecnica de solicitudes OTP sin exponer sus huellas."""

    list_display = (
        'id',
        'socio_id',
        'fecha_solicitud',
        'fecha_expiracion',
        'intentos_fallidos',
        'fecha_uso',
        'email_enviado',
    )
    list_filter = ('email_enviado', 'fecha_solicitud', 'fecha_uso')
    readonly_fields = (
        'id',
        'socio',
        'codigo_hash',
        'ip_hash',
        'fecha_solicitud',
        'fecha_expiracion',
        'intentos_fallidos',
        'fecha_uso',
        'email_enviado',
    )
    ordering = ('-fecha_solicitud',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AceptacionPrivacidadConsulta)
class AceptacionPrivacidadConsultaAdmin(admin.ModelAdmin):
    """Evidencia inmutable de la version informada al socio."""

    list_display = (
        'socio_id',
        'version_politica',
        'metodo_verificacion',
        'fecha_aceptacion',
    )
    list_filter = ('version_politica', 'metodo_verificacion', 'fecha_aceptacion')
    readonly_fields = (
        'socio',
        'version_politica',
        'texto_hash',
        'metodo_verificacion',
        'fecha_aceptacion',
        'ip_hash',
    )
    ordering = ('-fecha_aceptacion',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
