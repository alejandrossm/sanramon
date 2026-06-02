from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import AsistenciaReunion, DesbloqueoSocio, Reunion, Usuario


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
