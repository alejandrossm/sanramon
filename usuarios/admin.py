from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display = (
        'username',
        'email',
        'first_name',
        'last_name',
        'rut',
        'rol',
        'is_active',
        'is_staff',
    )
    list_filter = ('rol', 'is_active', 'is_staff', 'is_superuser')
    search_fields = ('username', 'email', 'first_name', 'last_name', 'rut')
    ordering = ('last_name', 'first_name', 'username')

    fieldsets = UserAdmin.fieldsets + (
        ('Datos del sistema', {'fields': ('rut', 'rol')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Datos del sistema', {'fields': ('email', 'first_name', 'last_name', 'rut', 'rol')}),
    )
