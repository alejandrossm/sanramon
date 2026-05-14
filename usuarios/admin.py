from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Reunion, Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    """Configuracion del modelo Usuario dentro del admin de Django."""

    list_display = (
        'username',
        'email',
        'first_name',
        'last_name',
        'rut',
        'telefono_movil',
        'rol',
        'is_active',
        'is_staff',
    )
    list_filter = ('rol', 'is_active', 'is_staff', 'is_superuser')
    search_fields = ('username', 'email', 'first_name', 'last_name', 'rut', 'telefono_movil')
    ordering = ('last_name', 'first_name', 'username')

    fieldsets = UserAdmin.fieldsets + (
        ('Datos del sistema', {'fields': ('rut', 'telefono_movil', 'rol')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (
            'Datos del sistema',
            {'fields': ('email', 'first_name', 'last_name', 'rut', 'telefono_movil', 'rol')},
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

    list_display = ('fecha', 'hora', 'locacion', 'estado', 'es_proxima', 'creador', 'fecha_creacion')
    list_filter = ('estado', 'es_proxima', 'fecha')
    search_fields = ('locacion', 'creador__username', 'creador__email')
    readonly_fields = ('fecha_creacion',)
    ordering = ('-fecha', '-fecha_creacion')
