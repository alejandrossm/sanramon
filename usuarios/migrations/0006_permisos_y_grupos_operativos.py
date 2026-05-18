from django.db import migrations


PERMISOS_USUARIO = (
    ('gestionar_usuarios', 'Puede gestionar usuarios internos'),
    ('registrar_usuarios', 'Puede registrar usuarios internos'),
    ('registrar_socios', 'Puede registrar socios'),
    ('editar_socios', 'Puede editar socios'),
    ('acceder_asistencia', 'Puede acceder al modulo de asistencia'),
    ('eliminar_usuarios', 'Puede eliminar usuarios internos'),
    ('eliminar_socios', 'Puede eliminar socios'),
    ('administrar_privilegios', 'Puede administrar privilegios'),
)

GRUPO_ADMINISTRADOR = 'Administrador'
GRUPO_ENCARGADO_REGISTRO = 'Encargado de registro'
GRUPO_SOCIO = 'Socio'

PERMISOS_POR_GRUPO = {
    GRUPO_ADMINISTRADOR: tuple(codename for codename, _label in PERMISOS_USUARIO),
    GRUPO_ENCARGADO_REGISTRO: ('acceder_asistencia',),
    GRUPO_SOCIO: (),
}

GRUPO_POR_ROL = {
    'ADMINISTRADOR': GRUPO_ADMINISTRADOR,
    'ENCARGADO_REGISTRO': GRUPO_ENCARGADO_REGISTRO,
    'SOCIO': GRUPO_SOCIO,
}


def crear_permisos_y_grupos(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    ContentType = apps.get_model('contenttypes', 'ContentType')
    Permission = apps.get_model('auth', 'Permission')
    Group = apps.get_model('auth', 'Group')
    Usuario = apps.get_model('usuarios', 'Usuario')

    content_type, _created = ContentType.objects.using(db_alias).get_or_create(
        app_label='usuarios',
        model='usuario',
    )

    permisos_por_codigo = {}
    for codename, name in PERMISOS_USUARIO:
        permiso, creado = Permission.objects.using(db_alias).get_or_create(
            content_type=content_type,
            codename=codename,
            defaults={'name': name},
        )
        if not creado and permiso.name != name:
            permiso.name = name
            permiso.save(update_fields=['name'])
        permisos_por_codigo[codename] = permiso

    grupos_por_nombre = {}
    for nombre_grupo, permisos_grupo in PERMISOS_POR_GRUPO.items():
        grupo, _created = Group.objects.using(db_alias).get_or_create(
            name=nombre_grupo,
        )
        permisos = [
            permisos_por_codigo[codename]
            for codename in permisos_grupo
        ]
        if permisos:
            grupo.permissions.add(*permisos)
        grupos_por_nombre[nombre_grupo] = grupo

    grupos_operativos = list(grupos_por_nombre.values())
    for rol, nombre_grupo in GRUPO_POR_ROL.items():
        grupo_destino = grupos_por_nombre[nombre_grupo]
        grupos_a_remover = [
            grupo
            for grupo in grupos_operativos
            if grupo.name != nombre_grupo
        ]
        for usuario in Usuario.objects.using(db_alias).filter(rol=rol).iterator():
            if grupos_a_remover:
                usuario.groups.remove(*grupos_a_remover)
            usuario.groups.add(grupo_destino)


class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0005_usuario_telefono_movil_alter_usuario_email_and_more'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='usuario',
            options={
                'ordering': ['last_name', 'first_name', 'username'],
                'permissions': PERMISOS_USUARIO,
                'verbose_name': 'usuario',
                'verbose_name_plural': 'usuarios',
            },
        ),
        migrations.RunPython(
            crear_permisos_y_grupos,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
