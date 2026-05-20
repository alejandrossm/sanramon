import django.db.models.deletion
from django.db import migrations, models


def borrar_justificaciones_existentes(apps, schema_editor):
    """Elimina justificaciones previas sin trazabilidad exacta."""
    DesbloqueoSocio = apps.get_model('usuarios', 'DesbloqueoSocio')
    DesbloqueoSocio.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0014_ajustar_justificacion_inasistencia'),
    ]

    operations = [
        migrations.RunPython(
            borrar_justificaciones_existentes,
            migrations.RunPython.noop,
        ),
        migrations.AddField(
            model_name='desbloqueosocio',
            name='asistencia',
            field=models.OneToOneField(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='justificacion',
                to='usuarios.asistenciareunion',
                verbose_name='inasistencia justificada',
            ),
        ),
        migrations.AlterField(
            model_name='desbloqueosocio',
            name='asistencia',
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='justificacion',
                to='usuarios.asistenciareunion',
                verbose_name='inasistencia justificada',
            ),
        ),
    ]
