import csv
import re
import sqlite3
import zipfile
from datetime import date, datetime, time, timedelta
from io import BytesIO, StringIO
from pathlib import Path
from tempfile import NamedTemporaryFile, gettempdir
from urllib.parse import urlparse
from unittest.mock import patch

from django.conf import settings
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.staticfiles import finders
from django.core.cache import cache
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from .admin import UsuarioAdmin
from .auditoria import (
    ACCION_CARGA_HISTORICA_REVERTIDA,
    ACCION_CARGA_HISTORICA,
    ACCION_CARGA_MASIVA_SOCIOS,
    ACCION_LOG_AUDITORIA_DESCARGADO,
    ACCION_REPORTE_EXPORTADO,
    ACCION_RESPALDO_BASE_DATOS,
    ACCION_REUNION_CANCELADA,
    ACCION_REUNION_ELIMINADA,
    ACCION_SOCIO_ELIMINADO,
    ACCION_USUARIO_ACTIVADO,
    ACCION_USUARIO_DESACTIVADO,
    ACCION_USUARIO_ELIMINADO,
    leer_eventos_auditoria,
    listar_archivos_auditoria,
    registrar_evento_auditoria,
    verificar_integridad_archivo,
)
from .forms import (
    JustificacionInasistenciaForm,
    ReunionCancelacionForm,
    ReunionCreationForm,
    UsuarioCreationForm,
    UsuarioUpdateForm,
)
from .identificacion import (
    ORIGEN_QR_REGISTRO_CIVIL,
    ORIGEN_RUT_MANUAL,
    calcular_digito_verificador_rut,
    parsear_lectura_rut,
)
from .models import (
    AceptacionPrivacidadConsulta,
    AsistenciaReunion,
    CargaAsistenciaHistorica,
    DesbloqueoSocio,
    IntentoAcceso,
    NotificacionBloqueoSocio,
    Reunion,
    SolicitudCodigoConsulta,
)
from .privacidad import (
    POLITICA_PRIVACIDAD_VERSION,
    SESION_SOLICITUD_ID,
)
from .permisos import (
    GRUPO_ADMINISTRADOR,
    GRUPO_ENCARGADO_REGISTRO,
    GRUPO_SOCIO,
    PERM_ACCEDER_ASISTENCIA,
    PERM_ADMINISTRAR_PRIVILEGIOS,
    PERM_GESTIONAR_USUARIOS,
    ROLES_INTERNOS_GESTIONABLES,
)
from .servicios_asistencia import (
    agregar_resumen_asistencia_socios,
    anotar_resumen_asistencia_socios,
    obtener_historial_asistencia_socio,
    obtener_indicador_asistencia,
    obtener_proxima_reunion,
    obtener_resumen_anual_asistencia_socio,
    obtener_resumen_asistencia_socio,
    puede_eliminar_socio_seguro,
)
from .respaldos import descifrar_respaldo
from .seguridad import SESION_REAUTENTICADA_HASTA
from .views import (
    ROLES_FILTRABLES_USUARIOS,
    obtener_resumen_estado_asistencia_socios,
    puede_acceder_asistencia,
    puede_gestionar_usuarios,
    puede_registrar_socios,
    puede_registrar_usuarios,
)


@override_settings(
    PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    AUDITORIA_LOG_PATH=Path(gettempdir()) / 'sanramon_test_auditoria.log',
    RESPALDO_ENCRYPTION_KEYS=[
        'tK4O8lU1LMYcatkJFS352xgHz8obw8AvOPRIYV55phM='
    ],
    AUDITORIA_HMAC_KEY='clave-hmac-auditoria-exclusiva-para-pruebas',
)
class UsuariosModuloTests(TestCase):
    """Pruebas de autenticacion, roles, permisos y gestion de usuarios."""

    def setUp(self):
        """Crea usuarios base para validar reglas por rol."""
        Path(settings.AUDITORIA_LOG_PATH).unlink(missing_ok=True)
        cache.delete('privacidad:purga-solicitudes-otp:v1')
        cache.delete('seguridad:purga-intentos:v1')
        self.User = get_user_model()
        self.admin_user = self.User.objects.create_user(
            username='admin',
            email='admin@example.com',
            password='ClaveSegura123',
            first_name='Admin',
            last_name='Sistema',
            rut='11.111.111-1',
            telefono_movil='+56911111111',
            rol=self.User.ADMINISTRADOR,
        )
        self.socio_user = self.User.objects.create_user(
            username='socio',
            email='socio@example.com',
            password='ClaveSegura123',
            first_name='Socio',
            last_name='Prueba',
            rut='22.222.222-2',
            telefono_movil='+56922222222',
            rol=self.User.SOCIO,
        )
        self.encargado_user = self.User.objects.create_user(
            username='encargado',
            email='encargado@example.com',
            password='ClaveSegura123',
            first_name='Encargado',
            last_name='Registro',
            rut='44.444.444-4',
            telefono_movil='+56944444444',
            rol=self.User.ENCARGADO_REGISTRO,
        )

    @staticmethod
    def rut_prueba(cuerpo):
        """Construye un RUT de prueba con digito verificador valido."""
        cuerpo = str(cuerpo)
        return f'{cuerpo}-{calcular_digito_verificador_rut(cuerpo)}'

    def registrar_asistencia_historica(self, socio, estado, fecha):
        """Crea un registro historico de asistencia para pruebas de resumen."""
        reunion = Reunion.objects.create(
            fecha=fecha,
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
            estado=Reunion.FINALIZADA,
        )
        origen = AsistenciaReunion.ORIGEN_RUT
        if estado == AsistenciaReunion.AUSENTE:
            origen = AsistenciaReunion.ORIGEN_AUTOMATICO
        return AsistenciaReunion.objects.create(
            reunion=reunion,
            socio=socio,
            estado=estado,
            origen=origen,
            registrada_por=self.admin_user,
        )

    def solicitar_codigo_consulta(self, rut=None, anio=2026):
        """Solicita y extrae el OTP entregado por el backend de pruebas."""
        response = self.client.post(
            reverse('usuarios:consulta_publica_asistencia'),
            {
                'rut': rut or self.socio_user.rut,
                'anio': str(anio),
            },
        )
        self.assertRedirects(
            response,
            reverse('usuarios:verificar_codigo_consulta'),
        )
        mensaje = mail.outbox[-1]
        coincidencia = re.search(r'Tu código es: (\d{6})', mensaje.body)
        self.assertIsNotNone(coincidencia)
        return coincidencia.group(1)

    def test_permisos_base_estan_asignados_a_grupos_operativos(self):
        """Crea grupos equivalentes a roles sin acoplar permisos al codigo."""
        grupo_admin = Group.objects.get(name=GRUPO_ADMINISTRADOR)
        grupo_encargado = Group.objects.get(name=GRUPO_ENCARGADO_REGISTRO)
        grupo_socio = Group.objects.get(name=GRUPO_SOCIO)

        self.assertTrue(
            grupo_admin.permissions.filter(
                codename=PERM_GESTIONAR_USUARIOS,
            ).exists()
        )
        self.assertTrue(
            grupo_admin.permissions.filter(
                codename=PERM_ADMINISTRAR_PRIVILEGIOS,
            ).exists()
        )
        self.assertTrue(
            grupo_encargado.permissions.filter(
                codename=PERM_ACCEDER_ASISTENCIA,
            ).exists()
        )
        self.assertFalse(
            grupo_encargado.permissions.filter(
                codename=PERM_GESTIONAR_USUARIOS,
            ).exists()
        )
        self.assertEqual(grupo_socio.permissions.count(), 0)

    def test_usuario_sincroniza_grupo_operativo_segun_rol(self):
        """Mantiene grupos Django alineados con el rol operativo vigente."""
        self.assertTrue(
            self.admin_user.groups.filter(name=GRUPO_ADMINISTRADOR).exists()
        )
        self.assertTrue(
            self.encargado_user.groups.filter(name=GRUPO_ENCARGADO_REGISTRO).exists()
        )
        self.assertTrue(
            self.socio_user.groups.filter(name=GRUPO_SOCIO).exists()
        )

        self.encargado_user.rol = self.User.ADMINISTRADOR
        self.encargado_user.save(update_fields=['rol'])

        self.assertTrue(
            self.encargado_user.groups.filter(name=GRUPO_ADMINISTRADOR).exists()
        )
        self.assertFalse(
            self.encargado_user.groups.filter(name=GRUPO_ENCARGADO_REGISTRO).exists()
        )

    def test_permisos_operativos_respetan_roles_vigentes(self):
        """Mantiene las reglas actuales sobre la capa de permisos Django."""
        self.assertTrue(puede_gestionar_usuarios(self.admin_user))
        self.assertTrue(puede_registrar_usuarios(self.admin_user))
        self.assertTrue(puede_registrar_socios(self.admin_user))
        self.assertTrue(puede_acceder_asistencia(self.admin_user))

        self.assertFalse(puede_gestionar_usuarios(self.encargado_user))
        self.assertFalse(puede_registrar_usuarios(self.encargado_user))
        self.assertFalse(puede_registrar_socios(self.encargado_user))
        self.assertTrue(puede_acceder_asistencia(self.encargado_user))

        self.assertFalse(puede_gestionar_usuarios(self.socio_user))
        self.assertFalse(puede_registrar_usuarios(self.socio_user))
        self.assertFalse(puede_registrar_socios(self.socio_user))
        self.assertFalse(puede_acceder_asistencia(self.socio_user))

    def test_reunion_se_crea_programada_con_creador(self):
        """Persiste los datos base de una reunion programada."""
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
        )

        self.assertEqual(reunion.estado, Reunion.PROGRAMADA)
        self.assertFalse(reunion.es_proxima)
        self.assertEqual(reunion.creador, self.admin_user)
        self.assertEqual(str(reunion), '2026-05-20 18:30 - Sede social')

    def test_formulario_reunion_exige_fecha_hora_y_locacion(self):
        """Valida los campos obligatorios antes de guardar."""
        form = ReunionCreationForm(data={}, creador=self.admin_user)

        self.assertFalse(form.is_valid())
        self.assertIn('fecha', form.errors)
        self.assertIn('hora', form.errors)
        self.assertIn('locacion', form.errors)

    def test_formulario_reunion_exige_hora_en_formato_24_horas(self):
        """Rechaza horas con AM/PM o sin cero inicial."""
        datos_base = {
            'fecha': '2026-07-20',
            'locacion': 'Sede social',
            'estado': Reunion.PROGRAMADA,
        }

        for hora_invalida in ('6:30 PM', '6:30'):
            form = ReunionCreationForm(
                data={**datos_base, 'hora': hora_invalida},
                creador=self.admin_user,
            )
            self.assertFalse(form.is_valid())
            self.assertIn(
                ReunionCreationForm.HORA_24H_MENSAJE,
                form.errors['hora'],
            )

        form = ReunionCreationForm(
            data={**datos_base, 'hora': '18:30'},
            creador=self.admin_user,
        )
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['hora'], time(18, 30))

    @patch('usuarios.forms.timezone.localtime', return_value=datetime(2026, 5, 14, 12, 0))
    def test_formulario_reunion_alerta_fecha_hora_duplicada(self, _localtime):
        """Bloquea reuniones con fecha y hora ya registradas."""
        Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
        )

        form = ReunionCreationForm(
            data={
                'fecha': '2026-05-20',
                'hora': '18:30',
                'locacion': 'Sede norte',
                'estado': Reunion.PROGRAMADA,
            },
            creador=self.admin_user,
        )

        self.assertFalse(form.is_valid())
        self.assertTrue(form.reunion_duplicada)
        self.assertIn(
            ReunionCreationForm.REUNION_DUPLICADA_MENSAJE,
            form.non_field_errors(),
        )

    @patch('usuarios.forms.timezone.localtime', return_value=datetime(2026, 5, 14, 12, 0))
    def test_formulario_reunion_pasada_debe_ser_historica(self, _localtime):
        """Obliga a registrar como historicas las reuniones anteriores a ahora."""
        form = ReunionCreationForm(
            data={
                'fecha': '2026-05-13',
                'hora': '18:30',
                'locacion': 'Sede social',
                'estado': Reunion.PROGRAMADA,
            },
            creador=self.admin_user,
        )

        self.assertFalse(form.is_valid())
        self.assertTrue(form.reunion_pasada_requiere_historica)
        self.assertIn(
            ReunionCreationForm.REUNION_PASADA_HISTORICA_MENSAJE,
            form.non_field_errors(),
        )

        form = ReunionCreationForm(
            data={
                'fecha': '2026-05-13',
                'hora': '18:30',
                'locacion': 'Sede social',
                'estado': Reunion.HISTORICA,
            },
            creador=self.admin_user,
        )

        self.assertTrue(form.is_valid())

    @patch('usuarios.forms.timezone.localtime', return_value=datetime(2026, 5, 14, 12, 0))
    def test_formulario_reunion_hoy_con_hora_pasada_debe_ser_historica(self, _localtime):
        """Considera historicas las reuniones de hoy cuando la hora ya paso."""
        form = ReunionCreationForm(
            data={
                'fecha': '2026-05-14',
                'hora': '11:30',
                'locacion': 'Sede social',
                'estado': Reunion.PROGRAMADA,
            },
            creador=self.admin_user,
        )

        self.assertFalse(form.is_valid())
        self.assertTrue(form.reunion_pasada_requiere_historica)
        self.assertIn(
            ReunionCreationForm.REUNION_PASADA_HISTORICA_MENSAJE,
            form.non_field_errors(),
        )

        form = ReunionCreationForm(
            data={
                'fecha': '2026-05-14',
                'hora': '12:30',
                'locacion': 'Sede social',
                'estado': Reunion.PROGRAMADA,
            },
            creador=self.admin_user,
        )

        self.assertTrue(form.is_valid())

    def test_formulario_reunion_permite_programada_o_historica(self):
        """Limita los estados disponibles al crear reuniones."""
        form = ReunionCreationForm(creador=self.admin_user)

        self.assertEqual(
            list(form.fields['estado'].choices),
            [
                (Reunion.PROGRAMADA, 'Programada'),
                (Reunion.HISTORICA, 'Histórica'),
            ],
        )

        form = ReunionCreationForm(
            data={
                'fecha': '2026-05-20',
                'hora': '18:30',
                'locacion': 'Sede social',
                'estado': Reunion.HISTORICA,
            },
            creador=self.admin_user,
        )

        self.assertTrue(form.is_valid())
        reunion = form.save()
        self.assertEqual(reunion.estado, Reunion.HISTORICA)

    def test_formulario_cancelacion_exige_motivo(self):
        """Valida que el motivo de cancelacion tenga contenido real."""
        form_vacio = ReunionCancelacionForm(data={'motivo_cancelacion': '   '})
        form_valido = ReunionCancelacionForm(data={'motivo_cancelacion': 'Cambio de agenda'})

        self.assertFalse(form_vacio.is_valid())
        self.assertIn('motivo_cancelacion', form_vacio.errors)
        self.assertTrue(form_valido.is_valid())
        self.assertEqual(form_valido.cleaned_data['motivo_cancelacion'], 'Cambio de agenda')

    def test_formulario_justificacion_exige_motivo_y_socio_bloqueado(self):
        """Valida motivo y condicion de bloqueo antes de justificar."""
        ausencia_justificada = self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 20),
        )
        form_no_bloqueado = JustificacionInasistenciaForm(
            data={
                'asistencia': ausencia_justificada.pk,
                'motivo': 'Revision administrativa',
            },
            socio=self.socio_user,
            usuario=self.admin_user,
        )
        self.assertFalse(form_no_bloqueado.is_valid())
        self.assertIn(
            'El socio no esta bloqueado por inasistencias.',
            form_no_bloqueado.non_field_errors(),
        )

        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 27),
        )
        form_vacio = JustificacionInasistenciaForm(
            data={'asistencia': ausencia_justificada.pk, 'motivo': '   '},
            socio=self.socio_user,
            usuario=self.admin_user,
        )
        form_valido = JustificacionInasistenciaForm(
            data={
                'asistencia': ausencia_justificada.pk,
                'motivo': 'Compromiso firmado',
            },
            socio=self.socio_user,
            usuario=self.admin_user,
        )

        self.assertFalse(form_vacio.is_valid())
        self.assertIn('motivo', form_vacio.errors)
        self.assertTrue(form_valido.is_valid())
        self.assertEqual(form_valido.cleaned_data['asistencia'], ausencia_justificada)
        self.assertEqual(form_valido.cleaned_data['motivo'], 'Compromiso firmado')

    def test_reunion_historica_no_se_inicia_ni_finaliza(self):
        """Reserva reuniones historicas para carga posterior y eliminacion segura."""
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
            estado=Reunion.HISTORICA,
        )

        self.assertTrue(reunion.es_historica())
        self.assertFalse(reunion.puede_iniciarse())
        self.assertFalse(reunion.puede_finalizarse())
        self.assertTrue(reunion.puede_eliminarse())

    def test_reunion_no_se_elimina_si_tiene_asistencias(self):
        """Bloquea eliminacion de reuniones con asistencia registrada."""
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
            estado=Reunion.HISTORICA,
        )
        AsistenciaReunion.objects.create(
            reunion=reunion,
            socio=self.socio_user,
            estado=AsistenciaReunion.PRESENTE,
            origen=AsistenciaReunion.ORIGEN_RUT,
            registrada_por=self.admin_user,
        )

        self.assertFalse(reunion.puede_eliminarse())

    @patch('usuarios.models.timezone.now')
    def test_reunion_programada_se_inicia_con_usuario_y_fecha(self, now_mock):
        """Cambia una reunion programada a activa registrando responsable."""
        momento = datetime(2026, 5, 20, 18, 35, tzinfo=timezone.get_current_timezone())
        now_mock.return_value = momento
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
        )

        reunion.iniciar(self.admin_user)
        reunion.refresh_from_db()

        self.assertEqual(reunion.estado, Reunion.ACTIVA)
        self.assertEqual(reunion.activada_por, self.admin_user)
        self.assertEqual(reunion.fecha_activacion, momento)
        self.assertTrue(reunion.puede_finalizarse())

    def test_reunion_no_inicia_si_no_esta_programada(self):
        """Impide activar reuniones historicas o en estados no iniciables."""
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
            estado=Reunion.HISTORICA,
        )

        with self.assertRaises(ValidationError):
            reunion.iniciar(self.admin_user)

        reunion.refresh_from_db()
        self.assertEqual(reunion.estado, Reunion.HISTORICA)

    def test_reunion_no_inicia_si_ya_existe_otra_activa(self):
        """Mantiene una unica reunion activa en el sistema."""
        activa = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
        )
        activa.iniciar(self.admin_user)
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 21),
            hora=time(18, 30),
            locacion='Sede norte',
            creador=self.admin_user,
        )

        with self.assertRaises(ValidationError):
            reunion.iniciar(self.admin_user)

        reunion.refresh_from_db()
        self.assertEqual(reunion.estado, Reunion.PROGRAMADA)
        self.assertEqual(Reunion.objects.filter(estado=Reunion.ACTIVA).count(), 1)

    @patch('usuarios.models.timezone.now')
    def test_reunion_activa_se_finaliza_marcando_ausentes_activos(self, now_mock):
        """Cierra la reunion y crea ausencias automaticas para socios activos."""
        momento = datetime(2026, 5, 20, 20, 0, tzinfo=timezone.get_current_timezone())
        now_mock.return_value = momento
        socio_ausente = self.User.objects.create_user(
            username='socio.ausente',
            email='socio.ausente@example.com',
            password='ClaveSegura123',
            first_name='Socio',
            last_name='Ausente',
            rut='33.333.333-3',
            rol=self.User.SOCIO,
        )
        socio_inactivo = self.User.objects.create_user(
            username='socio.inactivo',
            email='socio.inactivo@example.com',
            password='ClaveSegura123',
            first_name='Socio',
            last_name='Inactivo',
            rut='55.555.555-5',
            rol=self.User.SOCIO,
            is_active=False,
        )
        reunion_previa = Reunion.objects.create(
            fecha=date(2026, 3, 10),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
            estado=Reunion.FINALIZADA,
        )
        AsistenciaReunion.objects.create(
            reunion=reunion_previa,
            socio=socio_ausente,
            estado=AsistenciaReunion.AUSENTE,
            origen=AsistenciaReunion.ORIGEN_AUTOMATICO,
            registrada_por=self.admin_user,
        )
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
        )
        reunion.iniciar(self.admin_user)
        AsistenciaReunion.registrar_presente(
            reunion=reunion,
            socio=self.socio_user,
            usuario=self.encargado_user,
            origen=AsistenciaReunion.ORIGEN_RUT,
        )

        resultado = reunion.finalizar(self.admin_user)
        reunion.refresh_from_db()

        self.assertEqual(reunion.estado, Reunion.FINALIZADA)
        self.assertEqual(reunion.finalizada_por, self.admin_user)
        self.assertEqual(reunion.fecha_finalizacion, momento)
        self.assertEqual(resultado['ausencias_creadas'], 1)
        self.assertEqual(resultado['inasistencias_anuales'][socio_ausente.pk], 2)
        self.assertFalse(
            AsistenciaReunion.objects.filter(
                reunion=reunion,
                socio=socio_inactivo,
            ).exists()
        )
        asistencia_ausente = AsistenciaReunion.objects.get(
            reunion=reunion,
            socio=socio_ausente,
        )
        self.assertEqual(asistencia_ausente.estado, AsistenciaReunion.AUSENTE)
        self.assertEqual(asistencia_ausente.origen, AsistenciaReunion.ORIGEN_AUTOMATICO)
        self.assertEqual(asistencia_ausente.registrada_por, self.admin_user)

    def test_reunion_finalizada_no_marca_ausente_socio_bloqueado(self):
        """No crea nuevas ausencias automaticas para socios ya bloqueados."""
        socio_bloqueado = self.User.objects.create_user(
            username='socio.bloqueado.finalizar',
            email='socio.bloqueado.finalizar@example.com',
            password='ClaveSegura123',
            first_name='Socio',
            last_name='Bloqueado',
            rut='66.666.666-6',
            rol=self.User.SOCIO,
        )
        self.registrar_asistencia_historica(
            socio_bloqueado,
            AsistenciaReunion.AUSENTE,
            date(2026, 4, 10),
        )
        self.registrar_asistencia_historica(
            socio_bloqueado,
            AsistenciaReunion.AUSENTE,
            date(2026, 4, 17),
        )
        self.assertTrue(AsistenciaReunion.socio_esta_bloqueado(socio_bloqueado))
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
        )
        reunion.iniciar(self.admin_user)
        AsistenciaReunion.registrar_presente(
            reunion=reunion,
            socio=self.socio_user,
            usuario=self.encargado_user,
            origen=AsistenciaReunion.ORIGEN_RUT,
        )

        resultado = reunion.finalizar(self.admin_user)

        self.assertEqual(resultado['ausencias_creadas'], 0)
        self.assertEqual(resultado['inasistencias_anuales'][socio_bloqueado.pk], 2)
        self.assertFalse(
            AsistenciaReunion.objects.filter(
                reunion=reunion,
                socio=socio_bloqueado,
            ).exists()
        )

    def test_reunion_finalizada_no_marca_ausente_socio_bloqueado_anio_previo(self):
        """Mantiene el bloqueo operativo al finalizar reuniones de otro ano."""
        anio_actual = timezone.localdate().year
        socio_bloqueado = self.User.objects.create_user(
            username='socio.bloqueado.anio.previo',
            email='socio.bloqueado.anio.previo@example.com',
            password='ClaveSegura123',
            first_name='Socio',
            last_name='Bloqueado',
            rut=self.rut_prueba(87654321),
            rol=self.User.SOCIO,
        )
        self.registrar_asistencia_historica(
            socio_bloqueado,
            AsistenciaReunion.AUSENTE,
            date(anio_actual - 1, 4, 10),
        )
        self.registrar_asistencia_historica(
            socio_bloqueado,
            AsistenciaReunion.AUSENTE,
            date(anio_actual - 1, 4, 17),
        )
        reunion = Reunion.objects.create(
            fecha=date(anio_actual, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
        )
        reunion.iniciar(self.admin_user)

        resultado = reunion.finalizar(self.admin_user)

        self.assertEqual(resultado['ausencias_creadas'], 1)
        self.assertFalse(
            AsistenciaReunion.objects.filter(
                reunion=reunion,
                socio=socio_bloqueado,
            ).exists()
        )
        self.assertTrue(AsistenciaReunion.socio_esta_bloqueado(socio_bloqueado))

    def test_reunion_finalizada_marca_ausente_socio_desbloqueado(self):
        """Vuelve a contabilizar ausencias cuando el socio ya fue desbloqueado."""
        socio_desbloqueado = self.User.objects.create_user(
            username='socio.desbloqueado.finalizar',
            email='socio.desbloqueado.finalizar@example.com',
            password='ClaveSegura123',
            first_name='Socio',
            last_name='Desbloqueado',
            rut='77.777.777-7',
            rol=self.User.SOCIO,
        )
        ausencia_justificada = self.registrar_asistencia_historica(
            socio_desbloqueado,
            AsistenciaReunion.AUSENTE,
            date(2026, 4, 10),
        )
        self.registrar_asistencia_historica(
            socio_desbloqueado,
            AsistenciaReunion.AUSENTE,
            date(2026, 4, 17),
        )
        DesbloqueoSocio.registrar(
            socio=socio_desbloqueado,
            usuario=self.admin_user,
            motivo='Justificacion administrativa',
            asistencia=ausencia_justificada,
        )
        self.assertFalse(AsistenciaReunion.socio_esta_bloqueado(socio_desbloqueado))
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
        )
        reunion.iniciar(self.admin_user)
        AsistenciaReunion.registrar_presente(
            reunion=reunion,
            socio=self.socio_user,
            usuario=self.encargado_user,
            origen=AsistenciaReunion.ORIGEN_RUT,
        )

        resultado = reunion.finalizar(self.admin_user)

        self.assertEqual(resultado['ausencias_creadas'], 1)
        self.assertEqual(resultado['inasistencias_anuales'][socio_desbloqueado.pk], 3)
        nueva_ausencia = AsistenciaReunion.objects.get(
            reunion=reunion,
            socio=socio_desbloqueado,
        )
        self.assertEqual(nueva_ausencia.estado, AsistenciaReunion.AUSENTE)
        self.assertEqual(
            AsistenciaReunion.contar_inasistencias_efectivas_socio(socio_desbloqueado),
            2,
        )
        self.assertTrue(AsistenciaReunion.socio_esta_bloqueado(socio_desbloqueado))

    def test_reunion_no_finaliza_si_no_esta_activa(self):
        """Impide cerrar reuniones programadas, historicas o ya finalizadas."""
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
        )

        with self.assertRaises(ValidationError):
            reunion.finalizar(self.admin_user)

        reunion.refresh_from_db()
        self.assertEqual(reunion.estado, Reunion.PROGRAMADA)
        self.assertFalse(
            AsistenciaReunion.objects.filter(reunion=reunion).exists()
        )

    @patch('usuarios.models.timezone.now')
    def test_reunion_activa_se_cancela_con_motivo_y_elimina_asistencias(self, now_mock):
        """Cancela una reunion activa sin dejar asistencias contabilizables."""
        momento = datetime(2026, 5, 20, 19, 0, tzinfo=timezone.get_current_timezone())
        now_mock.return_value = momento
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
        )
        reunion.iniciar(self.admin_user)
        AsistenciaReunion.registrar_presente(
            reunion=reunion,
            socio=self.socio_user,
            usuario=self.encargado_user,
            origen=AsistenciaReunion.ORIGEN_RUT,
        )

        resultado = reunion.cancelar(self.admin_user, '  Corte de energia  ')
        reunion.refresh_from_db()

        self.assertEqual(reunion.estado, Reunion.CANCELADA)
        self.assertEqual(reunion.cancelada_por, self.admin_user)
        self.assertEqual(reunion.fecha_cancelacion, momento)
        self.assertEqual(reunion.motivo_cancelacion, 'Corte de energia')
        self.assertEqual(resultado['asistencias_eliminadas'], 1)
        self.assertFalse(AsistenciaReunion.objects.filter(reunion=reunion).exists())
        self.assertFalse(Reunion.objects.filter(estado=Reunion.ACTIVA).exists())

    def test_reunion_cancelacion_requiere_motivo(self):
        """Impide cancelar sin motivo y conserva el estado original."""
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
        )

        with self.assertRaises(ValidationError):
            reunion.cancelar(self.admin_user, '   ')

        reunion.refresh_from_db()
        self.assertEqual(reunion.estado, Reunion.PROGRAMADA)
        self.assertIsNone(reunion.cancelada_por)
        self.assertEqual(reunion.motivo_cancelacion, '')

    def test_reunion_no_cancela_si_estado_no_permitido(self):
        """Impide cancelar reuniones historicas o cerradas."""
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
            estado=Reunion.HISTORICA,
        )

        with self.assertRaises(ValidationError):
            reunion.cancelar(self.admin_user, 'Registro erroneo')

        reunion.refresh_from_db()
        self.assertEqual(reunion.estado, Reunion.HISTORICA)

    def test_roles_internos_gestionables_alimentan_formularios_y_filtros(self):
        """Centraliza roles internos usados por formularios y filtros."""
        roles_esperados = {
            self.User.ADMINISTRADOR,
            self.User.ENCARGADO_REGISTRO,
        }
        self.assertEqual(set(ROLES_INTERNOS_GESTIONABLES), roles_esperados)
        form_creacion = UsuarioCreationForm(actor=self.admin_user)
        form_edicion = UsuarioUpdateForm(instance=self.encargado_user, actor=self.admin_user)

        self.assertEqual(
            {valor for valor, _label in form_creacion.fields['rol'].choices},
            roles_esperados,
        )
        self.assertEqual(
            {valor for valor, _label in form_edicion.fields['rol'].choices},
            roles_esperados,
        )
        self.assertEqual(
            {valor for valor, _label in ROLES_FILTRABLES_USUARIOS},
            roles_esperados,
        )

    def test_login_permite_correo_electronico(self):
        """Permite iniciar sesion usando email como identificador."""
        response = self.client.post(
            reverse('usuarios:login'),
            {'username': 'admin@example.com', 'password': 'ClaveSegura123'},
        )
        self.assertRedirects(response, reverse('usuarios:dashboard'))

    def test_login_bloquea_fuerza_bruta_por_identificador(self):
        """Bloquea nuevos intentos durante la ventana configurada."""
        with self.settings(SEGURIDAD_LOGIN_MAX_IDENTIFICADOR=2):
            for _indice in range(2):
                response = self.client.post(
                    reverse('usuarios:login'),
                    {'username': 'admin', 'password': 'incorrecta'},
                )
                self.assertEqual(response.status_code, 200)

            response = self.client.post(
                reverse('usuarios:login'),
                {'username': 'admin', 'password': 'ClaveSegura123'},
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Demasiados intentos')
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        self.assertGreaterEqual(
            IntentoAcceso.objects.filter(tipo=IntentoAcceso.LOGIN).count(),
            2,
        )

    def test_login_muestra_link_de_recuperacion_password(self):
        """Expone el acceso publico para recuperar contrasena."""
        response = self.client.get(reverse('usuarios:login'))

        self.assertContains(response, reverse('usuarios:password_reset'))
        self.assertContains(response, 'Olvide mi contrasena')

    def test_index_publico_muestra_landing_y_navegacion(self):
        """Expone la pagina de llegada con proyecto, menu, imagenes y footer."""
        response = self.client.get(reverse('usuarios:home'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Proyecto San Ram&oacute;n')
        self.assertContains(response, 'Ver mi asistencia')
        self.assertContains(response, 'Acceso al sistema')
        self.assertContains(response, reverse('usuarios:consulta_publica_asistencia'))
        self.assertContains(response, reverse('usuarios:login'))
        self.assertContains(response, 'images/f01.jpeg')
        self.assertContains(response, 'images/f02.jpeg')
        self.assertContains(response, 'images/f03.jpeg')
        self.assertContains(response, 'Redes sociales')
        self.assertContains(response, 'Contacto')

    def test_index_redirige_usuarios_autenticados_al_destino_por_rol(self):
        """Evita mostrar la portada publica a usuarios con sesion activa."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:home'))
        self.assertRedirects(response, reverse('usuarios:dashboard'))

        self.client.logout()
        self.client.login(username='socio', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:home'))
        self.assertRedirects(response, reverse('usuarios:mis_asistencias'))

    def test_consulta_publica_rut_invalido_muestra_mensaje_generico(self):
        """No entrega datos ni confirma coincidencias sin verificar correo."""
        response = self.client.post(
            reverse('usuarios:consulta_publica_asistencia'),
            {'rut': 'rut-invalido', 'anio': '2026'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'No fue posible encontrar informacion para los datos ingresados.',
        )
        self.assertNotIn('socio', response.context)

        response = self.client.post(
            reverse('usuarios:consulta_publica_asistencia'),
            {'rut': self.admin_user.rut, 'anio': '2026'},
        )
        self.assertRedirects(
            response,
            reverse('usuarios:verificar_codigo_consulta'),
        )
        self.assertEqual(len(mail.outbox), 0)
        response = self.client.get(reverse('usuarios:verificar_codigo_consulta'))
        self.assertContains(
            response,
            'Si el RUT está registrado, enviamos un código al correo asociado.',
        )
        self.assertNotContains(response, self.admin_user.email)
        self.assertNotContains(response, self.admin_user.nombre_completo)

    def test_consulta_publica_muestra_estado_resumen_e_historial(self):
        """Exige OTP y aceptacion antes de mostrar el historial anual."""
        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.PRESENTE,
            date(2025, 5, 20),
        )
        asistencia_2026 = self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.PRESENTE,
            date(2026, 5, 20),
        )
        ausencia_2026 = self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 21),
        )
        DesbloqueoSocio.objects.create(
            socio=self.socio_user,
            asistencia=ausencia_2026,
            motivo='Revision administrativa',
            desbloqueado_por=self.admin_user,
            inasistencias_al_desbloquear=1,
        )

        codigo = self.solicitar_codigo_consulta(anio=2026)
        solicitud = SolicitudCodigoConsulta.objects.get()
        self.assertNotEqual(solicitud.codigo_hash, codigo)
        self.assertNotIn(codigo, solicitud.codigo_hash)
        self.assertEqual(mail.outbox[0].to, [self.socio_user.email])

        response = self.client.get(
            reverse('usuarios:resultado_consulta_asistencia'),
        )
        self.assertRedirects(
            response,
            reverse('usuarios:consulta_publica_asistencia'),
            fetch_redirect_response=False,
        )

        response = self.client.post(
            reverse('usuarios:verificar_codigo_consulta'),
            {'codigo': codigo},
        )
        self.assertRedirects(
            response,
            reverse('usuarios:aceptar_privacidad_consulta'),
        )

        response = self.client.post(
            reverse('usuarios:aceptar_privacidad_consulta'),
            {'acepta': 'on'},
        )
        self.assertRedirects(
            response,
            reverse('usuarios:resultado_consulta_asistencia'),
        )

        response = self.client.get(
            reverse('usuarios:resultado_consulta_asistencia'),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(response.context['socio'], self.socio_user)
        self.assertNotIn('proxima_reunion', response.context)
        self.assertEqual(response.context['resumen_general']['total_reuniones'], 3)
        self.assertEqual(response.context['resumen_general']['total_asistencias'], 2)
        self.assertEqual(response.context['resumen_general']['total_ausencias'], 1)
        self.assertEqual(response.context['resumen_anual']['total_reuniones'], 2)
        self.assertEqual(response.context['resumen_anual']['total_asistencias'], 1)
        self.assertEqual(response.context['resumen_anual']['total_ausencias'], 1)
        self.assertEqual(
            list(response.context['historial']),
            [ausencia_2026, asistencia_2026],
        )
        self.assertContains(response, self.socio_user.nombre_completo)
        self.assertContains(response, 'Resumen anual 2026')
        self.assertNotContains(response, 'Pr&oacute;xima reuni&oacute;n')
        self.assertNotContains(response, 'Ausencias efectivas')
        self.assertNotContains(response, 'Justificaciones')
        self.assertNotContains(response, 'JUSTIFICACI')
        self.assertNotContains(response, 'Justificada')
        self.assertNotContains(response, '2025')
        aceptacion = AceptacionPrivacidadConsulta.objects.get(
            socio=self.socio_user,
        )
        self.assertEqual(
            aceptacion.version_politica,
            POLITICA_PRIVACIDAD_VERSION,
        )
        self.assertEqual(
            aceptacion.metodo_verificacion,
            AceptacionPrivacidadConsulta.METODO_EMAIL_OTP,
        )

    def test_codigo_consulta_es_de_uso_unico_y_limita_intentos(self):
        """Rechaza reutilizacion y bloquea una solicitud tras cinco errores."""
        codigo = self.solicitar_codigo_consulta()
        solicitud_id = self.client.session[SESION_SOLICITUD_ID]

        for _indice in range(5):
            response = self.client.post(
                reverse('usuarios:verificar_codigo_consulta'),
                {'codigo': '999999' if codigo != '999999' else '888888'},
            )
            self.assertEqual(response.status_code, 200)

        solicitud = SolicitudCodigoConsulta.objects.get(pk=solicitud_id)
        self.assertEqual(solicitud.intentos_fallidos, 5)
        response = self.client.post(
            reverse('usuarios:verificar_codigo_consulta'),
            {'codigo': codigo},
        )
        self.assertContains(response, 'máximo de intentos')

        SolicitudCodigoConsulta.objects.all().delete()
        mail.outbox.clear()
        codigo = self.solicitar_codigo_consulta()
        response = self.client.post(
            reverse('usuarios:verificar_codigo_consulta'),
            {'codigo': codigo},
        )
        self.assertEqual(response.status_code, 302)
        solicitud = SolicitudCodigoConsulta.objects.get()
        sesion = self.client.session
        sesion[SESION_SOLICITUD_ID] = str(solicitud.pk)
        sesion.save()
        response = self.client.post(
            reverse('usuarios:verificar_codigo_consulta'),
            {'codigo': codigo},
        )
        self.assertContains(response, 'no es válido')

    def test_codigo_consulta_expira_y_aplica_limite_por_socio(self):
        """Impide usar codigos vencidos y frena reenvios abusivos."""
        codigo = self.solicitar_codigo_consulta()
        solicitud = SolicitudCodigoConsulta.objects.get()
        solicitud.fecha_expiracion = timezone.now() - timedelta(seconds=1)
        solicitud.save(update_fields=['fecha_expiracion'])
        response = self.client.post(
            reverse('usuarios:verificar_codigo_consulta'),
            {'codigo': codigo},
        )
        self.assertContains(response, 'expiró')

        SolicitudCodigoConsulta.objects.all().delete()
        mail.outbox.clear()
        with self.settings(CONSULTA_CODIGO_MAX_SOLICITUDES_SOCIO=1):
            self.solicitar_codigo_consulta()
            response = self.client.post(
                reverse('usuarios:consulta_publica_asistencia'),
                {'rut': self.socio_user.rut, 'anio': '2026'},
            )
        self.assertRedirects(
            response,
            reverse('usuarios:verificar_codigo_consulta'),
        )
        self.assertEqual(len(mail.outbox), 1)

    def test_politica_privacidad_es_publica_y_versionada(self):
        """Mantiene disponible el aviso usado por la consulta."""
        response = self.client.get(reverse('usuarios:politica_privacidad'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, POLITICA_PRIVACIDAD_VERSION)
        self.assertContains(response, 'Derechos de las personas')
        self.assertContains(response, 'contacto@vallesanramon.cl')

    def test_nueva_solicitud_purga_otp_antiguos(self):
        """Elimina oportunistamente la evidencia tecnica con mas de 30 dias."""
        self.solicitar_codigo_consulta()
        solicitud = SolicitudCodigoConsulta.objects.get()
        SolicitudCodigoConsulta.objects.filter(pk=solicitud.pk).update(
            fecha_solicitud=timezone.now() - timedelta(days=31),
        )

        cache.delete('privacidad:purga-solicitudes-otp:v1')
        mail.outbox.clear()
        self.solicitar_codigo_consulta()
        self.assertFalse(SolicitudCodigoConsulta.objects.filter(pk=solicitud.pk).exists())

    def test_recuperacion_password_muestra_link_a_home(self):
        """Permite volver a home desde el flujo publico de recuperacion."""
        response = self.client.get(reverse('usuarios:password_reset'))

        self.assertContains(response, reverse('usuarios:home'))
        self.assertContains(response, 'Volver a home')

        response = self.client.get(
            reverse(
                'usuarios:password_reset_confirm',
                kwargs={'uidb64': 'uid-invalido', 'token': 'token-invalido'},
            )
        )

        self.assertContains(response, reverse('usuarios:home'))
        self.assertContains(response, 'Volver a home')

    def test_recuperacion_password_envia_correo_y_actualiza_password(self):
        """Envia el token por correo y permite guardar una nueva contrasena."""
        response = self.client.post(
            reverse('usuarios:password_reset'),
            {'email': 'admin@example.com'},
        )

        self.assertRedirects(response, reverse('usuarios:password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)
        mensaje = mail.outbox[0]
        self.assertEqual(mensaje.to, ['admin@example.com'])
        asunto_esperado = ''.join(
            render_to_string('usuarios/password_reset_subject.txt').splitlines()
        )
        self.assertEqual(mensaje.subject, asunto_esperado)

        enlace = next(
            linea.strip()
            for linea in mensaje.body.splitlines()
            if 'recuperar-contrasena' in linea
        )
        ruta_reset = urlparse(enlace).path

        response = self.client.get(ruta_reset)
        self.assertEqual(response.status_code, 302)
        ruta_confirmacion = response['Location']

        response = self.client.post(
            ruta_confirmacion,
            {
                'new_password1': 'ClaveNuevaSegura123',
                'new_password2': 'ClaveNuevaSegura123',
            },
        )

        self.assertRedirects(response, reverse('usuarios:password_reset_complete'))
        self.admin_user.refresh_from_db()
        self.assertTrue(self.admin_user.check_password('ClaveNuevaSegura123'))

    def test_recuperacion_password_limita_envios_sin_revelar_cuenta(self):
        """Mantiene la respuesta generica y deja de enviar al alcanzar el limite."""
        with self.settings(SEGURIDAD_RECUPERACION_MAX_IDENTIFICADOR=2):
            for _indice in range(3):
                response = self.client.post(
                    reverse('usuarios:password_reset'),
                    {'email': self.admin_user.email},
                )
                self.assertRedirects(
                    response,
                    reverse('usuarios:password_reset_done'),
                )

        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(
            IntentoAcceso.objects.filter(
                tipo=IntentoAcceso.RECUPERACION,
            ).count(),
            2,
        )

    def test_exportacion_exige_reautenticacion_cuando_vence_sesion_reciente(self):
        """Solicita contraseña y vuelve de forma segura a la descarga."""
        self.client.login(username='admin', password='ClaveSegura123')
        sesion = self.client.session
        sesion.pop(SESION_REAUTENTICADA_HASTA, None)
        sesion.save()
        destino = reverse('usuarios:exportar_socios_completo', args=['csv'])

        response = self.client.get(destino)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].startswith(reverse('usuarios:reauth_seguridad')))

        response = self.client.post(
            reverse('usuarios:reauth_seguridad'),
            {'password': 'incorrecta', 'next': destino},
        )
        self.assertContains(response, 'contraseña no es correcta')

        response = self.client.post(
            reverse('usuarios:reauth_seguridad'),
            {'password': 'ClaveSegura123', 'next': destino},
        )
        self.assertRedirects(response, destino, fetch_redirect_response=False)

        response = self.client.get(destino)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('text/csv'))
        self.assertEqual(
            leer_eventos_auditoria()[0]['accion'],
            ACCION_REPORTE_EXPORTADO,
        )

    def test_recuperacion_password_no_envia_correo_a_socio_activo(self):
        """No envia recuperacion a socios aunque tengan password utilizable."""
        response = self.client.post(
            reverse('usuarios:password_reset'),
            {'email': 'socio@example.com'},
        )

        self.assertRedirects(response, reverse('usuarios:password_reset_done'))
        self.assertEqual(len(mail.outbox), 0)

    def test_recuperacion_password_no_envia_correo_a_socio_sin_password_utilizable(self):
        """No envia recuperacion cuando el socio no tiene password utilizable."""
        self.socio_user.set_unusable_password()
        self.socio_user.save(update_fields=['password'])

        response = self.client.post(
            reverse('usuarios:password_reset'),
            {'email': 'socio@example.com'},
        )

        self.assertRedirects(response, reverse('usuarios:password_reset_done'))
        self.assertEqual(len(mail.outbox), 0)

    def test_socio_no_accede_a_gestion_de_usuarios(self):
        """Redirige al socio cuando intenta entrar a gestion de usuarios."""
        self.client.login(username='socio', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:listado_usuarios'))
        self.assertRedirects(response, reverse('usuarios:mis_asistencias'))
        response = self.client.get(reverse('usuarios:listado_socios'))
        self.assertRedirects(response, reverse('usuarios:mis_asistencias'))

    def test_socio_no_accede_a_vista_de_asistencia(self):
        """Redirige al socio cuando intenta entrar al modulo de asistencia."""
        self.client.login(username='socio', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:listado_socios_asistencia'))
        self.assertRedirects(response, reverse('usuarios:mis_asistencias'))

    def test_socio_login_redirige_a_mis_asistencias(self):
        """Envia al socio a su vista de asistencias despues del login."""
        response = self.client.post(
            reverse('usuarios:login'),
            {'username': 'socio@example.com', 'password': 'ClaveSegura123'},
        )
        self.assertRedirects(response, reverse('usuarios:mis_asistencias'))

    def test_socio_dashboard_redirige_a_mis_asistencias(self):
        """Evita que el socio use el dashboard interno."""
        self.client.login(username='socio', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:dashboard'))
        self.assertRedirects(response, reverse('usuarios:mis_asistencias'))

    def test_socio_ve_mensaje_sin_asistencias(self):
        """Muestra el estado vacio de asistencias para socios."""
        self.client.login(username='socio', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:mis_asistencias'))
        self.assertContains(response, 'No hay asistencias registradas.')

    def test_usuario_no_autenticado_redirige_a_login(self):
        """Protege el dashboard para visitantes no autenticados."""
        response = self.client.get(reverse('usuarios:dashboard'))
        self.assertRedirects(
            response,
            f"{reverse('usuarios:login')}?next={reverse('usuarios:dashboard')}",
        )

    def test_usuario_no_autenticado_no_accede_a_asistencia(self):
        """Protege la vista de asistencia para visitantes no autenticados."""
        url = reverse('usuarios:listado_socios_asistencia')
        response = self.client.get(url)
        self.assertRedirects(response, f"{reverse('usuarios:login')}?next={url}")

    def test_dashboard_muestra_logo_metricas_y_grafico_de_asistencia_socios(self):
        """Renderiza metricas y grafico de estado de asistencia de socios."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:dashboard'))
        self.assertContains(response, 'images/logo.png')
        self.assertContains(response, 'Estado de asistencia de socios')
        self.assertContains(response, 'Socios totales')
        self.assertContains(response, 'Sin falta')
        self.assertContains(response, 'En riesgo')
        self.assertContains(response, 'Bloqueados por inasistencia')
        self.assertContains(response, 'asistenciaChart')
        self.assertContains(response, '<canvas id="asistenciaChart"></canvas>', html=True)
        self.assertNotContains(response, 'dashboard-line-chart')
        self.assertNotContains(response, 'dashboard-bar-chart')
        self.assertContains(response, '<strong class="d-block fs-1 lh-1">3</strong>', html=True)

    def test_layout_usa_bootstrap_sweetalert_e_iconos_locales(self):
        """Carga dependencias visuales desde static local sin CDN."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:dashboard'))

        self.assertNotContains(response, 'cdn.jsdelivr.net')
        self.assertContains(response, 'vendor/bootstrap/bootstrap.min.css')
        self.assertContains(response, 'vendor/bootstrap-icons/bootstrap-icons.min.css')
        self.assertContains(response, 'css/styles.css?v=placeholder-1')
        self.assertContains(response, 'vendor/bootstrap/bootstrap.bundle.min.js')
        self.assertContains(response, 'vendor/sweetalert2/sweetalert2.all.min.js')
        self.assertContains(response, 'vendor/chart.js/chart.min.js')
        self.assertContains(response, 'js/app.js')
        self.assertContains(response, 'js/dashboard.js')
        self.assertNotContains(response, 'js/reuniones.js')
        self.assertContains(response, 'data-sidebar-toggle')
        self.assertContains(response, 'aria-controls="sidebar-panel"')

        rutas_estaticas = [
            'vendor/bootstrap/bootstrap.min.css',
            'vendor/bootstrap-icons/bootstrap-icons.min.css',
            'vendor/bootstrap-icons/fonts/bootstrap-icons.woff',
            'vendor/bootstrap-icons/fonts/bootstrap-icons.woff2',
            'vendor/bootstrap/bootstrap.bundle.min.js',
            'vendor/sweetalert2/sweetalert2.all.min.js',
            'vendor/chart.js/chart.min.js',
            'js/app.js',
            'js/dashboard.js',
            'js/reuniones.js',
        ]
        for ruta in rutas_estaticas:
            with self.subTest(ruta=ruta):
                self.assertIsNotNone(finders.find(ruta))

        ruta_css = finders.find('css/styles.css')
        with open(ruta_css, encoding='utf-8') as archivo_css:
            estilos = archivo_css.read()
        self.assertIn('--color-placeholder', estilos)
        self.assertIn('.form-control::placeholder', estilos)

    def test_layout_publico_usa_css_con_placeholders_diferenciados(self):
        """Carga la misma hoja global actualizada en la vista publica."""
        response = self.client.get(reverse('usuarios:consulta_publica_asistencia'))

        self.assertContains(response, 'css/styles.css?v=placeholder-1')
        self.assertContains(response, 'placeholder="12.345.678-5"')

    def test_dashboard_encargado_no_muestra_registro_socio(self):
        """Oculta el acceso de registro de socio para encargados."""
        self.client.login(username='encargado', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Registrar socio')
        self.assertNotContains(response, 'Listado socios')

    def test_nav_dashboard_admin_muestra_accesos_autorizados(self):
        """Mantiene accesos del dashboard alineados a permisos administrativos."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:dashboard'))

        self.assertContains(response, 'aria-label="Accesos del dashboard"')
        self.assertContains(response, 'Gestionar usuarios')
        self.assertContains(response, 'Gestionar socios')
        self.assertContains(response, 'Registrar socio')
        self.assertContains(response, 'Asistencia')

    def test_nav_dashboard_encargado_solo_muestra_asistencia(self):
        """Evita exponer gestion administrativa al encargado de registro."""
        self.client.login(username='encargado', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:dashboard'))

        self.assertContains(response, 'aria-label="Accesos del dashboard"')
        self.assertContains(response, 'Asistencia')
        self.assertContains(
            response,
            '<p class="sidebar-section-title text-uppercase fw-bold small mb-1 mt-3 px-3">Asistencias</p>',
            html=True,
        )
        self.assertContains(response, 'Registrar asistencia')
        self.assertContains(response, reverse('usuarios:registrar_asistencia_activa'))
        self.assertContains(response, 'Listado asistencia')
        self.assertNotContains(response, 'Justificaciones')
        self.assertNotContains(response, reverse('usuarios:listado_justificaciones'))
        self.assertNotContains(response, 'Configuraci')
        self.assertNotContains(response, 'Registro de logs')
        self.assertNotContains(response, 'Exportar base de datos')
        self.assertNotContains(
            response,
            '<p class="sidebar-section-title text-uppercase fw-bold small mb-1 mt-3 px-3">Socios</p>',
            html=True,
        )
        self.assertNotContains(response, 'Gestionar usuarios')
        self.assertNotContains(response, 'Registrar usuario')
        self.assertNotContains(response, 'Gestionar socios')
        self.assertNotContains(response, 'Registrar socio')

    def test_menu_encargado_redirige_a_registro_de_reunion_activa(self):
        """Permite al encargado abrir el registro operativo desde el menu."""
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
        )
        reunion.iniciar(self.admin_user)

        self.client.login(username='encargado', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:registrar_asistencia_activa'))

        self.assertRedirects(
            response,
            reverse('usuarios:registrar_asistencia_reunion', args=[reunion.pk]),
        )

    def test_menu_encargado_advierte_si_no_hay_reunion_activa(self):
        """Muestra alerta warning cuando no existe reunion activa."""
        self.client.login(username='encargado', password='ClaveSegura123')
        response = self.client.get(
            reverse('usuarios:registrar_asistencia_activa'),
            follow=True,
        )

        self.assertRedirects(response, reverse('usuarios:listado_socios_asistencia'))
        self.assertContains(response, 'data-message-level="warning"')
        self.assertContains(response, 'No hay reuniones activas.')
        self.assertContains(
            response,
            'El registro de asistencia funciona solo al existir reuniones activas.',
        )

    def test_sidebar_socio_solo_muestra_secciones_permitidas(self):
        """Limita el sidebar de socio a asistencias propias y cuenta."""
        self.client.login(username='socio', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:mis_asistencias'))

        self.assertContains(response, 'Mis asistencias')
        self.assertContains(response, 'Mi contrase')
        self.assertNotContains(response, 'Dashboard')
        self.assertNotContains(response, 'Listado usuarios')
        self.assertNotContains(response, 'Registrar usuario')
        self.assertNotContains(response, 'Listado socios')
        self.assertNotContains(response, 'Registrar socio')
        self.assertNotContains(response, 'Registrar asistencia')
        self.assertNotContains(response, 'Listado asistencia')
        self.assertNotContains(response, 'Reuniones')
        self.assertNotContains(response, 'Crear reuni')
        self.assertNotContains(response, 'Configuraci')
        self.assertNotContains(response, 'Registro de logs')
        self.assertNotContains(response, 'Exportar base de datos')

    def test_menu_lateral_admin_separa_socios_y_asistencias(self):
        """Separa gestion de socios y asistencia en secciones del sidebar."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:dashboard'))
        self.assertContains(response, 'Listado usuarios')
        self.assertContains(response, 'Registrar usuario')
        self.assertContains(
            response,
            '<p class="sidebar-section-title text-uppercase fw-bold small mb-1 mt-3 px-3">Socios</p>',
            html=True,
        )
        self.assertContains(response, 'Listado socios')
        self.assertContains(response, 'Registrar socio')
        self.assertContains(
            response,
            '<p class="sidebar-section-title text-uppercase fw-bold small mb-1 mt-3 px-3">Asistencias</p>',
            html=True,
        )
        self.assertContains(response, 'Registrar asistencia')
        self.assertContains(response, 'Listado asistencia')
        self.assertContains(response, 'Justificaciones')
        self.assertContains(response, reverse('usuarios:listado_justificaciones'))
        self.assertContains(response, 'Reuniones')
        self.assertContains(response, 'Crear reuni')
        self.assertContains(response, reverse('usuarios:crear_reunion'))
        self.assertContains(response, 'Listado reuniones')
        self.assertContains(response, reverse('usuarios:listado_reuniones'))
        self.assertContains(response, 'bi-list-ul')
        self.assertContains(response, 'Configuraci')
        self.assertContains(response, reverse('usuarios:configuracion'))
        self.assertContains(response, 'bi-gear')
        self.assertNotContains(response, reverse('usuarios:descargar_registro_logs'))
        self.assertNotContains(response, reverse('usuarios:exportar_base_datos_respaldo'))
        self.assertLess(
            response.content.decode().index('Crear reuni'),
            response.content.decode().index('Listado reuniones'),
        )
        self.assertLess(
            response.content.decode().index('Listado reuniones'),
            response.content.decode().index('Registrar asistencia'),
        )
        self.assertLess(
            response.content.decode().index('Registrar asistencia'),
            response.content.decode().index('Listado socios'),
        )
        self.assertLess(
            response.content.decode().index('Registrar socio'),
            response.content.decode().index('Listado usuarios'),
        )
        self.assertLess(
            response.content.decode().index('Mi contrase'),
            response.content.decode().index('Configuraci'),
        )

    @patch('usuarios.views.obtener_ruta_sqlite_respaldo')
    def test_configuracion_admin_accede_logs_y_respaldo(self, mock_ruta_respaldo):
        """Centraliza descargas de logs y respaldo para el administrador."""
        with NamedTemporaryFile(delete=False, suffix='.sqlite3') as archivo:
            ruta_respaldo = Path(archivo.name)
        conexion = sqlite3.connect(ruta_respaldo)
        try:
            conexion.execute('CREATE TABLE prueba (id INTEGER PRIMARY KEY)')
            conexion.commit()
        finally:
            conexion.close()
        mock_ruta_respaldo.return_value = ruta_respaldo
        with NamedTemporaryFile(delete=False, suffix='.log') as archivo_auditoria:
            archivo_auditoria.write(b'evento-test\n')
            ruta_auditoria = Path(archivo_auditoria.name)

        self.client.login(username='admin', password='ClaveSegura123')

        try:
            with self.settings(AUDITORIA_LOG_PATH=ruta_auditoria):
                response = self.client.get(reverse('usuarios:configuracion'))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'Configuraci')
                self.assertContains(response, 'Registro de logs')
                self.assertContains(response, 'Descargar .log')
                self.assertContains(response, reverse('usuarios:descargar_registro_logs'))
                self.assertContains(response, 'Carga masiva de socios')
                self.assertContains(response, 'Plantilla socios')
                self.assertContains(response, 'Cargar socios')
                self.assertContains(
                    response,
                    reverse('usuarios:descargar_plantilla_carga_masiva_socios'),
                )
                self.assertContains(response, reverse('usuarios:cargar_socios_masivo'))
                self.assertContains(response, 'Respaldo de base de datos')
                self.assertContains(response, 'Respaldar base de datos')
                self.assertContains(response, reverse('usuarios:exportar_base_datos_respaldo'))
                self.assertContains(response, 'Cargas hist')
                self.assertContains(response, 'No hay cargas hist')
                self.assertNotContains(response, '<th>FECHA Y HORA</th>', html=True)
                self.assertNotContains(response, 'evento-test')

                response = self.client.get(reverse('usuarios:registro_logs'))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'Configuraci')
                self.assertContains(response, 'Descargar .log')
                self.assertNotContains(response, '<th>FECHA Y HORA</th>', html=True)

                response = self.client.get(reverse('usuarios:descargar_registro_logs'))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response['Content-Type'], 'text/plain')
                self.assertIn('attachment;', response['Content-Disposition'])
                self.assertIn('.log', response['Content-Disposition'])
                contenido_log = b''.join(response.streaming_content)
                self.assertIn(
                    ACCION_LOG_AUDITORIA_DESCARGADO.encode(),
                    contenido_log,
                )
                response.close()

                response = self.client.get(reverse('usuarios:exportar_base_datos_respaldo'))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response['Content-Type'], 'application/octet-stream')
                self.assertIn('attachment;', response['Content-Disposition'])
                self.assertIn('respaldo_sanramon_', response['Content-Disposition'])
                self.assertIn('.sqlite3.fernet', response['Content-Disposition'])
                self.assertTrue(
                    descifrar_respaldo(response.content).startswith(b'SQLite format 3')
                )

                eventos = leer_eventos_auditoria()
                self.assertEqual(eventos[0]['accion'], ACCION_RESPALDO_BASE_DATOS)
                self.assertEqual(eventos[0]['usuario'], 'admin')
        finally:
            ruta_respaldo.unlink(missing_ok=True)
            ruta_auditoria.unlink(missing_ok=True)
            ruta_auditoria.with_suffix('.log.lock').unlink(missing_ok=True)
            for ruta_rotada in ruta_auditoria.parent.glob(
                f'{ruta_auditoria.stem}-*.log.gz'
            ):
                ruta_rotada.unlink(missing_ok=True)

    def test_configuracion_permite_revertir_carga_historica_por_planilla(self):
        """Revierte todos los registros de una carga historica desde configuracion."""
        reunion = Reunion.objects.create(
            fecha=date(2025, 5, 20),
            hora=time(18, 30),
            locacion='Sede historica',
            creador=self.admin_user,
            estado=Reunion.HISTORICA,
        )
        carga = CargaAsistenciaHistorica.objects.create(
            reunion=reunion,
            cargado_por=self.admin_user,
            archivo_nombre='asistencia.csv',
            total_registros=1,
            total_presentes=1,
            total_ausentes=0,
        )
        AsistenciaReunion.objects.create(
            reunion=reunion,
            socio=self.socio_user,
            estado=AsistenciaReunion.PRESENTE,
            origen=AsistenciaReunion.ORIGEN_MANUAL,
            registrada_por=self.admin_user,
            carga_historica=carga,
        )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:configuracion'))

        self.assertContains(response, 'Cargas hist')
        self.assertContains(response, 'asistencia.csv')
        self.assertContains(response, 'Revertir carga')
        self.assertContains(
            response,
            reverse('usuarios:revertir_carga_asistencia_historica', args=[carga.pk]),
        )

        response = self.client.post(
            reverse('usuarios:revertir_carga_asistencia_historica', args=[carga.pk]),
            follow=True,
        )
        carga.refresh_from_db()

        self.assertRedirects(response, reverse('usuarios:configuracion'))
        self.assertContains(response, 'Carga historica revertida correctamente')
        self.assertEqual(AsistenciaReunion.objects.filter(reunion=reunion).count(), 0)
        self.assertTrue(carga.revertida)
        self.assertEqual(carga.revertida_por, self.admin_user)
        self.assertEqual(carga.registros_revertidos, 1)
        self.assertEqual(leer_eventos_auditoria()[0]['accion'], ACCION_CARGA_HISTORICA_REVERTIDA)

    def test_configuracion_bloquea_revertir_carga_historica_con_justificaciones(self):
        """Evita borrar asistencias de una carga si ya tienen justificacion."""
        reunion = Reunion.objects.create(
            fecha=date(2025, 5, 20),
            hora=time(18, 30),
            locacion='Sede historica',
            creador=self.admin_user,
            estado=Reunion.HISTORICA,
        )
        carga = CargaAsistenciaHistorica.objects.create(
            reunion=reunion,
            cargado_por=self.admin_user,
            archivo_nombre='asistencia.csv',
            total_registros=1,
            total_presentes=0,
            total_ausentes=1,
        )
        asistencia = AsistenciaReunion.objects.create(
            reunion=reunion,
            socio=self.socio_user,
            estado=AsistenciaReunion.AUSENTE,
            origen=AsistenciaReunion.ORIGEN_MANUAL,
            registrada_por=self.admin_user,
            carga_historica=carga,
        )
        DesbloqueoSocio.objects.create(
            socio=self.socio_user,
            asistencia=asistencia,
            motivo='Correccion revisada',
            desbloqueado_por=self.admin_user,
            inasistencias_al_desbloquear=1,
        )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:revertir_carga_asistencia_historica', args=[carga.pk]),
            follow=True,
        )
        carga.refresh_from_db()

        self.assertRedirects(response, reverse('usuarios:configuracion'))
        self.assertContains(response, 'No se puede revertir una carga con justificaciones')
        self.assertEqual(AsistenciaReunion.objects.filter(reunion=reunion).count(), 1)
        self.assertFalse(carga.revertida)

    def test_configuracion_restringe_encargado_y_socio(self):
        """Bloquea opciones criticas de configuracion fuera del rol administrador."""
        reunion = Reunion.objects.create(
            fecha=date(2025, 5, 20),
            hora=time(18, 30),
            locacion='Sede historica',
            creador=self.admin_user,
            estado=Reunion.HISTORICA,
        )
        carga = CargaAsistenciaHistorica.objects.create(
            reunion=reunion,
            cargado_por=self.admin_user,
        )

        self.client.login(username='encargado', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:configuracion'))
        self.assertRedirects(response, reverse('usuarios:dashboard'))
        response = self.client.get(reverse('usuarios:descargar_registro_logs'))
        self.assertRedirects(response, reverse('usuarios:dashboard'))
        response = self.client.get(reverse('usuarios:exportar_base_datos_respaldo'))
        self.assertRedirects(response, reverse('usuarios:dashboard'))
        response = self.client.get(reverse('usuarios:descargar_plantilla_carga_masiva_socios'))
        self.assertRedirects(response, reverse('usuarios:dashboard'))
        response = self.client.get(reverse('usuarios:cargar_socios_masivo'))
        self.assertRedirects(response, reverse('usuarios:dashboard'))
        response = self.client.post(
            reverse('usuarios:revertir_carga_asistencia_historica', args=[carga.pk]),
        )
        self.assertRedirects(response, reverse('usuarios:dashboard'))

        self.client.login(username='socio', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:configuracion'))
        self.assertRedirects(response, reverse('usuarios:mis_asistencias'))
        response = self.client.get(reverse('usuarios:descargar_registro_logs'))
        self.assertRedirects(response, reverse('usuarios:mis_asistencias'))
        response = self.client.get(reverse('usuarios:exportar_base_datos_respaldo'))
        self.assertRedirects(response, reverse('usuarios:mis_asistencias'))
        response = self.client.get(reverse('usuarios:descargar_plantilla_carga_masiva_socios'))
        self.assertRedirects(response, reverse('usuarios:mis_asistencias'))
        response = self.client.get(reverse('usuarios:cargar_socios_masivo'))
        self.assertRedirects(response, reverse('usuarios:mis_asistencias'))
        response = self.client.post(
            reverse('usuarios:revertir_carga_asistencia_historica', args=[carga.pk]),
        )
        self.assertRedirects(response, reverse('usuarios:mis_asistencias'))

    def test_auditoria_registra_acciones_criticas_en_auditoria_log(self):
        """Registra eventos criticos en auditoria.log con actor y entidad."""
        with NamedTemporaryFile(delete=False, suffix='.log') as archivo_auditoria:
            ruta_auditoria = Path(archivo_auditoria.name)

        self.client.login(username='admin', password='ClaveSegura123')

        try:
            with self.settings(AUDITORIA_LOG_PATH=ruta_auditoria):
                self.client.post(
                    reverse('usuarios:cambiar_estado_usuario', args=[self.encargado_user.pk]),
                )

                reunion_cancelada = Reunion.objects.create(
                    fecha=date(2026, 5, 20),
                    hora=time(18, 30),
                    locacion='Sede social',
                    creador=self.admin_user,
                )
                self.client.post(
                    reverse('usuarios:cancelar_reunion', args=[reunion_cancelada.pk]),
                    {'motivo_cancelacion': 'Suspension administrativa'},
                )

                reunion_eliminada = Reunion.objects.create(
                    fecha=date(2026, 6, 20),
                    hora=time(18, 30),
                    locacion='Sede social',
                    creador=self.admin_user,
                )
                self.client.post(
                    reverse('usuarios:eliminar_reunion', args=[reunion_eliminada.pk]),
                )

                usuario_borrable = self.User.objects.create_user(
                    username='usuario.borrable',
                    email='usuario.borrable@example.com',
                    password='ClaveSegura123',
                    first_name='Usuario',
                    last_name='Borrable',
                    rut='55.555.555-5',
                    rol=self.User.ENCARGADO_REGISTRO,
                )
                self.client.post(
                    reverse('usuarios:eliminar_usuario', args=[usuario_borrable.pk]),
                )

                socio_borrable = self.User.objects.create_user(
                    username='socio.borrable',
                    email='socio.borrable@example.com',
                    password='ClaveSegura123',
                    first_name='Socio',
                    last_name='Borrable',
                    rut='66.666.666-6',
                    rol=self.User.SOCIO,
                )
                self.client.post(
                    reverse('usuarios:eliminar_socio', args=[socio_borrable.pk]),
                )

                eventos = leer_eventos_auditoria()
                acciones = {evento['accion'] for evento in eventos}

                self.assertEqual(len(eventos), 5)
                self.assertIn(ACCION_USUARIO_DESACTIVADO, acciones)
                self.assertIn(ACCION_REUNION_CANCELADA, acciones)
                self.assertIn(ACCION_REUNION_ELIMINADA, acciones)
                self.assertIn(ACCION_USUARIO_ELIMINADO, acciones)
                self.assertIn(ACCION_SOCIO_ELIMINADO, acciones)
                for evento in eventos:
                    self.assertEqual(evento['usuario'], 'admin')
                    self.assertTrue(evento['entidad_tipo'])
                    self.assertTrue(evento['entidad'])
                    self.assertTrue(evento['fecha_hora'])

                response = self.client.get(reverse('usuarios:configuracion'))
                self.assertContains(response, 'Registro de logs')
                self.assertNotContains(response, 'Usuario desactivado')
                self.assertNotContains(response, 'Reunion cancelada')
                self.assertNotContains(response, 'Reunion eliminada')
                self.assertNotContains(response, 'Usuario eliminado')
                self.assertNotContains(response, 'Socio eliminado')
                self.assertNotContains(response, 'Suspension administrativa')

                response = self.client.get(reverse('usuarios:descargar_registro_logs'))
                contenido_log = b''.join(response.streaming_content).decode('utf-8')
                response.close()
                self.assertIn(ACCION_USUARIO_DESACTIVADO, contenido_log)
                self.assertIn(ACCION_REUNION_CANCELADA, contenido_log)
                self.assertIn(ACCION_REUNION_ELIMINADA, contenido_log)
                self.assertIn(ACCION_USUARIO_ELIMINADO, contenido_log)
                self.assertIn(ACCION_SOCIO_ELIMINADO, contenido_log)
                self.assertIn('Suspension administrativa', contenido_log)
        finally:
            ruta_auditoria.unlink(missing_ok=True)
            ruta_auditoria.with_suffix('.log.lock').unlink(missing_ok=True)
            for ruta_rotada in ruta_auditoria.parent.glob(
                f'{ruta_auditoria.stem}-*.log.gz'
            ):
                ruta_rotada.unlink(missing_ok=True)

    def test_auditoria_detecta_alteracion_y_rota_archivo(self):
        """Firma eventos, detecta manipulacion y preserva el archivo observado."""
        with NamedTemporaryFile(delete=False, suffix='.log') as archivo:
            ruta_auditoria = Path(archivo.name)

        try:
            with self.settings(AUDITORIA_LOG_PATH=ruta_auditoria):
                registrar_evento_auditoria(
                    self.admin_user,
                    ACCION_USUARIO_DESACTIVADO,
                    entidad_tipo='Usuario',
                    entidad_id=self.encargado_user.pk,
                    entidad='Usuario interno',
                )
                self.assertTrue(verificar_integridad_archivo(ruta_auditoria))

                contenido = ruta_auditoria.read_text(encoding='utf-8')
                ruta_auditoria.write_text(
                    contenido.replace(
                        ACCION_USUARIO_DESACTIVADO,
                        ACCION_USUARIO_ELIMINADO,
                        1,
                    ),
                    encoding='utf-8',
                )
                self.assertFalse(verificar_integridad_archivo(ruta_auditoria))

                registrar_evento_auditoria(
                    self.admin_user,
                    ACCION_USUARIO_ACTIVADO,
                    entidad_tipo='Usuario',
                    entidad_id=self.encargado_user.pk,
                    entidad='Usuario interno',
                )
                archivos = listar_archivos_auditoria()
                actual = next(item for item in archivos if item['id'] == 'actual')
                historicos = [item for item in archivos if item['id'] != 'actual']
                self.assertTrue(actual['integridad_valida'])
                self.assertEqual(len(historicos), 1)
                self.assertFalse(historicos[0]['integridad_valida'])
                self.assertTrue(historicos[0]['comprimido'])
        finally:
            ruta_auditoria.unlink(missing_ok=True)
            ruta_auditoria.with_suffix('.log.lock').unlink(missing_ok=True)
            for ruta_rotada in ruta_auditoria.parent.glob(
                f'{ruta_auditoria.stem}-*.log.gz'
            ):
                ruta_rotada.unlink(missing_ok=True)

    @patch('usuarios.forms.timezone.localtime', return_value=datetime(2026, 5, 14, 12, 0))
    def test_crear_reunion_solo_disponible_para_administrador(self, _localtime):
        """Protege la entrada inicial de creacion de reuniones."""
        url = reverse('usuarios:crear_reunion')

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Crear reuni')
        self.assertNotContains(response, 'Control de reuniones programadas y activas.')
        self.assertNotContains(response, '<th>FECHA</th>', html=True)
        self.assertNotContains(response, '/reuniones/1/iniciar/')
        self.assertContains(response, 'name="fecha"')
        self.assertContains(response, 'data-reunion-date="true"')
        self.assertContains(response, 'data-today="2026-05-14"')
        self.assertContains(response, 'name="hora"')
        self.assertContains(response, 'type="time"')
        self.assertContains(response, 'lang="es-CL"')
        self.assertContains(response, 'min="00:00"')
        self.assertContains(response, 'max="23:59"')
        self.assertContains(response, 'step="60"')
        self.assertContains(response, 'pattern="([01][0-9]|2[0-3]):[0-5][0-9]"')
        self.assertContains(response, 'data-reunion-time="true"')
        self.assertContains(response, 'data-current-time="12:00"')
        self.assertContains(response, 'name="locacion"')
        self.assertContains(response, 'Locaci')
        self.assertContains(response, 'name="estado"')
        self.assertContains(response, 'class="col-md-4"')
        self.assertContains(response, 'class="col-md-8 col-lg-6"')
        self.assertContains(response, 'data-reunion-status="true"')
        self.assertContains(response, 'data-historical-value="HISTORICA"')
        self.assertContains(response, 'js/reuniones.js')
        self.assertContains(response, 'Hist')
        self.assertContains(response, 'Plantilla CSV')
        self.assertContains(response, 'Plantilla CSV para carga hist')
        self.assertContains(response, '12345678-9')
        self.assertContains(response, 'A/a para Ausente')
        self.assertContains(response, 'P/p para Presente')
        self.assertContains(response, 'Situaci')
        self.assertContains(
            response,
            reverse('usuarios:descargar_plantilla_asistencia_historica_csv'),
        )
        contenido = response.content.decode()
        self.assertLess(
            contenido.index('name="locacion"'),
            contenido.index('data-reunion-status="true"'),
        )
        self.assertLess(
            contenido.index('data-reunion-status="true"'),
            contenido.index('Plantilla CSV'),
        )
        self.assertLess(
            contenido.index('Plantilla CSV'),
            contenido.index('Plantilla CSV para carga hist'),
        )

        response = self.client.post(
            url,
            {
                'fecha': '2026-05-20',
                'hora': '18:30',
                'locacion': 'Sede social',
                'estado': Reunion.PROGRAMADA,
            },
            follow=True,
        )
        self.assertRedirects(response, reverse('usuarios:listado_reuniones'))
        self.assertContains(response, 'creada correctamente')
        reunion = Reunion.objects.get(locacion='Sede social')
        self.assertEqual(reunion.creador, self.admin_user)
        self.assertEqual(reunion.estado, Reunion.PROGRAMADA)

        self.client.login(username='encargado', password='ClaveSegura123')
        response = self.client.get(url)
        self.assertRedirects(response, reverse('usuarios:dashboard'))

        self.client.login(username='socio', password='ClaveSegura123')
        response = self.client.get(url)
        self.assertRedirects(response, reverse('usuarios:mis_asistencias'))

    @patch('usuarios.forms.timezone.localtime', return_value=datetime(2026, 5, 14, 12, 0))
    def test_crear_reunion_muestra_alerta_si_fecha_hora_duplicada(self, _localtime):
        """Informa al administrador cuando intenta duplicar una reunion."""
        url = reverse('usuarios:crear_reunion')
        Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
        )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.post(
            url,
            {
                'fecha': '2026-05-20',
                'hora': '18:30',
                'locacion': 'Sede norte',
                'estado': Reunion.PROGRAMADA,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, ReunionCreationForm.REUNION_DUPLICADA_MENSAJE)
        self.assertContains(response, 'data-message-level="warning"')
        self.assertEqual(Reunion.objects.count(), 1)

    @patch('usuarios.forms.timezone.localtime', return_value=datetime(2026, 5, 14, 12, 0))
    def test_crear_reunion_muestra_alerta_si_reunion_pasada_no_es_historica(self, _localtime):
        """Alerta cuando una reunion anterior al momento actual no se marca historica."""
        url = reverse('usuarios:crear_reunion')

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.post(
            url,
            {
                'fecha': '2026-05-14',
                'hora': '11:30',
                'locacion': 'Sede social',
                'estado': Reunion.PROGRAMADA,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, ReunionCreationForm.REUNION_PASADA_HISTORICA_MENSAJE)
        self.assertContains(response, 'data-message-level="warning"')
        self.assertEqual(Reunion.objects.count(), 0)

    @patch('usuarios.models.timezone.now')
    def test_administrador_inicia_reunion_programada(self, now_mock):
        """Permite habilitar asistencia cambiando la reunion a activa."""
        momento = datetime(2026, 5, 20, 18, 35, tzinfo=timezone.get_current_timezone())
        now_mock.return_value = momento
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
        )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:listado_reuniones'))
        self.assertContains(response, 'Listado reuniones')
        self.assertContains(response, reverse('usuarios:iniciar_reunion', args=[reunion.pk]))
        self.assertContains(response, 'Iniciar')

        response = self.client.post(
            reverse('usuarios:iniciar_reunion', args=[reunion.pk]),
            follow=True,
        )

        self.assertRedirects(response, reverse('usuarios:listado_reuniones'))
        self.assertContains(response, 'iniciada correctamente')
        self.assertContains(response, 'Activa')
        reunion.refresh_from_db()
        self.assertEqual(reunion.estado, Reunion.ACTIVA)
        self.assertEqual(reunion.activada_por, self.admin_user)
        self.assertEqual(reunion.fecha_activacion, momento)

    def test_iniciar_reunion_bloquea_si_ya_existe_activa(self):
        """Evita iniciar una segunda reunion cuando ya hay una activa."""
        activa = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
        )
        activa.iniciar(self.admin_user)
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 21),
            hora=time(18, 30),
            locacion='Sede norte',
            creador=self.admin_user,
        )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:iniciar_reunion', args=[reunion.pk]),
            follow=True,
        )

        self.assertRedirects(response, reverse('usuarios:listado_reuniones'))
        self.assertContains(response, 'Ya existe una reunion activa.')
        reunion.refresh_from_db()
        self.assertEqual(reunion.estado, Reunion.PROGRAMADA)
        self.assertEqual(Reunion.objects.filter(estado=Reunion.ACTIVA).count(), 1)

    def test_iniciar_reunion_bloquea_reunion_historica(self):
        """Impide iniciar reuniones historicas desde la vista."""
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
            estado=Reunion.HISTORICA,
        )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:iniciar_reunion', args=[reunion.pk]),
            follow=True,
        )

        self.assertRedirects(response, reverse('usuarios:listado_reuniones'))
        self.assertContains(response, 'Solo se pueden iniciar reuniones programadas.')
        reunion.refresh_from_db()
        self.assertEqual(reunion.estado, Reunion.HISTORICA)

    def test_listado_reuniones_solo_disponible_para_administrador(self):
        """Protege el listado operativo de reuniones."""
        url = reverse('usuarios:listado_reuniones')

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Listado reuniones')
        self.assertContains(response, 'No hay reuniones registradas.')
        self.assertContains(response, reverse('usuarios:crear_reunion'))
        self.assertContains(response, 'd-none d-md-block')
        self.assertContains(response, 'list-group shadow-sm border rounded overflow-hidden d-md-none')
        self.assertNotContains(response, 'Limpiar pruebas')

        self.client.login(username='encargado', password='ClaveSegura123')
        response = self.client.get(url)
        self.assertRedirects(response, reverse('usuarios:dashboard'))

        self.client.login(username='socio', password='ClaveSegura123')
        response = self.client.get(url)
        self.assertRedirects(response, reverse('usuarios:mis_asistencias'))

    def test_listado_reuniones_filtra_por_anio(self):
        """Permite acotar el listado de reuniones por ano calendario."""
        reunion_2026 = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede 2026',
            creador=self.admin_user,
        )
        Reunion.objects.create(
            fecha=date(2025, 5, 20),
            hora=time(18, 30),
            locacion='Sede 2025',
            creador=self.admin_user,
            estado=Reunion.HISTORICA,
        )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(
            reverse('usuarios:listado_reuniones'),
            {'anio': '2026'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="filtro-reunion-anio"')
        self.assertContains(response, '<option value="2026" selected>2026</option>', html=True)
        self.assertContains(response, '<option value="2025" >2025</option>', html=True)
        self.assertContains(response, 'Sede 2026')
        self.assertNotContains(response, 'Sede 2025')
        self.assertContains(response, reverse('usuarios:listado_reuniones'))
        self.assertContains(response, 'Limpiar')

        response = self.client.get(
            reverse('usuarios:listado_reuniones'),
            {'anio': '2030'},
        )

        self.assertContains(response, 'Sede 2026')
        self.assertContains(response, 'Sede 2025')
        self.assertEqual(
            list(response.context['anios_reuniones']),
            [2026, 2025],
        )
        self.assertEqual(response.context['anio_actual'], '')
        self.assertIn(reunion_2026, response.context['reuniones'])

    def test_listado_reuniones_activa_carga_solo_en_historicas(self):
        """Expone carga historica solo para reuniones en estado historico."""
        reunion_historica = Reunion.objects.create(
            fecha=date(2025, 5, 20),
            hora=time(18, 30),
            locacion='Sede historica',
            creador=self.admin_user,
            estado=Reunion.HISTORICA,
        )
        reunion_programada = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede programada',
            creador=self.admin_user,
        )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:listado_reuniones'))

        self.assertContains(response, 'Carga hist')
        self.assertContains(
            response,
            reverse('usuarios:cargar_asistencia_historica', args=[reunion_historica.pk]),
        )
        self.assertNotContains(
            response,
            reverse('usuarios:cargar_asistencia_historica', args=[reunion_programada.pk]),
        )

    def test_listado_reuniones_reemplaza_carga_historica_si_ya_tiene_registros(self):
        """Oculta carga historica y muestra badge cuando la reunion ya fue cargada."""
        reunion_cargada = Reunion.objects.create(
            fecha=date(2025, 5, 20),
            hora=time(18, 30),
            locacion='Sede historica cargada',
            creador=self.admin_user,
            estado=Reunion.HISTORICA,
        )
        reunion_pendiente = Reunion.objects.create(
            fecha=date(2025, 5, 21),
            hora=time(18, 30),
            locacion='Sede historica pendiente',
            creador=self.admin_user,
            estado=Reunion.HISTORICA,
        )
        AsistenciaReunion.objects.create(
            reunion=reunion_cargada,
            socio=self.socio_user,
            estado=AsistenciaReunion.PRESENTE,
            origen=AsistenciaReunion.ORIGEN_MANUAL,
            registrada_por=self.admin_user,
        )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:listado_reuniones'))

        self.assertContains(response, 'Cargada manualmente')
        self.assertContains(response, 'data-bs-toggle="tooltip"')
        self.assertContains(response, 'RUT del usuario y la fecha correspondiente')
        self.assertNotContains(
            response,
            reverse('usuarios:cargar_asistencia_historica', args=[reunion_cargada.pk]),
        )
        self.assertContains(
            response,
            reverse('usuarios:cargar_asistencia_historica', args=[reunion_pendiente.pk]),
        )

    def test_listado_reuniones_muestra_badge_si_carga_historica_fue_revertida(self):
        """Muestra estado revertido y permite cargar nuevamente una planilla."""
        reunion = Reunion.objects.create(
            fecha=date(2025, 5, 20),
            hora=time(18, 30),
            locacion='Sede historica revertida',
            creador=self.admin_user,
            estado=Reunion.HISTORICA,
        )
        CargaAsistenciaHistorica.objects.create(
            reunion=reunion,
            cargado_por=self.admin_user,
            total_registros=2,
            total_presentes=1,
            total_ausentes=1,
            revertida=True,
            revertida_por=self.admin_user,
            fecha_reversion=timezone.now(),
            registros_revertidos=2,
        )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:listado_reuniones'))

        self.assertContains(response, 'Reuni&oacute;n revertida')
        self.assertContains(response, 'La carga anterior fue revertida')
        self.assertNotContains(
            response,
            reverse('usuarios:cargar_asistencia_historica', args=[reunion.pk]),
        )
        self.assertNotContains(response, 'Cargada manualmente')

    def test_plantilla_asistencia_historica_descarga_xlsx_base(self):
        """Propone una plantilla XLSX exportable a CSV para la carga historica."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(
            reverse('usuarios:descargar_plantilla_asistencia_historica'),
        )

        with zipfile.ZipFile(BytesIO(response.content)) as archivo:
            worksheet = archivo.read('xl/worksheets/sheet1.xml').decode('utf-8')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        self.assertIn('attachment;', response['Content-Disposition'])
        self.assertIn('plantilla_asistencia_historica.xlsx', response['Content-Disposition'])
        self.assertIn('RUT', worksheet)
        self.assertIn('Situaci', worksheet)
        self.assertNotIn('Nombre', worksheet)
        self.assertIn(self.socio_user.rut, worksheet)

    def test_plantilla_asistencia_historica_descarga_csv_encabezados(self):
        """Entrega CSV de referencia con encabezados para carga historica."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(
            reverse('usuarios:descargar_plantilla_asistencia_historica_csv'),
        )
        filas = list(csv.reader(StringIO(response.content.decode('utf-8-sig'))))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv; charset=utf-8')
        self.assertIn('attachment;', response['Content-Disposition'])
        self.assertIn('plantilla_asistencia_historica.csv', response['Content-Disposition'])
        self.assertEqual(
            filas,
            [['RUT', 'Situaci\u00f3n']],
        )

    def test_plantilla_carga_masiva_socios_descarga_csv_con_socios_actuales(self):
        """Entrega CSV con encabezados de carga masiva y socios actuales."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(
            reverse('usuarios:descargar_plantilla_carga_masiva_socios'),
        )
        filas = list(csv.reader(StringIO(response.content.decode('utf-8-sig'))))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv; charset=utf-8')
        self.assertIn('attachment;', response['Content-Disposition'])
        self.assertIn('plantilla_carga_masiva_socios.csv', response['Content-Disposition'])
        self.assertEqual(
            filas[0],
            [
                'nombre',
                'apellido_paterno',
                'apellido_materno',
                'rut',
                'correo_electronico',
                'telefono_movil',
                'fecha_ingreso_proyecto',
            ],
        )
        self.assertIn(
            [
                'Socio',
                'Prueba',
                '',
                self.socio_user.rut,
                'socio@example.com',
                '+56922222222',
                self.socio_user.fecha_ingreso_proyecto.isoformat(),
            ],
            filas,
        )
        self.assertNotIn('admin@example.com', response.content.decode('utf-8-sig'))

    def test_carga_masiva_socios_csv_crea_socios_sin_password(self):
        """Crea socios en lote desde CSV y registra auditoria del lote."""
        rut_nuevo = self.rut_prueba('70000001')
        archivo = SimpleUploadedFile(
            'socios.csv',
            (
                'sep=;\n'
                'nombre;apellido_paterno;apellido_materno;rut;correo_electronico;telefono_movil;fecha_ingreso_proyecto\n'
                f'Nuevo;Masivo;Uno;{rut_nuevo};NUEVO.MASIVO@example.com;56933333333;2026-05-15\n'
            ).encode('utf-8'),
            content_type='text/csv',
        )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:cargar_socios_masivo'),
            {'archivo': archivo},
            follow=True,
        )

        self.assertRedirects(response, reverse('usuarios:listado_socios'))
        self.assertContains(response, 'Carga masiva completada. Socios creados: 1.')
        socio = self.User.objects.get(email='nuevo.masivo@example.com')
        self.assertEqual(socio.username, 'nuevo.masivo@example.com')
        self.assertEqual(socio.rol, self.User.SOCIO)
        self.assertEqual(socio.rut, rut_nuevo)
        self.assertEqual(socio.telefono_movil, '+56933333333')
        self.assertEqual(socio.fecha_ingreso_proyecto, date(2026, 5, 15))
        self.assertFalse(socio.has_usable_password())
        evento = leer_eventos_auditoria()[0]
        self.assertEqual(evento['accion'], ACCION_CARGA_MASIVA_SOCIOS)
        self.assertNotIn('socios.csv', evento['detalle'])

    def test_carga_csv_rechaza_tamano_tipo_y_contenido_binario(self):
        """Aplica controles previos antes de procesar una planilla."""
        self.client.login(username='admin', password='ClaveSegura123')
        url = reverse('usuarios:cargar_socios_masivo')

        with self.settings(CARGA_CSV_MAX_BYTES=16):
            response = self.client.post(
                url,
                {
                    'archivo': SimpleUploadedFile(
                        'socios.csv',
                        b'columna1,columna2\nvalor1,valor2\n',
                        content_type='text/csv',
                    )
                },
            )
        self.assertContains(response, 'máximo permitido')

        response = self.client.post(
            url,
            {
                'archivo': SimpleUploadedFile(
                    'socios.csv',
                    b'columna1,columna2\nvalor1,valor2\n',
                    content_type='application/pdf',
                )
            },
        )
        self.assertContains(response, 'tipo de contenido')

        response = self.client.post(
            url,
            {
                'archivo': SimpleUploadedFile(
                    'socios.csv',
                    b'columna1,columna2\nvalor\x00,valor2\n',
                    content_type='text/csv',
                )
            },
        )
        self.assertContains(response, 'datos binarios')

    def test_carga_masiva_socios_csv_rollback_por_error(self):
        """No crea ningun socio si una fila de la planilla contiene errores."""
        rut_valido = self.rut_prueba('70000002')
        archivo = SimpleUploadedFile(
            'socios.csv',
            (
                'nombre,apellido_paterno,apellido_materno,rut,correo_electronico,telefono_movil,fecha_ingreso_proyecto\n'
                f'Valido,Lote,Uno,{rut_valido},valido.lote@example.com,+56933333333,2026-05-15\n'
                f'Duplicado,Lote,Dos,{self.socio_user.rut},duplicado.lote@example.com,+56944444444,2026-05-15\n'
            ).encode('utf-8'),
            content_type='text/csv',
        )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:cargar_socios_masivo'),
            {'archivo': archivo},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Errores de la planilla')
        self.assertContains(response, 'No se creo ningun socio')
        self.assertContains(response, 'Ya existe un usuario con este RUT.')
        self.assertFalse(self.User.objects.filter(email='valido.lote@example.com').exists())
        self.assertFalse(self.User.objects.filter(email='duplicado.lote@example.com').exists())

    def test_carga_asistencia_historica_csv_semicolon_registro_por_registro(self):
        """Carga asistencia historica desde CSV separado por punto y coma."""
        socio_ausente = self.User.objects.create_user(
            username='socio.ausente',
            email='socio.ausente@example.com',
            password='ClaveSegura123',
            first_name='Socio',
            last_name='Ausente',
            rut='77.777.777-7',
            rol=self.User.SOCIO,
        )
        reunion = Reunion.objects.create(
            fecha=date(2025, 5, 20),
            hora=time(18, 30),
            locacion='Sede historica',
            creador=self.admin_user,
            estado=Reunion.HISTORICA,
        )
        archivo = SimpleUploadedFile(
            'asistencia.csv',
            (
                'sep=;\n'
                'RUT;Situaci\u00f3n\n'
                f'{self.socio_user.rut};p\n'
                f'{socio_ausente.rut};A\n'
            ).encode('utf-8'),
            content_type='text/csv',
        )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:cargar_asistencia_historica', args=[reunion.pk]),
            {'archivo': archivo},
            follow=True,
        )

        self.assertRedirects(response, reverse('usuarios:listado_reuniones'))
        self.assertContains(response, 'Carga historica completada')
        asistencias = AsistenciaReunion.objects.filter(reunion=reunion).order_by('socio_id')
        self.assertEqual(asistencias.count(), 2)
        carga = CargaAsistenciaHistorica.objects.get(reunion=reunion)
        self.assertEqual(carga.cargado_por, self.admin_user)
        self.assertRegex(carga.archivo_nombre, r'^CSV-[0-9a-f]{16}$')
        self.assertNotEqual(carga.archivo_nombre, 'asistencia.csv')
        self.assertEqual(carga.total_registros, 2)
        self.assertEqual(carga.total_presentes, 1)
        self.assertEqual(carga.total_ausentes, 1)
        self.assertEqual(asistencias.filter(carga_historica=carga).count(), 2)
        self.assertEqual(
            leer_eventos_auditoria()[0]['accion'],
            ACCION_CARGA_HISTORICA,
        )
        self.assertTrue(
            asistencias.filter(
                socio=self.socio_user,
                estado=AsistenciaReunion.PRESENTE,
                origen=AsistenciaReunion.ORIGEN_MANUAL,
                registrada_por=self.admin_user,
            ).exists()
        )
        self.assertTrue(
            asistencias.filter(
                socio=socio_ausente,
                estado=AsistenciaReunion.AUSENTE,
                origen=AsistenciaReunion.ORIGEN_MANUAL,
                registrada_por=self.admin_user,
            ).exists()
        )

    def test_carga_asistencia_historica_csv_coma_y_rollback_por_error(self):
        """Revierte toda la carga si una fila CSV no cumple reglas de negocio."""
        reunion = Reunion.objects.create(
            fecha=date(2025, 5, 20),
            hora=time(18, 30),
            locacion='Sede historica',
            creador=self.admin_user,
            estado=Reunion.HISTORICA,
        )
        archivo = SimpleUploadedFile(
            'asistencia.csv',
            (
                'RUT,Estado\n'
                f'{self.socio_user.rut},Presente\n'
                '99.999.999-9,Presente\n'
            ).encode('utf-8'),
            content_type='text/csv',
        )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:cargar_asistencia_historica', args=[reunion.pk]),
            {'archivo': archivo},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Fila 3')
        self.assertContains(response, 'socio no encontrado')
        self.assertEqual(AsistenciaReunion.objects.filter(reunion=reunion).count(), 0)

    def test_carga_asistencia_historica_bloquea_reuniones_no_historicas(self):
        """Impide cargar CSV en reuniones programadas, activas o cerradas."""
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede programada',
            creador=self.admin_user,
        )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(
            reverse('usuarios:cargar_asistencia_historica', args=[reunion.pk]),
            follow=True,
        )

        self.assertRedirects(response, reverse('usuarios:listado_reuniones'))
        self.assertContains(
            response,
            'La carga historica solo esta disponible para reuniones historicas.',
        )

    def test_carga_asistencia_historica_bloquea_reuniones_ya_cargadas(self):
        """Impide volver a cargar CSV cuando una historica ya tiene asistencias."""
        reunion = Reunion.objects.create(
            fecha=date(2025, 5, 20),
            hora=time(18, 30),
            locacion='Sede historica',
            creador=self.admin_user,
            estado=Reunion.HISTORICA,
        )
        AsistenciaReunion.objects.create(
            reunion=reunion,
            socio=self.socio_user,
            estado=AsistenciaReunion.PRESENTE,
            origen=AsistenciaReunion.ORIGEN_MANUAL,
            registrada_por=self.admin_user,
        )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(
            reverse('usuarios:cargar_asistencia_historica', args=[reunion.pk]),
            follow=True,
        )

        self.assertRedirects(response, reverse('usuarios:listado_reuniones'))
        self.assertContains(response, 'ya fue registrada manualmente')
        self.assertContains(response, 'RUT del usuario y la fecha correspondiente')

    def test_carga_asistencia_historica_bloquea_reuniones_revertidas(self):
        """Impide cargar planilla nuevamente si la carga historica fue revertida."""
        reunion = Reunion.objects.create(
            fecha=date(2025, 5, 20),
            hora=time(18, 30),
            locacion='Sede historica',
            creador=self.admin_user,
            estado=Reunion.HISTORICA,
        )
        CargaAsistenciaHistorica.objects.create(
            reunion=reunion,
            cargado_por=self.admin_user,
            revertida=True,
            revertida_por=self.admin_user,
            fecha_reversion=timezone.now(),
            registros_revertidos=2,
        )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(
            reverse('usuarios:cargar_asistencia_historica', args=[reunion.pk]),
            follow=True,
        )

        self.assertRedirects(response, reverse('usuarios:listado_reuniones'))
        self.assertContains(response, 'fue revertida')
        self.assertContains(response, 'no admite una nueva carga')

    def test_administrador_elimina_reunion_sin_asistencias(self):
        """Permite eliminar reuniones, incluidas historicas, sin asistencias."""
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
            estado=Reunion.HISTORICA,
        )
        url_eliminar = reverse('usuarios:eliminar_reunion', args=[reunion.pk])

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:listado_reuniones'))
        self.assertContains(response, url_eliminar)
        self.assertContains(response, 'aria-label="Eliminar reuni')

        response = self.client.post(url_eliminar, follow=True)

        self.assertRedirects(response, reverse('usuarios:listado_reuniones'))
        self.assertContains(response, 'eliminada correctamente')
        self.assertFalse(Reunion.objects.filter(pk=reunion.pk).exists())

    def test_eliminar_reunion_bloquea_si_tiene_asistencias(self):
        """Impide eliminar reuniones con asistencias registradas."""
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
        )
        reunion.iniciar(self.admin_user)
        AsistenciaReunion.registrar_presente(
            reunion=reunion,
            socio=self.socio_user,
            usuario=self.encargado_user,
            origen=AsistenciaReunion.ORIGEN_RUT,
        )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:listado_reuniones'))
        self.assertContains(response, 'Eliminar reuni&oacute;n no disponible')
        response = self.client.post(
            reverse('usuarios:eliminar_reunion', args=[reunion.pk]),
            follow=True,
        )

        self.assertRedirects(response, reverse('usuarios:listado_reuniones'))
        self.assertContains(response, 'Solo se pueden eliminar reuniones sin asistencias registradas.')
        self.assertTrue(Reunion.objects.filter(pk=reunion.pk).exists())

    def test_eliminar_reunion_solo_disponible_para_administrador(self):
        """Protege la eliminacion de reuniones para usuarios sin permisos."""
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
        )
        url = reverse('usuarios:eliminar_reunion', args=[reunion.pk])

        self.client.login(username='encargado', password='ClaveSegura123')
        response = self.client.post(url)
        self.assertRedirects(response, reverse('usuarios:dashboard'))

        self.client.login(username='socio', password='ClaveSegura123')
        response = self.client.post(url)
        self.assertRedirects(response, reverse('usuarios:mis_asistencias'))

        self.assertTrue(Reunion.objects.filter(pk=reunion.pk).exists())

    def test_iniciar_reunion_solo_disponible_para_administrador(self):
        """Protege la accion de inicio con los mismos permisos de reuniones."""
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
        )
        url = reverse('usuarios:iniciar_reunion', args=[reunion.pk])

        self.client.login(username='encargado', password='ClaveSegura123')
        response = self.client.post(url)
        self.assertRedirects(response, reverse('usuarios:dashboard'))

        self.client.login(username='socio', password='ClaveSegura123')
        response = self.client.post(url)
        self.assertRedirects(response, reverse('usuarios:mis_asistencias'))

        reunion.refresh_from_db()
        self.assertEqual(reunion.estado, Reunion.PROGRAMADA)

    @patch('usuarios.models.timezone.now')
    def test_administrador_finaliza_reunion_activa(self, now_mock):
        """Permite cerrar asistencia y marcar ausentes desde el listado."""
        momento = datetime(2026, 5, 20, 20, 0, tzinfo=timezone.get_current_timezone())
        now_mock.return_value = momento
        socio_ausente = self.User.objects.create_user(
            username='socio.finalizar',
            email='socio.finalizar@example.com',
            password='ClaveSegura123',
            first_name='Socio',
            last_name='Finalizar',
            rut='66.666.666-6',
            rol=self.User.SOCIO,
        )
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
        )
        reunion.iniciar(self.admin_user)
        AsistenciaReunion.registrar_presente(
            reunion=reunion,
            socio=self.socio_user,
            usuario=self.encargado_user,
            origen=AsistenciaReunion.ORIGEN_RUT,
        )
        url_finalizar = reverse('usuarios:finalizar_reunion', args=[reunion.pk])

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:listado_reuniones'))
        self.assertContains(response, url_finalizar)
        self.assertContains(response, 'Finalizar')

        response = self.client.post(url_finalizar, follow=True)

        self.assertRedirects(response, reverse('usuarios:listado_reuniones'))
        self.assertContains(response, 'finalizada correctamente')
        self.assertContains(response, 'Ausencias automaticas: 1.')
        reunion.refresh_from_db()
        self.assertEqual(reunion.estado, Reunion.FINALIZADA)
        self.assertEqual(reunion.finalizada_por, self.admin_user)
        self.assertEqual(reunion.fecha_finalizacion, momento)
        asistencia_ausente = AsistenciaReunion.objects.get(
            reunion=reunion,
            socio=socio_ausente,
        )
        self.assertEqual(asistencia_ausente.estado, AsistenciaReunion.AUSENTE)
        self.assertEqual(asistencia_ausente.origen, AsistenciaReunion.ORIGEN_AUTOMATICO)
        self.assertContains(response, 'Finalizada')
        self.assertContains(response, self.admin_user.nombre_completo)

    def test_finalizar_reunion_bloquea_si_no_esta_activa(self):
        """Muestra error sin crear ausencias cuando la reunion no esta activa."""
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
        )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:finalizar_reunion', args=[reunion.pk]),
            follow=True,
        )

        self.assertRedirects(response, reverse('usuarios:listado_reuniones'))
        self.assertContains(response, 'Solo se pueden finalizar reuniones activas.')
        reunion.refresh_from_db()
        self.assertEqual(reunion.estado, Reunion.PROGRAMADA)
        self.assertEqual(AsistenciaReunion.objects.filter(reunion=reunion).count(), 0)

    def test_finalizar_reunion_solo_disponible_para_administrador(self):
        """Protege el cierre de reunion para usuarios sin gestion de reuniones."""
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
        )
        reunion.iniciar(self.admin_user)
        url = reverse('usuarios:finalizar_reunion', args=[reunion.pk])

        self.client.login(username='encargado', password='ClaveSegura123')
        response = self.client.post(url)
        self.assertRedirects(response, reverse('usuarios:dashboard'))

        self.client.login(username='socio', password='ClaveSegura123')
        response = self.client.post(url)
        self.assertRedirects(response, reverse('usuarios:mis_asistencias'))

        reunion.refresh_from_db()
        self.assertEqual(reunion.estado, Reunion.ACTIVA)

    @patch('usuarios.models.timezone.now')
    def test_administrador_cancela_reunion_activa_con_motivo(self, now_mock):
        """Permite cancelar una reunion activa registrando auditoria basica."""
        momento = datetime(2026, 5, 20, 19, 0, tzinfo=timezone.get_current_timezone())
        now_mock.return_value = momento
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
        )
        reunion.iniciar(self.admin_user)
        AsistenciaReunion.registrar_presente(
            reunion=reunion,
            socio=self.socio_user,
            usuario=self.encargado_user,
            origen=AsistenciaReunion.ORIGEN_RUT,
        )
        url_cancelar = reverse('usuarios:cancelar_reunion', args=[reunion.pk])

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:listado_reuniones'))
        self.assertContains(response, url_cancelar)
        self.assertContains(response, 'Cancelar')

        response = self.client.get(url_cancelar)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Cancelar reuni')
        self.assertContains(response, 'motivo_cancelacion')

        response = self.client.post(
            url_cancelar,
            {'motivo_cancelacion': '  Corte de energia  '},
            follow=True,
        )

        self.assertRedirects(response, reverse('usuarios:listado_reuniones'))
        self.assertContains(response, 'cancelada correctamente')
        self.assertContains(response, 'Asistencias eliminadas: 1.')
        self.assertContains(response, 'Cancelada')
        self.assertContains(response, self.admin_user.nombre_completo)
        reunion.refresh_from_db()
        self.assertEqual(reunion.estado, Reunion.CANCELADA)
        self.assertEqual(reunion.cancelada_por, self.admin_user)
        self.assertEqual(reunion.fecha_cancelacion, momento)
        self.assertEqual(reunion.motivo_cancelacion, 'Corte de energia')
        self.assertFalse(AsistenciaReunion.objects.filter(reunion=reunion).exists())

    def test_cancelar_reunion_requiere_motivo(self):
        """Mantiene la reunion sin cambios cuando falta el motivo."""
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
        )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:cancelar_reunion', args=[reunion.pk]),
            {'motivo_cancelacion': '   '},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Este campo es obligatorio.')
        reunion.refresh_from_db()
        self.assertEqual(reunion.estado, Reunion.PROGRAMADA)
        self.assertIsNone(reunion.cancelada_por)

    def test_cancelar_reunion_bloquea_estado_no_permitido(self):
        """Rechaza cancelaciones de reuniones que ya no estan abiertas."""
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
            estado=Reunion.HISTORICA,
        )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:cancelar_reunion', args=[reunion.pk]),
            {'motivo_cancelacion': 'Carga erronea'},
            follow=True,
        )

        self.assertRedirects(response, reverse('usuarios:listado_reuniones'))
        self.assertContains(response, 'Solo se pueden cancelar reuniones programadas o activas.')
        reunion.refresh_from_db()
        self.assertEqual(reunion.estado, Reunion.HISTORICA)
        self.assertIsNone(reunion.cancelada_por)

    def test_cancelar_reunion_solo_disponible_para_administrador(self):
        """Protege la cancelacion de reuniones para usuarios sin permisos."""
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
        )
        reunion.iniciar(self.admin_user)
        url = reverse('usuarios:cancelar_reunion', args=[reunion.pk])

        self.client.login(username='encargado', password='ClaveSegura123')
        response = self.client.post(url, {'motivo_cancelacion': 'Sin quorum'})
        self.assertRedirects(response, reverse('usuarios:dashboard'))

        self.client.login(username='socio', password='ClaveSegura123')
        response = self.client.post(url, {'motivo_cancelacion': 'Sin quorum'})
        self.assertRedirects(response, reverse('usuarios:mis_asistencias'))

        reunion.refresh_from_db()
        self.assertEqual(reunion.estado, Reunion.ACTIVA)
        self.assertIsNone(reunion.cancelada_por)

    def test_listado_reuniones_muestra_registro_asistencia_para_activa(self):
        """Expone la accion de registro desde la reunion activa."""
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
        )
        reunion.iniciar(self.admin_user)
        url_registro = reverse('usuarios:registrar_asistencia_reunion', args=[reunion.pk])

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:listado_reuniones'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, url_registro)
        self.assertContains(response, 'Registrar asistencia')

    def test_registro_asistencia_reunion_muestra_rut_y_qr_operativo(self):
        """Muestra la vista de registro con RUT manual y scanner QR operativo."""
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
        )
        reunion.iniciar(self.admin_user)

        self.client.login(username='encargado', password='ClaveSegura123')
        response = self.client.get(
            reverse('usuarios:registrar_asistencia_reunion', args=[reunion.pk]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Scanner QR')
        self.assertContains(response, 'Escaneo con lector QR activo')
        self.assertContains(response, 'form-switch')
        self.assertContains(response, 'role="switch"')
        self.assertContains(response, 'Registro manual')
        self.assertContains(response, 'data-rut-scan-toggle')
        self.assertContains(response, 'data-rut-scan-target="#id_lectura_qr_scanner"')
        self.assertContains(response, 'data-rut-scan-input')
        self.assertContains(response, 'name="lectura_qr"')
        self.assertContains(response, 'data-rut-manual-region')
        self.assertContains(response, 'aria-disabled="true"')
        self.assertContains(response, 'pe-none')
        self.assertContains(response, 'Registro Manual')
        self.assertContains(response, 'data-rut-format="true"')
        self.assertContains(response, 'data-rut-manual-input="true"')
        self.assertContains(response, 'readonly="readonly"')
        self.assertContains(response, 'tabindex="-1"')
        self.assertContains(response, 'data-rut-manual-submit="true"')
        self.assertContains(response, 'disabled="disabled"')
        self.assertContains(response, 'Registrar por RUT')
        self.assertContains(response, reverse('usuarios:listado_reuniones'))

    def test_parser_reutilizable_extrae_rut_manual_o_run_qr(self):
        """Normaliza RUT manual y payload QR con el mismo contrato."""
        lectura_manual = parsear_lectura_rut('22.222.222-2')
        lectura_qr = parsear_lectura_rut(
            "httpsÑ--portal.sidiv.registrocivil.cl-docstatus_RUN¿14333689'1/type¿CEDULA"
        )

        self.assertEqual(lectura_manual.rut, '22222222-2')
        self.assertEqual(lectura_manual.origen, ORIGEN_RUT_MANUAL)
        self.assertEqual(lectura_qr.rut, '14333689-1')
        self.assertEqual(lectura_qr.origen, ORIGEN_QR_REGISTRO_CIVIL)
        self.assertIsNone(parsear_lectura_rut('22.222.222-3'))
        self.assertIsNone(
            parsear_lectura_rut(
                "httpsÃ‘--portal.sidiv.registrocivil.cl-docstatus_RUNÂ¿14333689'2/typeÂ¿CEDULA"
            )
        )

    def test_encargado_registra_asistencia_por_rut(self):
        """Crea asistencia presente para un socio existente en reunion activa."""
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
        )
        reunion.iniciar(self.admin_user)

        self.client.login(username='encargado', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:registrar_asistencia_reunion', args=[reunion.pk]),
            {'rut': '22.222.222-2'},
            follow=True,
        )

        self.assertRedirects(
            response,
            reverse('usuarios:registrar_asistencia_reunion', args=[reunion.pk]),
        )
        self.assertContains(response, 'Asistencia registrada para Socio Prueba.')
        asistencia = AsistenciaReunion.objects.get(reunion=reunion, socio=self.socio_user)
        self.assertEqual(asistencia.estado, AsistenciaReunion.PRESENTE)
        self.assertEqual(asistencia.origen, AsistenciaReunion.ORIGEN_RUT)
        self.assertEqual(asistencia.registrada_por, self.encargado_user)

    def test_encargado_registra_asistencia_por_qr_con_bloque_run(self):
        """Crea asistencia presente usando el RUN incluido en el payload QR."""
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
        )
        reunion.iniciar(self.admin_user)
        payload_qr = (
            "httpsÑ--portal.sidiv.registrocivil.cl-docstatus_RUN¿22222222'2/"
            'type¿CEDULA/serial¿513275009/mrz¿513275009077100902710095'
        )

        self.client.login(username='encargado', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:registrar_asistencia_reunion', args=[reunion.pk]),
            {'lectura_qr': payload_qr},
            follow=True,
        )

        self.assertRedirects(
            response,
            reverse('usuarios:registrar_asistencia_reunion', args=[reunion.pk]),
        )
        self.assertContains(response, 'Asistencia registrada para Socio Prueba.')
        asistencia = AsistenciaReunion.objects.get(reunion=reunion, socio=self.socio_user)
        self.assertEqual(asistencia.estado, AsistenciaReunion.PRESENTE)
        self.assertEqual(asistencia.origen, AsistenciaReunion.ORIGEN_QR)
        self.assertEqual(asistencia.registrada_por, self.encargado_user)

    def test_registro_asistencia_rechaza_rut_no_existente(self):
        """No permite registrar asistencia a socios inexistentes."""
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
        )
        reunion.iniciar(self.admin_user)

        self.client.login(username='encargado', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:registrar_asistencia_reunion', args=[reunion.pk]),
            {'rut': '99.999.999-9'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Solo se pueden registrar socios existentes.')
        self.assertEqual(AsistenciaReunion.objects.count(), 0)

    def test_registro_asistencia_rechaza_duplicada(self):
        """Mantiene una sola asistencia por socio y reunion."""
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
        )
        reunion.iniciar(self.admin_user)
        AsistenciaReunion.registrar_presente(
            reunion=reunion,
            socio=self.socio_user,
            usuario=self.encargado_user,
            origen=AsistenciaReunion.ORIGEN_RUT,
        )

        self.client.login(username='encargado', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:registrar_asistencia_reunion', args=[reunion.pk]),
            {'rut': '22.222.222-2'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'El socio ya tiene asistencia registrada en esta reunion.')
        self.assertEqual(AsistenciaReunion.objects.count(), 1)

    def test_registro_asistencia_rechaza_socio_inactivo(self):
        """Impide registrar asistencia presente a socios inactivos."""
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
        )
        reunion.iniciar(self.admin_user)
        self.socio_user.is_active = False
        self.socio_user.save(update_fields=['is_active'])

        self.client.login(username='encargado', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:registrar_asistencia_reunion', args=[reunion.pk]),
            {'rut': '22.222.222-2'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'El socio esta inactivo.')
        self.assertEqual(AsistenciaReunion.objects.count(), 0)

    def test_registro_asistencia_rechaza_socio_bloqueado_por_rut(self):
        """Impide registrar asistencia por RUT a socios con dos inasistencias."""
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
        )
        reunion.iniciar(self.admin_user)
        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 4, 10),
        )
        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 4, 17),
        )

        self.client.login(username='encargado', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:registrar_asistencia_reunion', args=[reunion.pk]),
            {'rut': '22.222.222-2'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, AsistenciaReunion.MENSAJE_SOCIO_BLOQUEADO)
        self.assertFalse(
            AsistenciaReunion.objects.filter(
                reunion=reunion,
                socio=self.socio_user,
                estado=AsistenciaReunion.PRESENTE,
            ).exists()
        )

    def test_registro_asistencia_rechaza_socio_bloqueado_por_qr(self):
        """Impide registrar asistencia por QR a socios con dos inasistencias."""
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
        )
        reunion.iniciar(self.admin_user)
        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 4, 10),
        )
        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 4, 17),
        )
        self.client.login(username='encargado', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:registrar_asistencia_reunion', args=[reunion.pk]),
            {'lectura_qr': '22.222.222-2'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, AsistenciaReunion.MENSAJE_SOCIO_BLOQUEADO)
        self.assertFalse(
            AsistenciaReunion.objects.filter(
                reunion=reunion,
                socio=self.socio_user,
                estado=AsistenciaReunion.PRESENTE,
            ).exists()
        )

    def test_modelo_rechaza_asistencia_presente_de_socio_bloqueado(self):
        """Protege la regla de bloqueo aunque se omita el formulario."""
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
        )
        reunion.iniciar(self.admin_user)
        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 4, 10),
        )
        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 4, 17),
        )

        with self.assertRaisesMessage(
            ValidationError,
            AsistenciaReunion.MENSAJE_SOCIO_BLOQUEADO,
        ):
            AsistenciaReunion.registrar_presente(
                reunion=reunion,
                socio=self.socio_user,
                usuario=self.encargado_user,
                origen=AsistenciaReunion.ORIGEN_RUT,
            )

        self.assertFalse(
            AsistenciaReunion.objects.filter(
                reunion=reunion,
                socio=self.socio_user,
                estado=AsistenciaReunion.PRESENTE,
            ).exists()
        )
    def test_bloqueo_operativo_persiste_entre_anios_hasta_justificar(self):
        """El bloqueo vigente no se reinicia por cambiar de ano calendario."""
        anio_actual = timezone.localdate().year
        anio_previo = anio_actual - 1
        ausencia_justificada = self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(anio_previo, 4, 10),
        )
        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(anio_previo, 4, 17),
        )
        reunion = Reunion.objects.create(
            fecha=date(anio_actual, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
        )
        reunion.iniciar(self.admin_user)

        self.assertTrue(
            AsistenciaReunion.socio_esta_bloqueado(
                self.socio_user,
                anio=anio_previo,
            )
        )
        self.assertTrue(AsistenciaReunion.socio_esta_bloqueado(self.socio_user))

        with self.assertRaisesMessage(
            ValidationError,
            AsistenciaReunion.MENSAJE_SOCIO_BLOQUEADO,
        ):
            AsistenciaReunion.registrar_presente(
                reunion=reunion,
                socio=self.socio_user,
                usuario=self.encargado_user,
                origen=AsistenciaReunion.ORIGEN_RUT,
            )

        DesbloqueoSocio.registrar(
            socio=self.socio_user,
            usuario=self.admin_user,
            motivo='Revision administrativa',
            asistencia=ausencia_justificada,
        )

        self.assertFalse(AsistenciaReunion.socio_esta_bloqueado(self.socio_user))
        asistencia = AsistenciaReunion.registrar_presente(
            reunion=reunion,
            socio=self.socio_user,
            usuario=self.encargado_user,
            origen=AsistenciaReunion.ORIGEN_RUT,
        )
        self.assertEqual(asistencia.estado, AsistenciaReunion.PRESENTE)

    @patch('usuarios.models.timezone.now')
    def test_modelo_justifica_inasistencia_con_motivo_responsable_y_fecha(self, now_mock):
        """Registra una justificacion sin borrar ausencias historicas."""
        momento = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.get_current_timezone())
        now_mock.return_value = momento
        ausencia_justificada = self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 20),
        )
        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 27),
        )
        self.assertTrue(AsistenciaReunion.socio_esta_bloqueado(self.socio_user))

        justificacion = DesbloqueoSocio.registrar(
            socio=self.socio_user,
            usuario=self.admin_user,
            motivo='  Compromiso firmado  ',
            asistencia=ausencia_justificada,
        )

        self.assertEqual(justificacion.socio, self.socio_user)
        self.assertEqual(justificacion.asistencia, ausencia_justificada)
        self.assertEqual(justificacion.desbloqueado_por, self.admin_user)
        self.assertEqual(justificacion.fecha_desbloqueo, momento)
        self.assertEqual(justificacion.motivo, 'Compromiso firmado')
        self.assertEqual(justificacion.inasistencias_al_desbloquear, 2)
        self.assertEqual(
            AsistenciaReunion.contar_inasistencias_efectivas_socio(self.socio_user),
            1,
        )
        self.assertFalse(AsistenciaReunion.socio_esta_bloqueado(self.socio_user))

    def test_modelo_justificacion_vuelve_a_bloquear_con_nueva_ausencia(self):
        """Una ausencia posterior vuelve a dejar al socio bloqueado."""
        ausencia_justificada = self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 20),
        )
        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 27),
        )
        DesbloqueoSocio.registrar(
            socio=self.socio_user,
            usuario=self.admin_user,
            motivo='Compromiso firmado',
            asistencia=ausencia_justificada,
        )
        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 6, 3),
        )

        self.assertEqual(
            AsistenciaReunion.contar_inasistencias_efectivas_socio(self.socio_user),
            2,
        )
        self.assertTrue(AsistenciaReunion.socio_esta_bloqueado(self.socio_user))

    def test_modelo_permite_registrar_asistencia_de_socio_justificado_activo(self):
        """Permite asistencia posterior si el socio esta activo y justificado."""
        reunion = Reunion.objects.create(
            fecha=date(2026, 6, 10),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
        )
        reunion.iniciar(self.admin_user)
        ausencia_justificada = self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 20),
        )
        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 27),
        )
        DesbloqueoSocio.registrar(
            socio=self.socio_user,
            usuario=self.admin_user,
            motivo='Compromiso firmado',
            asistencia=ausencia_justificada,
        )

        asistencia = AsistenciaReunion.registrar_presente(
            reunion=reunion,
            socio=self.socio_user,
            usuario=self.encargado_user,
            origen=AsistenciaReunion.ORIGEN_RUT,
        )

        self.assertEqual(asistencia.estado, AsistenciaReunion.PRESENTE)
        self.assertEqual(asistencia.socio, self.socio_user)

    def test_registro_asistencia_requiere_reunion_activa(self):
        """Bloquea el registro si la reunion no esta activa."""
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
        )

        self.client.login(username='encargado', password='ClaveSegura123')
        response = self.client.get(
            reverse('usuarios:registrar_asistencia_reunion', args=[reunion.pk]),
            follow=True,
        )

        self.assertRedirects(response, reverse('usuarios:listado_socios_asistencia'))
        self.assertContains(response, 'Solo se puede registrar asistencia en una reunion activa.')

    def test_registro_asistencia_solo_disponible_para_permiso_asistencia(self):
        """Protege el registro para socios sin permiso operativo."""
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
        )
        reunion.iniciar(self.admin_user)

        self.client.login(username='socio', password='ClaveSegura123')
        response = self.client.get(
            reverse('usuarios:registrar_asistencia_reunion', args=[reunion.pk]),
        )

        self.assertRedirects(response, reverse('usuarios:mis_asistencias'))

    def test_resumen_asistencia_socio_usa_registros_reales(self):
        """Cuenta asistencias reales para indicadores y eliminacion segura."""
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
        )
        reunion.iniciar(self.admin_user)
        AsistenciaReunion.registrar_presente(
            reunion=reunion,
            socio=self.socio_user,
            usuario=self.encargado_user,
            origen=AsistenciaReunion.ORIGEN_RUT,
        )

        resumen = obtener_resumen_asistencia_socio(self.socio_user)

        self.assertEqual(
            resumen,
            {
                'total_reuniones': 1,
                'total_asistencias': 1,
                'total_ausencias': 0,
                'total_ausencias_efectivas': 0,
                'total_justificaciones': 0,
            },
        )
        self.assertFalse(puede_eliminar_socio_seguro(self.socio_user))

    def test_resumen_anual_asistencia_socio_filtra_ano_y_ausencias_efectivas(self):
        """Calcula resumen anual sin contar justificaciones como ausencias efectivas."""
        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.PRESENTE,
            date(2025, 5, 22),
        )
        ausencia_justificada = self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 20),
        )
        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 21),
        )
        DesbloqueoSocio.registrar(
            socio=self.socio_user,
            usuario=self.admin_user,
            motivo='Justificacion administrativa',
            asistencia=ausencia_justificada,
        )

        resumen = obtener_resumen_anual_asistencia_socio(self.socio_user, 2026)

        self.assertEqual(
            resumen,
            {
                'anio': 2026,
                'total_reuniones': 2,
                'total_asistencias': 0,
                'total_ausencias': 2,
                'total_ausencias_efectivas': 1,
                'total_justificaciones': 1,
            },
        )

    def test_historial_asistencia_socio_filtra_ano_y_ordena_por_reunion(self):
        """Entrega historial acotado al socio y ano seleccionado."""
        asistencia_reciente = self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.PRESENTE,
            date(2026, 6, 20),
        )
        asistencia_antigua = self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 20),
        )
        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.PRESENTE,
            date(2025, 5, 20),
        )
        otro_socio = self.User.objects.create_user(
            username='otro.historial',
            email='otro.historial@example.com',
            password='ClaveSegura123',
            first_name='Otro',
            last_name='Historial',
            rut='77.333.333-5',
            rol=self.User.SOCIO,
        )
        self.registrar_asistencia_historica(
            otro_socio,
            AsistenciaReunion.PRESENTE,
            date(2026, 7, 20),
        )

        historial = list(obtener_historial_asistencia_socio(self.socio_user, 2026))

        self.assertEqual(historial, [asistencia_reciente, asistencia_antigua])

    @patch('usuarios.servicios_asistencia.timezone.localtime')
    def test_proxima_reunion_usa_programada_mas_cercana_desde_ahora(self, localtime_mock):
        """Selecciona automaticamente la siguiente reunion programada por fecha y hora."""
        localtime_mock.return_value = timezone.make_aware(
            datetime(2026, 6, 10, 12, 0),
        )
        Reunion.objects.create(
            fecha=date(2026, 6, 10),
            hora=time(10, 0),
            locacion='Sede anterior',
            creador=self.admin_user,
        )
        reunion_esperada = Reunion.objects.create(
            fecha=date(2026, 6, 10),
            hora=time(18, 30),
            locacion='Sede cercana',
            creador=self.admin_user,
        )
        Reunion.objects.create(
            fecha=date(2026, 6, 11),
            hora=time(9, 0),
            locacion='Sede futura',
            creador=self.admin_user,
        )
        Reunion.objects.create(
            fecha=date(2026, 6, 10),
            hora=time(13, 0),
            locacion='Sede finalizada',
            creador=self.admin_user,
            estado=Reunion.FINALIZADA,
        )

        self.assertEqual(obtener_proxima_reunion(), reunion_esperada)

    def test_resumen_asistencia_socios_anotado_no_consulta_por_socio(self):
        """Agrega resumenes de asistencia en lote para evitar N+1 consultas."""
        socio_ausente = self.User.objects.create_user(
            username='ausente.resumen',
            email='ausente.resumen@example.com',
            password='ClaveSegura123',
            first_name='Ausente',
            last_name='Resumen',
            rut='77.222.222-K',
            rol=self.User.SOCIO,
        )
        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.PRESENTE,
            date(2026, 5, 20),
        )
        self.registrar_asistencia_historica(
            socio_ausente,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 21),
        )
        socios = anotar_resumen_asistencia_socios(
            self.User.objects.filter(rol=self.User.SOCIO).order_by('pk')
        )

        with self.assertNumQueries(1):
            socios_resumidos = agregar_resumen_asistencia_socios(socios)

        resumenes = {
            socio.pk: (
                socio.total_reuniones,
                socio.total_asistencias,
                socio.total_ausencias,
                socio.indicador_asistencia['key'],
            )
            for socio in socios_resumidos
        }
        self.assertEqual(resumenes[self.socio_user.pk], (1, 1, 0, 'sin_ausencias'))
        self.assertEqual(resumenes[socio_ausente.pk], (1, 0, 1, 'una_inasistencia'))

    def test_administrador_accede_a_asistencia_y_ve_solo_socios(self):
        """Permite al administrador ver el listado operativo de socios."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:listado_socios_asistencia'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Listado operativo de socios')
        self.assertContains(response, 'title="Reuniones"')
        self.assertContains(response, 'aria-label="Reuniones"')
        self.assertContains(response, 'bi-calendar-check')
        self.assertContains(response, 'title="Asistencias"')
        self.assertContains(response, 'aria-label="Asistencias"')
        self.assertContains(response, 'title="Ausencias"')
        self.assertContains(response, 'aria-label="Ausencias"')
        self.assertContains(response, 'title="Justificaciones"')
        self.assertContains(response, 'aria-label="Justificaciones"')
        self.assertContains(response, 'Sin ausencias')
        self.assertContains(response, 'aria-label="Ver detalle de asistencia"')
        self.assertContains(response, 'APELLIDOS')
        self.assertNotContains(response, 'Gestionar estado')
        self.assertNotContains(response, reverse('usuarios:editar_socio', args=[self.socio_user.pk]))
        self.assertContains(response, self.socio_user.rut)
        self.assertContains(response, '+56922222222')
        self.assertNotContains(response, self.socio_user.email)
        self.assertNotContains(response, 'admin@example.com')
        self.assertNotContains(response, 'encargado@example.com')

    def test_listado_asistencia_muestra_exportacion_solo_a_administrador(self):
        """Expone reportes anuales descargables solo a administradores."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:listado_socios_asistencia'))

        self.assertContains(response, 'aria-label="Exportar resumen anual"')
        self.assertContains(response, 'Descargar reporte anual CSV')
        self.assertContains(response, 'Descargar reporte anual XLSX')
        self.assertNotContains(response, 'Descargar reporte anual PDF')
        self.assertContains(
            response,
            reverse('usuarios:exportar_asistencia_anual', args=['csv']),
        )
        self.assertContains(
            response,
            f'anio={timezone.localdate().year}',
        )
        self.assertContains(response, 'name="estado"')
        self.assertContains(response, 'name="anio"')
        self.assertContains(response, 'filtro-asistencia-anio')
        self.assertContains(response, 'A&ntilde;o operativo')

        self.client.login(username='encargado', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:listado_socios_asistencia'))

        self.assertNotContains(response, 'aria-label="Exportar resumen anual"')
        self.assertNotContains(
            response,
            reverse('usuarios:exportar_asistencia_anual', args=['csv']),
        )

    def test_listado_asistencia_muestra_bloqueo_operativo_interanual(self):
        """El ano de la vista controla contadores, no el bloqueo vigente."""
        anio_actual = timezone.localdate().year
        anio_previo = anio_actual - 1
        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(anio_previo, 5, 20),
        )
        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(anio_previo, 5, 27),
        )
        self.client.login(username='admin', password='ClaveSegura123')

        response_actual = self.client.get(reverse('usuarios:listado_socios_asistencia'))
        socio_actual = next(
            socio
            for socio in response_actual.context['socios']
            if socio.pk == self.socio_user.pk
        )

        self.assertEqual(socio_actual.total_reuniones, 0)
        self.assertEqual(socio_actual.total_ausencias, 0)
        self.assertEqual(socio_actual.indicador_asistencia['key'], 'bloqueado')

        response_bloqueados = self.client.get(
            reverse('usuarios:listado_socios_asistencia'),
            {'indicador': 'bloqueado'},
        )
        self.assertContains(response_bloqueados, self.socio_user.rut)

        response_previo = self.client.get(
            reverse('usuarios:listado_socios_asistencia'),
            {'anio': anio_previo},
        )
        socio_previo = next(
            socio
            for socio in response_previo.context['socios']
            if socio.pk == self.socio_user.pk
        )

        self.assertEqual(socio_previo.total_reuniones, 2)
        self.assertEqual(socio_previo.total_ausencias, 2)
        self.assertEqual(socio_previo.indicador_asistencia['key'], 'bloqueado')
        self.assertContains(response_previo, f'value="{anio_previo}"')

    def test_exportar_asistencia_csv_usa_dataset_completo_no_paginado(self):
        """El reporte CSV usa todos los socios filtrados y no solo la pagina actual."""
        for indice in range(55):
            self.User.objects.create_user(
                username=f'exportable_{indice:02d}',
                email=f'exportable_{indice:02d}@example.com',
                password='ClaveSegura123',
                first_name='Exportable',
                last_name=f'Completo {indice:02d}',
                rut=self.rut_prueba(95000000 + indice),
                rol=self.User.SOCIO,
            )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(
            reverse('usuarios:exportar_asistencia_anual', args=['csv']),
            {'nombre': 'Exportable', 'anio': 2026},
        )
        contenido = response.content.decode('utf-8-sig')
        filas = list(csv.DictReader(StringIO(contenido)))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv; charset=utf-8')
        self.assertIn('attachment;', response['Content-Disposition'])
        self.assertIn('reporte_asistencia_anual_2026.csv', response['Content-Disposition'])
        self.assertEqual(len(filas), 55)
        self.assertEqual(filas[-1]['Correo electronico'], 'exportable_54@example.com')
        self.assertIn('Usuario', filas[-1])
        self.assertIn('Telefono movil', filas[-1])
        self.assertNotIn('Nombre completo', filas[-1])

    def test_exportar_asistencia_csv_respeta_anio_y_estado(self):
        """El reporte anual cuenta solo reuniones del ano seleccionado."""
        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.PRESENTE,
            date(2025, 5, 20),
        )
        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 21),
        )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(
            reverse('usuarios:exportar_asistencia_anual', args=['csv']),
            {
                'rut': self.socio_user.rut,
                'estado': 'activo',
                'anio': 2026,
            },
        )
        filas = list(csv.DictReader(StringIO(response.content.decode('utf-8-sig'))))

        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]['Ano'], '2026')
        self.assertEqual(filas[0]['RUT'], self.socio_user.rut)
        self.assertEqual(filas[0]['Estado actual'], 'Activo')
        self.assertEqual(filas[0]['Reuniones realizadas'], '1')
        self.assertEqual(filas[0]['Asistencias'], '0')
        self.assertEqual(filas[0]['Inasistencias'], '1')
        self.assertEqual(filas[0]['Inasistencias efectivas'], '1')

    def test_exportar_asistencia_xlsx_y_pdf_descargan_datos_completos(self):
        """Genera XLSX y PDF descargables con datos no visibles en la tabla."""
        self.client.login(username='admin', password='ClaveSegura123')

        response_xlsx = self.client.get(
            reverse('usuarios:exportar_asistencia_anual', args=['xlsx']),
            {'rut': self.socio_user.rut, 'anio': 2026},
        )
        with zipfile.ZipFile(BytesIO(response_xlsx.content)) as archivo:
            worksheet = archivo.read('xl/worksheets/sheet1.xml').decode('utf-8')
            styles = archivo.read('xl/styles.xml').decode('utf-8')

        self.assertEqual(response_xlsx.status_code, 200)
        self.assertEqual(
            response_xlsx['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        self.assertIn('attachment;', response_xlsx['Content-Disposition'])
        self.assertIn('Correo electronico', worksheet)
        self.assertIn('socio@example.com', worksheet)
        self.assertIn('Telefono movil', worksheet)
        self.assertIn('+56922222222', worksheet)
        self.assertNotIn('Nombre completo', worksheet)
        self.assertLess(worksheet.index('<sheetViews>'), worksheet.index('<cols>'))
        self.assertLess(worksheet.index('<cols>'), worksheet.index('<sheetData>'))
        self.assertIn('patternType="gray125"', styles)

        response_pdf = self.client.get(
            reverse('usuarios:exportar_asistencia_anual', args=['pdf']),
            {'rut': self.socio_user.rut, 'anio': 2026},
        )

        self.assertEqual(response_pdf.status_code, 200)
        self.assertEqual(response_pdf['Content-Type'], 'application/pdf')
        self.assertIn('attachment;', response_pdf['Content-Disposition'])
        self.assertTrue(response_pdf.content.startswith(b'%PDF-1.4'))
        self.assertIn(b'socio@example.com', response_pdf.content)
        self.assertIn(b'+56922222222', response_pdf.content)
        self.assertNotIn(b'Nombre completo', response_pdf.content)

    def test_exportar_asistencia_restringe_encargados(self):
        """Solo administradores pueden descargar reportes anuales."""
        self.client.login(username='encargado', password='ClaveSegura123')
        response = self.client.get(
            reverse('usuarios:exportar_asistencia_anual', args=['csv']),
        )

        self.assertRedirects(response, reverse('usuarios:dashboard'))

    def test_listado_asistencia_filtra_y_concatena_apellidos(self):
        """Aplica filtros operativos y muestra apellidos en una sola columna."""
        socio_filtrado = self.User.objects.create_user(
            username='ana.asistencia',
            email='ana.asistencia@example.com',
            password='ClaveSegura123',
            first_name='Ana',
            last_name='Asistencia',
            apellido_materno='Rojas',
            fecha_ingreso_proyecto=date(2026, 5, 15),
            rut='77.777.777-7',
            rol=self.User.SOCIO,
        )
        socio_excluido = self.User.objects.create_user(
            username='bruno.asistencia',
            email='bruno.asistencia@example.com',
            password='ClaveSegura123',
            first_name='Bruno',
            last_name='Asistencia',
            apellido_materno='Silva',
            rut='88.888.888-8',
            rol=self.User.SOCIO,
        )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(
            reverse('usuarios:listado_socios_asistencia'),
            {
                'rut': '77.777.777-7',
                'nombre': 'Ana',
                'apellido': 'Rojas',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ordenar RUT ascendente')
        self.assertContains(response, 'Ordenar Nombre ascendente')
        self.assertContains(response, 'Ordenar Apellidos ascendente')
        self.assertNotContains(response, 'Ordenar Apellido materno ascendente')
        self.assertNotContains(response, socio_filtrado.email)
        self.assertContains(response, '<td class="fw-semibold">77777777-7</td>', html=True)
        self.assertContains(
            response,
            '<span class="table-cell-truncate is-name" title="Ana">Ana</span>',
            html=True,
        )
        self.assertContains(
            response,
            '<span class="table-cell-truncate is-name-wide" title="Asistencia Rojas">Asistencia Rojas</span>',
            html=True,
        )
        self.assertContains(response, 'value="77.777.777-7"')
        self.assertContains(response, 'value="Ana"')
        self.assertContains(response, 'value="Rojas"')
        self.assertNotContains(response, socio_excluido.rut)
        self.assertNotContains(response, 'admin@example.com')

    def test_listado_asistencia_filtra_por_indicador(self):
        """Permite filtrar socios por indicador de asistencia."""
        socio_riesgo = self.User.objects.create_user(
            username='riesgo.asistencia',
            email='riesgo.asistencia@example.com',
            password='ClaveSegura123',
            first_name='Riesgo',
            last_name='Asistencia',
            rut='88.111.111-K',
            rol=self.User.SOCIO,
        )
        socio_bloqueado = self.User.objects.create_user(
            username='bloqueado.asistencia',
            email='bloqueado.asistencia@example.com',
            password='ClaveSegura123',
            first_name='Bloqueado',
            last_name='Asistencia',
            rut='88.222.222-5',
            rol=self.User.SOCIO,
        )
        self.registrar_asistencia_historica(
            socio_riesgo,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 20),
        )
        self.registrar_asistencia_historica(
            socio_bloqueado,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 21),
        )
        self.registrar_asistencia_historica(
            socio_bloqueado,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 22),
        )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(
            reverse('usuarios:listado_socios_asistencia'),
            {'indicador': 'bloqueado'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<option value="bloqueado" selected>Bloqueado</option>',
            html=True,
        )
        self.assertContains(response, socio_bloqueado.rut)
        self.assertNotContains(response, socio_riesgo.rut)
        self.assertNotContains(response, self.socio_user.rut)

    def test_listado_asistencia_filtra_socios_justificados_como_una_inasistencia(self):
        """Muestra socios justificados como una inasistencia efectiva."""
        socio_bloqueado = self.User.objects.create_user(
            username='bloq.filtro',
            email='bloq.filtro@example.com',
            password='ClaveSegura123',
            first_name='Bloqueado',
            last_name='Filtro',
            rut='88.333.333-0',
            rol=self.User.SOCIO,
        )
        socio_justificado = self.User.objects.create_user(
            username='justificado.filtro',
            email='justificado.filtro@example.com',
            password='ClaveSegura123',
            first_name='Justificado',
            last_name='Filtro',
            rut='88.444.444-6',
            rol=self.User.SOCIO,
        )
        ausencia_justificada = None
        for socio in (socio_bloqueado, socio_justificado):
            ausencia = self.registrar_asistencia_historica(
                socio,
                AsistenciaReunion.AUSENTE,
                date(2026, 5, 20),
            )
            if socio == socio_justificado:
                ausencia_justificada = ausencia
            self.registrar_asistencia_historica(
                socio,
                AsistenciaReunion.AUSENTE,
                date(2026, 5, 27),
            )
        DesbloqueoSocio.registrar(
            socio=socio_justificado,
            usuario=self.admin_user,
            motivo='Compromiso firmado',
            asistencia=ausencia_justificada,
        )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(
            reverse('usuarios:listado_socios_asistencia'),
            {'indicador': 'bloqueado'},
        )
        self.assertContains(response, socio_bloqueado.rut)
        self.assertNotContains(response, socio_justificado.rut)

        response = self.client.get(
            reverse('usuarios:listado_socios_asistencia'),
            {'indicador': 'una_inasistencia'},
        )
        self.assertContains(response, socio_justificado.rut)
        self.assertNotContains(response, socio_bloqueado.rut)

    def test_listado_asistencia_tiene_lista_responsiva_para_movil(self):
        """Replica el formato responsivo usado por los listados administrativos."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:listado_socios_asistencia'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'd-none d-md-block')
        self.assertContains(response, 'list-group shadow-sm border rounded overflow-hidden d-md-none')
        self.assertContains(response, '<dt class="col-4 text-muted fw-semibold">NOMBRE</dt>', html=True)
        self.assertContains(response, '<dt class="col-4 text-muted fw-semibold">APELLIDOS</dt>', html=True)
        self.assertNotContains(response, '<dt class="col-4 text-muted fw-semibold">AP. PATERNO</dt>', html=True)
        self.assertNotContains(response, '<dt class="col-4 text-muted fw-semibold">AP. MATERNO</dt>', html=True)
        self.assertNotContains(response, '<dt class="col-4 text-muted fw-semibold">EMAIL</dt>', html=True)
        self.assertContains(response, '<dt class="col-4 text-muted fw-semibold">TELÉFONO</dt>', html=True)
        self.assertContains(response, '<dt class="col-4 text-muted fw-semibold">REUNIONES</dt>', html=True)
        self.assertContains(response, '<dt class="col-4 text-muted fw-semibold">ASISTENCIAS</dt>', html=True)
        self.assertContains(response, '<dt class="col-4 text-muted fw-semibold">AUSENCIAS</dt>', html=True)

    def test_listado_asistencia_paginacion_conserva_filtros(self):
        """Mantiene filtros activos al navegar paginas del listado operativo."""
        for indice in range(51):
            self.User.objects.create_user(
                username=f'asistencia_filtro_{indice:02d}',
                email=f'asistencia_filtro_{indice:02d}@example.com',
                password='ClaveSegura123',
                first_name='AsistenciaFiltro',
                last_name=f'Paginacion {indice:02d}',
                rut=self.rut_prueba(91000000 + indice),
                rol=self.User.SOCIO,
            )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(
            reverse('usuarios:listado_socios_asistencia'),
            {'nombre': 'AsistenciaFiltro'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['socios']), 50)
        self.assertContains(response, 'nombre=AsistenciaFiltro&page=2')

    def test_listado_asistencia_ordena_columnas_ascendente_y_descendente(self):
        """Ordena el listado operativo por columnas de datos personales."""
        self.User.objects.create_user(
            username='aaron.asistencia',
            email='aaron.asistencia@example.com',
            password='ClaveSegura123',
            first_name='Aaron',
            last_name='Orden',
            rut='92.222.222-3',
            rol=self.User.SOCIO,
        )
        self.User.objects.create_user(
            username='zulu.asistencia',
            email='zulu.asistencia@example.com',
            password='ClaveSegura123',
            first_name='Zulu',
            last_name='Orden',
            rut='93.333.333-7',
            rol=self.User.SOCIO,
        )

        self.client.login(username='admin', password='ClaveSegura123')

        response = self.client.get(
            reverse('usuarios:listado_socios_asistencia'),
            {'orden': 'nombre', 'direccion': 'asc'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['socios'][0].username, 'aaron.asistencia')
        self.assertContains(response, 'Ordenar Nombre descendente')
        self.assertContains(response, 'aria-current="true"')

        response = self.client.get(
            reverse('usuarios:listado_socios_asistencia'),
            {'orden': 'nombre', 'direccion': 'desc'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['socios'][0].username, 'zulu.asistencia')
        self.assertContains(response, 'Ordenar Nombre ascendente')

    def test_indicador_asistencia_calcula_estados_por_ausencias(self):
        """Mapea ausencias a indicadores visuales esperados."""
        self.assertEqual(obtener_indicador_asistencia(0)['badge_class'], 'text-bg-success')
        self.assertEqual(obtener_indicador_asistencia(1)['badge_class'], 'text-bg-warning')
        self.assertEqual(obtener_indicador_asistencia(2)['badge_class'], 'text-bg-danger')

    def test_resumen_estado_asistencia_socios_agrupa_por_ausencias(self):
        """Agrupa socios sin faltas, en riesgo y bloqueados por ausencias."""
        socio_riesgo = self.User.objects.create_user(
            username='riesgo',
            email='riesgo@example.com',
            password='ClaveSegura123',
            first_name='Socio',
            last_name='Riesgo',
            rut='55.555.555-5',
            rol=self.User.SOCIO,
        )
        socio_bloqueado = self.User.objects.create_user(
            username='bloqueado',
            email='bloqueado@example.com',
            password='ClaveSegura123',
            first_name='Socio',
            last_name='Bloqueado',
            rut='66.666.666-6',
            rol=self.User.SOCIO,
        )
        self.registrar_asistencia_historica(
            socio_riesgo,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 20),
        )
        self.registrar_asistencia_historica(
            socio_bloqueado,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 21),
        )
        self.registrar_asistencia_historica(
            socio_bloqueado,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 22),
        )

        resumen = obtener_resumen_estado_asistencia_socios()

        totales = {item['label']: item['total'] for item in resumen['items']}
        self.assertEqual(resumen['total'], 3)
        self.assertEqual(totales['Socios totales'], 3)
        self.assertEqual(totales['Sin falta'], 1)
        self.assertEqual(totales['En riesgo'], 1)
        self.assertEqual(totales['Bloqueados por inasistencia'], 1)

    def test_resumen_estado_asistencia_socios_cuenta_justificados_en_riesgo(self):
        """Cuenta al socio justificado como una inasistencia efectiva."""
        ausencia_justificada = self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 20),
        )
        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 27),
        )
        DesbloqueoSocio.registrar(
            socio=self.socio_user,
            usuario=self.admin_user,
            motivo='Compromiso firmado',
            asistencia=ausencia_justificada,
        )

        resumen = obtener_resumen_estado_asistencia_socios()

        totales = {item['label']: item['total'] for item in resumen['items']}
        self.assertEqual(totales['Bloqueados por inasistencia'], 0)
        self.assertEqual(totales['En riesgo'], 1)
        self.assertNotIn('Desbloqueados', totales)

    def test_listado_usuarios_incluye_confirmacion_para_cambiar_estado(self):
        """Agrega confirmacion visual al cambio de estado de usuarios."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:listado_usuarios'))
        self.assertContains(response, 'data-confirm-submit')
        self.assertContains(response, 'data-confirm-title="Desactivar usuario"')
        self.assertContains(response, 'data-confirm-color="#b42318"')
        self.assertContains(response, 'admin@example.com')
        self.assertContains(response, '+56911111111')
        self.assertContains(response, 'encargado@example.com')
        self.assertNotContains(response, 'socio@example.com')

    def test_listado_usuarios_oculta_superadministradores(self):
        """Mantiene las cuentas del admin Django fuera de la gestion web."""
        superusuario = self.User.objects.create_superuser(
            username='super_oculto',
            email='super.oculto@example.com',
            password='ClaveSegura123',
            first_name='Super',
            last_name='Oculto',
            rut='12.000.000-4',
        )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:listado_usuarios'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'super_oculto')
        self.assertNotContains(response, 'super.oculto@example.com')
        self.assertTrue(all(not usuario.is_superuser for usuario in response.context['usuarios']))

        self.client.force_login(superusuario)
        response = self.client.get(reverse('usuarios:listado_usuarios'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'super_oculto')
        self.assertNotContains(response, 'super.oculto@example.com')

    def test_listado_usuarios_muestra_eliminacion_bloqueada_por_activador(self):
        """Muestra la columna de eliminacion bloqueada hasta activarla."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:listado_usuarios'))

        self.assertContains(response, 'data-enable-delete-column')
        self.assertContains(response, 'data-delete-enabled="false"')
        self.assertContains(response, 'Activar eliminación')
        self.assertContains(response, 'Desactivar eliminación')
        self.assertContains(response, 'Eliminación activada')
        self.assertContains(response, 'role="switch"')
        self.assertContains(response, 'aria-checked="false"')
        self.assertContains(response, reverse('usuarios:eliminar_usuario', args=[self.encargado_user.pk]))
        self.assertContains(response, 'data-delete-user-button')
        self.assertContains(response, 'data-delete-allowed="true"')
        self.assertContains(response, 'disabled')
        self.assertContains(response, 'No puedes eliminar tu propio usuario.')
        self.assertNotContains(response, reverse('usuarios:eliminar_usuario', args=[self.admin_user.pk]))

    def test_listado_usuarios_paginas_de_50_items(self):
        """Pagina el listado de usuarios internos en bloques de 50 registros."""
        for indice in range(50):
            self.User.objects.create_user(
                username=f'interno_{indice:02d}',
                email=f'interno_{indice:02d}@example.com',
                password='ClaveSegura123',
                first_name='Usuario',
                last_name=f'Paginado {indice:02d}',
                rut=self.rut_prueba(70000000 + indice),
                rol=self.User.ENCARGADO_REGISTRO,
            )

        self.client.login(username='admin', password='ClaveSegura123')

        response = self.client.get(reverse('usuarios:listado_usuarios'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['page_obj'].paginator.per_page, 50)
        self.assertEqual(len(response.context['usuarios']), 50)
        self.assertContains(response, '?page=2')

        response = self.client.get(f"{reverse('usuarios:listado_usuarios')}?page=2")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['usuarios']), 2)
        self.assertContains(response, '?page=1')

    def test_listado_usuarios_filtra_por_rut_nombre_y_apellido(self):
        """Permite filtrar usuarios internos por RUT, nombre y apellido."""
        usuario_filtrado = self.User.objects.create_user(
            username='ana.zapata',
            email='ana.zapata@example.com',
            password='ClaveSegura123',
            first_name='Ana',
            last_name='Zapata',
            rut='77.777.777-7',
            rol=self.User.ENCARGADO_REGISTRO,
        )
        self.User.objects.create_user(
            username='bruno.zapata',
            email='bruno.zapata@example.com',
            password='ClaveSegura123',
            first_name='Bruno',
            last_name='Zapata',
            rut='88.888.888-8',
            rol=self.User.ENCARGADO_REGISTRO,
        )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(
            reverse('usuarios:listado_usuarios'),
            {
                'rut': '77.777.777-7',
                'nombre': 'Ana',
                'apellido': 'Zapata',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ordenar Nombre ascendente')
        self.assertContains(response, 'Ordenar Apellido ascendente')
        self.assertContains(response, usuario_filtrado.email)
        self.assertContains(
            response,
            '<span class="table-cell-truncate is-name" title="Ana">Ana</span>',
            html=True,
        )
        self.assertContains(
            response,
            '<span class="table-cell-truncate is-name" title="Zapata">Zapata</span>',
            html=True,
        )
        self.assertContains(response, 'value="77.777.777-7"')
        self.assertContains(response, 'value="Ana"')
        self.assertContains(response, 'value="Zapata"')
        self.assertNotContains(response, 'bruno.zapata@example.com')
        self.assertNotContains(response, 'admin@example.com')

    def test_listado_usuarios_filtra_por_rol(self):
        """Permite filtrar usuarios internos por rol."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(
            reverse('usuarios:listado_usuarios'),
            {'rol': self.User.ADMINISTRADOR},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="rol"')
        self.assertContains(
            response,
            '<option value="ADMINISTRADOR" selected>Administrador</option>',
            html=True,
        )
        self.assertContains(response, 'admin@example.com')
        self.assertNotContains(response, 'encargado@example.com')
        self.assertNotContains(response, 'socio@example.com')

    def test_listado_usuarios_muestra_estado_propio_deshabilitado(self):
        """Muestra deshabilitado el boton de estado del usuario autenticado."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:listado_usuarios'))

        self.assertContains(response, 'No puedes desactivar tu propio usuario.')
        self.assertNotContains(
            response,
            reverse('usuarios:cambiar_estado_usuario', args=[self.admin_user.pk]),
        )
        self.assertContains(
            response,
            reverse('usuarios:cambiar_estado_usuario', args=[self.encargado_user.pk]),
        )

    def test_listado_usuarios_tiene_lista_responsiva_para_movil(self):
        """Renderiza una lista móvil alternativa a la tabla de escritorio."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:listado_usuarios'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'd-none d-md-block')
        self.assertContains(response, 'list-group shadow-sm border rounded overflow-hidden d-md-none')
        self.assertContains(response, '<dt class="col-4 text-muted fw-semibold">RUT</dt>', html=True)
        self.assertContains(response, '<dt class="col-4 text-muted fw-semibold">EMAIL</dt>', html=True)
        self.assertContains(response, '<dt class="col-4 text-muted fw-semibold">TELÉFONO</dt>', html=True)
        self.assertContains(response, '<dt class="col-4 text-muted fw-semibold">ROL</dt>', html=True)

    def test_listado_usuarios_paginacion_conserva_filtros(self):
        """Mantiene los filtros activos al navegar entre paginas."""
        for indice in range(51):
            self.User.objects.create_user(
                username=f'filtro_{indice:02d}',
                email=f'filtro_{indice:02d}@example.com',
                password='ClaveSegura123',
                first_name='Filtro',
                last_name=f'Paginacion {indice:02d}',
                rut=self.rut_prueba(71000000 + indice),
                rol=self.User.ENCARGADO_REGISTRO,
            )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(
            reverse('usuarios:listado_usuarios'),
            {'nombre': 'Filtro'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['usuarios']), 50)
        self.assertContains(response, 'nombre=Filtro&page=2')

    def test_listado_usuarios_ordena_columnas_ascendente_y_descendente(self):
        """Ordena el listado por columnas seleccionadas desde el encabezado."""
        self.User.objects.create_user(
            username='aaron.orden',
            email='aaron.orden@example.com',
            password='ClaveSegura123',
            first_name='Aaron',
            last_name='Orden',
            rut='72.222.222-9',
            rol=self.User.ENCARGADO_REGISTRO,
        )
        self.User.objects.create_user(
            username='zulu.orden',
            email='zulu.orden@example.com',
            password='ClaveSegura123',
            first_name='Zulu',
            last_name='Orden',
            rut='73.333.333-2',
            rol=self.User.ENCARGADO_REGISTRO,
        )

        self.client.login(username='admin', password='ClaveSegura123')

        response = self.client.get(
            reverse('usuarios:listado_usuarios'),
            {'orden': 'nombre', 'direccion': 'asc'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['usuarios'][0].username, 'aaron.orden')
        self.assertContains(response, 'Ordenar Nombre descendente')
        self.assertContains(response, 'aria-current="true"')

        response = self.client.get(
            reverse('usuarios:listado_usuarios'),
            {'orden': 'nombre', 'direccion': 'desc'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['usuarios'][0].username, 'zulu.orden')
        self.assertContains(response, 'Ordenar Nombre ascendente')

    def test_listado_usuarios_paginacion_conserva_orden(self):
        """Mantiene el orden activo al navegar entre paginas."""
        for indice in range(51):
            self.User.objects.create_user(
                username=f'orden_{indice:02d}',
                email=f'orden_{indice:02d}@example.com',
                password='ClaveSegura123',
                first_name='Orden',
                last_name=f'Paginacion {indice:02d}',
                rut=self.rut_prueba(74000000 + indice),
                rol=self.User.ENCARGADO_REGISTRO,
            )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(
            reverse('usuarios:listado_usuarios'),
            {'nombre': 'Orden', 'orden': 'apellido', 'direccion': 'desc'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['usuarios']), 50)
        self.assertContains(
            response,
            'nombre=Orden&amp;orden=apellido&amp;direccion=desc&page=2',
        )

    def test_administrador_accede_a_listado_socios_separado(self):
        """Lista socios en una vista administrativa separada de usuarios."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:listado_socios'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Gestión administrativa de socios registrados.')
        self.assertContains(response, 'aria-label="Contacto"')
        self.assertContains(response, 'title="Email: socio@example.com"')
        self.assertContains(response, 'title="Telefono: +56922222222"')
        self.assertContains(response, 'bi-envelope')
        self.assertContains(response, 'bi-telephone')
        self.assertContains(response, 'APELLIDO MATERNO')
        self.assertNotContains(response, 'INGRESO')
        self.assertContains(response, 'aria-label="Estado de asistencia"')
        self.assertContains(response, 'bi-info-circle')
        self.assertContains(response, 'title="Sin ausencias"')
        self.assertContains(response, 'aria-label="Estado de asistencia: Sin ausencias"')
        self.assertContains(response, 'bi-check-circle')
        self.assertContains(response, reverse('usuarios:detalle_socio', args=[self.socio_user.pk]))
        self.assertContains(response, 'aria-label="Ver detalles del socio"')
        self.assertContains(response, 'bi-eye')
        self.assertContains(response, reverse('usuarios:editar_socio', args=[self.socio_user.pk]))
        self.assertContains(response, 'data-confirm-title="Desactivar socio"')
        self.assertContains(response, reverse('usuarios:eliminar_socio', args=[self.socio_user.pk]))
        self.assertContains(response, 'data-confirm-title="Eliminar socio"')
        self.assertContains(response, 'class="btn btn-danger btn-sm"')
        self.assertContains(response, 'bi-trash-fill')
        self.assertContains(response, 'aria-label="Exportar reporte completo de socios"')
        self.assertContains(response, 'btn-group btn-group-sm')
        self.assertContains(response, 'Descargar reporte completo de socios CSV')
        self.assertNotContains(response, 'Descargar reporte completo de socios PDF')
        self.assertContains(
            response,
            reverse('usuarios:exportar_socios_completo', args=['csv']),
        )
        self.assertNotContains(response, 'name="anio"')
        self.assertNotContains(response, 'filtro-socio-anio')
        self.assertNotContains(response, 'A&ntilde;o reporte')
        self.assertNotContains(response, 'admin@example.com')
        self.assertNotContains(response, 'encargado@example.com')

    def test_exportar_socios_csv_usa_dataset_completo_no_paginado(self):
        """Exporta todos los socios filtrados desde el listado administrativo."""
        for indice in range(55):
            self.User.objects.create_user(
                username=f'socio_exportable_{indice:02d}',
                email=f'socio_exportable_{indice:02d}@example.com',
                password='ClaveSegura123',
                first_name='SocioExportable',
                last_name=f'Completo {indice:02d}',
                rut=self.rut_prueba(96000000 + indice),
                telefono_movil='+56933333333',
                rol=self.User.SOCIO,
            )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(
            reverse('usuarios:exportar_socios_completo', args=['csv']),
            {'nombre': 'SocioExportable'},
        )
        filas = list(csv.DictReader(StringIO(response.content.decode('utf-8-sig'))))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv; charset=utf-8')
        self.assertIn('attachment;', response['Content-Disposition'])
        self.assertIn(
            'reporte_socios_completo.csv',
            response['Content-Disposition'],
        )
        self.assertEqual(len(filas), 55)
        self.assertEqual(
            filas[-1]['Correo electronico'],
            'socio_exportable_54@example.com',
        )
        self.assertEqual(filas[-1]['Telefono movil'], '+56933333333')
        self.assertEqual(filas[-1]['Estado actual'], 'Activo')
        self.assertEqual(filas[-1]['Indicador asistencia'], 'Sin ausencias')
        self.assertNotIn('Ano', filas[-1])
        self.assertNotIn('Reuniones realizadas', filas[-1])
        self.assertNotIn('Nombre completo', filas[-1])

    def test_exportar_socios_xlsx_pdf_y_restringe_encargados(self):
        """Descarga XLSX/PDF desde socios y conserva permisos administrativos."""
        self.client.login(username='admin', password='ClaveSegura123')

        response_xlsx = self.client.get(
            reverse('usuarios:exportar_socios_completo', args=['xlsx']),
            {'rut': self.socio_user.rut},
        )
        with zipfile.ZipFile(BytesIO(response_xlsx.content)) as archivo:
            worksheet = archivo.read('xl/worksheets/sheet1.xml').decode('utf-8')

        self.assertEqual(response_xlsx.status_code, 200)
        self.assertIn('attachment;', response_xlsx['Content-Disposition'])
        self.assertIn(
            'reporte_socios_completo.xlsx',
            response_xlsx['Content-Disposition'],
        )
        self.assertIn('socio@example.com', worksheet)
        self.assertIn('+56922222222', worksheet)
        self.assertIn('Indicador asistencia', worksheet)
        self.assertIn('Estado actual', worksheet)
        self.assertNotIn('Nombre completo', worksheet)

        response_pdf = self.client.get(
            reverse('usuarios:exportar_socios_completo', args=['pdf']),
            {'rut': self.socio_user.rut},
        )

        self.assertEqual(response_pdf.status_code, 200)
        self.assertEqual(response_pdf['Content-Type'], 'application/pdf')
        self.assertIn(
            'reporte_socios_completo.pdf',
            response_pdf['Content-Disposition'],
        )
        self.assertTrue(response_pdf.content.startswith(b'%PDF-1.4'))
        self.assertIn(b'Indicador asistencia', response_pdf.content)
        self.assertIn(b'Estado actual', response_pdf.content)
        self.assertNotIn(b'Nombre completo', response_pdf.content)

        self.client.login(username='encargado', password='ClaveSegura123')
        response = self.client.get(
            reverse('usuarios:exportar_socios_completo', args=['csv']),
        )

        self.assertRedirects(response, reverse('usuarios:dashboard'))

    def test_listado_socios_filtra_y_separa_nombre_apellido(self):
        """Aplica filtros administrativos y muestra nombre y apellido separados."""
        socio_filtrado = self.User.objects.create_user(
            username='ana.socia',
            email='ana.socia@example.com',
            password='ClaveSegura123',
            first_name='Ana',
            last_name='Zapata',
            apellido_materno='Rojas',
            fecha_ingreso_proyecto=date(2026, 5, 15),
            rut='77.777.777-7',
            rol=self.User.SOCIO,
        )
        self.User.objects.create_user(
            username='bruno.socio',
            email='bruno.socio@example.com',
            password='ClaveSegura123',
            first_name='Bruno',
            last_name='Zapata',
            apellido_materno='Silva',
            rut='88.888.888-8',
            rol=self.User.SOCIO,
        )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(
            reverse('usuarios:listado_socios'),
            {
                'rut': '77.777.777-7',
                'nombre': 'Ana',
                'apellido': 'Rojas',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ordenar RUT ascendente')
        self.assertContains(response, 'Ordenar Nombre ascendente')
        self.assertContains(response, 'Ordenar Apellido paterno ascendente')
        self.assertContains(response, 'Ordenar Apellido materno ascendente')
        self.assertContains(response, f'title="Email: {socio_filtrado.email}"')
        self.assertContains(response, '<td class="fw-semibold">77777777-7</td>', html=True)
        self.assertContains(
            response,
            '<span class="table-cell-truncate is-name" title="Ana">Ana</span>',
            html=True,
        )
        self.assertContains(
            response,
            '<span class="table-cell-truncate is-name" title="Zapata">Zapata</span>',
            html=True,
        )
        self.assertContains(
            response,
            '<span class="table-cell-truncate is-name" title="Rojas">Rojas</span>',
            html=True,
        )
        self.assertNotContains(response, '15-05-2026')
        self.assertContains(response, 'value="77.777.777-7"')
        self.assertContains(response, 'value="Ana"')
        self.assertContains(response, 'value="Rojas"')
        self.assertNotContains(response, 'bruno.socio@example.com')
        self.assertNotContains(response, 'admin@example.com')

    def test_detalle_socio_muestra_fecha_ingreso(self):
        """Mueve la fecha de ingreso desde el listado al detalle administrativo."""
        self.socio_user.fecha_ingreso_proyecto = date(2026, 5, 15)
        self.socio_user.save(update_fields=['fecha_ingreso_proyecto'])

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(
            reverse('usuarios:detalle_socio', args=[self.socio_user.pk]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Detalle del socio')
        self.assertContains(response, 'Fecha de ingreso al proyecto')
        self.assertContains(response, '15-05-2026')
        self.assertContains(response, 'socio@example.com')
        self.assertContains(response, '+56922222222')
        self.assertContains(response, 'bi-calendar-check')
        self.assertContains(response, 'bi-shield-check')
        self.assertContains(response, 'bi-activity')
        self.assertContains(response, reverse('usuarios:editar_socio', args=[self.socio_user.pk]))

    def test_listado_socios_filtra_por_estado(self):
        """Permite filtrar socios activos e inactivos."""
        socio_inactivo = self.User.objects.create_user(
            username='socio.inactivo',
            email='socio.inactivo@example.com',
            password='ClaveSegura123',
            first_name='Socio',
            last_name='Inactivo',
            rut='55.555.555-5',
            rol=self.User.SOCIO,
            is_active=False,
        )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(
            reverse('usuarios:listado_socios'),
            {'estado': 'inactivo'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<option value="inactivo" selected>Inactivo</option>',
            html=True,
        )
        self.assertContains(response, f'title="Email: {socio_inactivo.email}"')
        self.assertNotContains(response, 'socio@example.com')

    def test_listado_socios_tiene_lista_responsiva_para_movil(self):
        """Replica el formato responsivo del listado administrativo de usuarios."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:listado_socios'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'd-none d-md-block')
        self.assertContains(response, 'list-group shadow-sm border rounded overflow-hidden d-md-none')
        self.assertContains(response, '<dt class="col-4 text-muted fw-semibold">NOMBRE</dt>', html=True)
        self.assertContains(response, '<dt class="col-4 text-muted fw-semibold">APELLIDO PATERNO</dt>', html=True)
        self.assertContains(response, '<dt class="col-4 text-muted fw-semibold">APELLIDO MATERNO</dt>', html=True)
        self.assertNotContains(response, '<dt class="col-4 text-muted fw-semibold">INGRESO</dt>', html=True)
        self.assertContains(response, '<dt class="col-4 text-muted fw-semibold">EMAIL</dt>', html=True)
        self.assertContains(response, '<dt class="col-4 text-muted fw-semibold">TELÉFONO</dt>', html=True)
        self.assertContains(response, 'socio@example.com')
        self.assertContains(response, '+56922222222')
        self.assertContains(response, 'aria-label="Contacto"')
        self.assertContains(response, 'data-bs-toggle="tooltip"')

        self.assertContains(response, '<span class="visually-hidden">ASISTENCIA</span>', html=True)

    def test_listado_socios_muestra_indicador_visual_de_asistencia(self):
        """Expone iconos de estado de asistencia en el listado administrativo."""
        self.client.login(username='admin', password='ClaveSegura123')

        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 20),
        )
        response = self.client.get(reverse('usuarios:listado_socios'))

        self.assertContains(response, 'title="Una inasistencia"')
        self.assertContains(response, 'aria-label="Estado de asistencia: Una inasistencia"')
        self.assertContains(response, 'bi-exclamation-triangle')

        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 21),
        )
        response = self.client.get(reverse('usuarios:listado_socios'))

        self.assertContains(response, 'title="Bloqueado"')
        self.assertContains(response, 'aria-label="Estado de asistencia: Bloqueado"')
        self.assertContains(response, 'bi-x-circle')

    def test_administrador_justifica_inasistencia_de_socio_bloqueado(self):
        """Permite justificar desde acciones del listado de asistencia."""
        ausencia_justificada = self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 20),
        )
        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 27),
        )
        url_justificar = reverse('usuarios:justificar_inasistencia', args=[self.socio_user.pk])
        url_detalle = reverse('usuarios:detalle_asistencia_socio', args=[self.socio_user.pk])

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:listado_socios'))
        self.assertNotContains(response, url_justificar)

        response = self.client.get(reverse('usuarios:listado_socios_asistencia'))
        self.assertNotContains(response, url_justificar)
        self.assertContains(response, url_detalle)
        self.assertContains(response, 'aria-label="Ver detalle para justificar inasistencia"')

        response = self.client.get(url_justificar)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Justificar inasistencia')
        self.assertContains(response, 'Reunion a justificar')
        self.assertContains(response, '20-05-2026 18:30 - Sede social')
        self.assertContains(response, 'motivo')

        response = self.client.post(
            url_justificar,
            {
                'asistencia': ausencia_justificada.pk,
                'motivo': 'Compromiso firmado',
            },
            follow=True,
        )

        self.assertRedirects(response, reverse('usuarios:listado_socios_asistencia'))
        self.assertContains(response, 'justificada correctamente')
        self.assertContains(response, 'text-bg-warning')
        self.assertContains(response, 'Una inasistencia')
        self.assertFalse(AsistenciaReunion.socio_esta_bloqueado(self.socio_user))
        justificacion = DesbloqueoSocio.objects.get(socio=self.socio_user)
        self.assertEqual(justificacion.asistencia, ausencia_justificada)
        self.assertEqual(justificacion.desbloqueado_por, self.admin_user)
        self.assertEqual(justificacion.motivo, 'Compromiso firmado')
        self.assertEqual(justificacion.inasistencias_al_desbloquear, 2)

    def test_administrador_envia_notificacion_de_bloqueo_desde_listado_asistencia(self):
        """Permite avisar por correo a un socio bloqueado desde el listado operativo."""
        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 20),
        )
        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 27),
        )
        url_notificar = reverse('usuarios:notificar_bloqueo_socio', args=[self.socio_user.pk])

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:listado_socios_asistencia'))
        self.assertContains(response, url_notificar)
        self.assertContains(response, 'aria-label="Enviar notificacion de bloqueo"')
        self.assertContains(response, 'bi-envelope')
        self.assertContains(
            response,
            'btn btn-danger btn-sm',
        )

        response = self.client.post(url_notificar, follow=True)

        self.assertRedirects(response, reverse('usuarios:listado_socios_asistencia'))
        self.assertContains(response, 'Notificacion de bloqueo enviada a socio@example.com.')
        self.assertContains(response, 'aria-label="Notificacion de bloqueo ya enviada"')
        self.assertContains(response, 'bi-envelope-check-fill')
        self.assertContains(response, 'btn btn-success btn-sm')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, 'Notificacion de bloqueo de asistencia')
        self.assertEqual(mail.outbox[0].to, ['socio@example.com'])
        self.assertEqual(NotificacionBloqueoSocio.objects.filter(socio=self.socio_user).count(), 1)
        self.assertIn(
            'Tu estado actual en el sistema de asistencia es: BLOQUEADO.',
            mail.outbox[0].body,
        )
        self.assertIn(
            'Registras 2 inasistencias pendientes de justificacion',
            mail.outbox[0].body,
        )
        self.assertIn('20-05-2026 18:30 - Sede social', mail.outbox[0].body)
        self.assertIn('27-05-2026 18:30 - Sede social', mail.outbox[0].body)

    def test_notificacion_bloqueo_no_reenvia_mientras_siga_el_mismo_bloqueo(self):
        """Evita duplicar correos si el bloqueo vigente ya fue notificado."""
        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 20),
        )
        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 27),
        )
        url_notificar = reverse('usuarios:notificar_bloqueo_socio', args=[self.socio_user.pk])

        self.client.login(username='admin', password='ClaveSegura123')
        self.client.post(url_notificar, follow=True)
        response = self.client.post(url_notificar, follow=True)

        self.assertRedirects(response, reverse('usuarios:listado_socios_asistencia'))
        self.assertContains(
            response,
            'La notificacion de bloqueo ya fue enviada para el bloqueo actual.',
        )
        self.assertContains(response, 'aria-label="Notificacion de bloqueo ya enviada"')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(NotificacionBloqueoSocio.objects.filter(socio=self.socio_user).count(), 1)

    def test_notificacion_bloqueo_vuelve_a_habilitarse_si_cambia_el_bloqueo(self):
        """Reactiva el envio cuando el socio cae en un nuevo bloqueo distinto."""
        ausencia_primera = self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 20),
        )
        ausencia_segunda = self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 27),
        )
        url_notificar = reverse('usuarios:notificar_bloqueo_socio', args=[self.socio_user.pk])

        self.client.login(username='admin', password='ClaveSegura123')
        self.client.post(url_notificar, follow=True)

        DesbloqueoSocio.registrar(
            socio=self.socio_user,
            usuario=self.admin_user,
            motivo='Revision administrativa',
            asistencia=ausencia_primera,
        )
        self.assertFalse(
            NotificacionBloqueoSocio.bloqueo_actual_ya_notificado(self.socio_user)
        )

        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 6, 3),
        )
        self.assertTrue(AsistenciaReunion.socio_esta_bloqueado(self.socio_user))
        self.assertNotEqual(
            AsistenciaReunion.obtener_firma_bloqueo_socio(self.socio_user),
            NotificacionBloqueoSocio.objects.get(socio=self.socio_user).firma_bloqueo,
        )

        response = self.client.get(reverse('usuarios:listado_socios_asistencia'))

        self.assertContains(response, url_notificar)
        self.assertContains(response, 'aria-label="Enviar notificacion de bloqueo"')
        self.assertContains(response, 'btn btn-danger btn-sm')
        self.assertNotContains(response, 'aria-label="Notificacion de bloqueo ya enviada"')
        self.assertEqual(ausencia_segunda.estado, AsistenciaReunion.AUSENTE)

    def test_notificacion_bloqueo_rechaza_socios_no_bloqueados(self):
        """Evita enviar el aviso cuando el socio todavia no cumple condicion de bloqueo."""
        url_notificar = reverse('usuarios:notificar_bloqueo_socio', args=[self.socio_user.pk])

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:listado_socios_asistencia'))
        self.assertNotContains(response, url_notificar)
        self.assertContains(response, 'aria-label="Notificacion de bloqueo no disponible"')
        self.assertContains(response, 'bi-envelope')
        self.assertContains(response, 'btn-outline-secondary btn-sm text-muted')

        response = self.client.post(url_notificar, follow=True)

        self.assertRedirects(response, reverse('usuarios:listado_socios_asistencia'))
        self.assertContains(response, 'El socio no esta bloqueado por inasistencias.')
        self.assertEqual(len(mail.outbox), 0)

    def test_notificacion_bloqueo_solo_disponible_para_administrador(self):
        """Impide que encargados envien avisos de bloqueo a socios."""
        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 20),
        )
        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 27),
        )
        url_notificar = reverse('usuarios:notificar_bloqueo_socio', args=[self.socio_user.pk])

        self.client.login(username='encargado', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:listado_socios_asistencia'))
        self.assertNotContains(response, url_notificar)
        self.assertContains(response, 'aria-label="Notificacion de bloqueo no disponible"')
        self.assertContains(response, 'bi-envelope')

        response = self.client.post(url_notificar, follow=True)

        self.assertRedirects(response, reverse('usuarios:dashboard'))
        self.assertEqual(len(mail.outbox), 0)

    def test_detalle_asistencia_socio_muestra_justificaciones_y_pendientes(self):
        """Muestra trazabilidad por socio desde el listado operativo."""
        ausencia_justificada = self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 20),
        )
        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 27),
        )
        DesbloqueoSocio.registrar(
            socio=self.socio_user,
            usuario=self.admin_user,
            motivo='Compromiso firmado',
            asistencia=ausencia_justificada,
        )
        detalle_url = reverse('usuarios:detalle_asistencia_socio', args=[self.socio_user.pk])

        self.client.login(username='encargado', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:listado_socios_asistencia'))
        self.assertContains(response, 'Justificaciones')
        self.assertContains(response, detalle_url)
        self.assertContains(response, 'aria-label="Ver detalle de asistencia"')

        response = self.client.get(detalle_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Detalle del socio')
        self.assertContains(response, 'Compromiso firmado')
        self.assertContains(response, '20-05-2026')
        self.assertContains(response, '27-05-2026')
        self.assertContains(response, 'Ausencias pendientes de justificaci&oacute;n')

    def test_detalle_asistencia_socio_permite_justificar_ausencia_pendiente(self):
        """Enlaza cada ausencia pendiente al formulario con la reunion preseleccionada."""
        ausencia_justificable = self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 20),
        )
        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 27),
        )
        detalle_url = reverse('usuarios:detalle_asistencia_socio', args=[self.socio_user.pk])
        justificar_url = reverse('usuarios:justificar_inasistencia', args=[self.socio_user.pk])
        url_justificar_ausencia = (
            f'{justificar_url}?anio={timezone.localdate().year}'
            f'&asistencia={ausencia_justificable.pk}'
        )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(detalle_url)
        self.assertContains(response, url_justificar_ausencia)
        self.assertContains(response, 'aria-label="Justificar esta inasistencia"')

        response = self.client.get(url_justificar_ausencia)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['form'].initial['asistencia'], ausencia_justificable)

    def test_justificacion_admin_desbloquea_inasistencia_de_anio_anterior(self):
        """Permite justificar ausencias antiguas que mantienen el bloqueo vigente."""
        anio_actual = timezone.localdate().year
        anio_previo = anio_actual - 1
        ausencia_justificable = self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(anio_previo, 5, 20),
        )
        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(anio_previo, 5, 27),
        )
        justificar_url = reverse(
            'usuarios:justificar_inasistencia',
            args=[self.socio_user.pk],
        )
        url_justificar_ausencia = (
            f'{justificar_url}?anio={anio_actual}'
            f'&asistencia={ausencia_justificable.pk}'
        )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(url_justificar_ausencia)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'20-05-{anio_previo}')
        self.assertEqual(response.context['form'].initial['asistencia'], ausencia_justificable)

        response = self.client.post(
            justificar_url,
            {
                'anio': anio_actual,
                'asistencia': ausencia_justificable.pk,
                'motivo': 'Revision administrativa',
            },
            follow=True,
        )

        self.assertRedirects(response, reverse('usuarios:listado_socios_asistencia'))
        self.assertFalse(AsistenciaReunion.socio_esta_bloqueado(self.socio_user))
        self.assertTrue(
            DesbloqueoSocio.objects.filter(
                socio=self.socio_user,
                asistencia=ausencia_justificable,
            ).exists()
        )
    def test_listado_justificaciones_admin_muestra_trazabilidad_general(self):
        """Expone una vista general de justificaciones solo para administradores."""
        ausencia_justificada = self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 20),
        )
        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 27),
        )
        DesbloqueoSocio.registrar(
            socio=self.socio_user,
            usuario=self.admin_user,
            motivo='Control medico',
            asistencia=ausencia_justificada,
        )
        url = reverse('usuarios:listado_justificaciones')

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Historial general de justificaciones')
        self.assertContains(response, 'aria-label="Filtros de justificaciones"')
        self.assertContains(response, self.socio_user.rut)
        self.assertContains(response, '20-05-2026')
        self.assertContains(response, 'Control medico')
        self.assertContains(response, 'Sede social')

        self.client.login(username='encargado', password='ClaveSegura123')
        response = self.client.get(url)
        self.assertRedirects(response, reverse('usuarios:dashboard'))

    def test_listado_justificaciones_filtra_por_socio_y_motivo(self):
        """Permite ubicar justificaciones por socio y causa."""
        ausencia_justificada = self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 20),
        )
        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 27),
        )
        DesbloqueoSocio.registrar(
            socio=self.socio_user,
            usuario=self.admin_user,
            motivo='Control medico',
            asistencia=ausencia_justificada,
        )
        otro_socio = self.User.objects.create_user(
            username='otro.justificado',
            email='otro.justificado@example.com',
            password='ClaveSegura123',
            first_name='Otro',
            last_name='Justificado',
            rut='55.555.555-5',
            rol=self.User.SOCIO,
        )
        otra_ausencia = self.registrar_asistencia_historica(
            otro_socio,
            AsistenciaReunion.AUSENTE,
            date(2026, 6, 3),
        )
        self.registrar_asistencia_historica(
            otro_socio,
            AsistenciaReunion.AUSENTE,
            date(2026, 6, 10),
        )
        DesbloqueoSocio.registrar(
            socio=otro_socio,
            usuario=self.admin_user,
            motivo='Trabajo fuera',
            asistencia=otra_ausencia,
        )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(
            reverse('usuarios:listado_justificaciones'),
            {
                'rut': self.socio_user.rut,
                'nombre': 'Socio',
                'apellido': 'Prueba',
                'motivo': 'Control',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['justificaciones']), 1)
        self.assertContains(response, f'value="{self.socio_user.rut}"')
        self.assertContains(response, 'value="Socio"')
        self.assertContains(response, 'value="Prueba"')
        self.assertContains(response, 'value="Control"')
        self.assertContains(response, 'Limpiar')
        self.assertContains(response, 'Control medico')
        self.assertNotContains(response, 'Trabajo fuera')
        self.assertNotContains(response, otro_socio.rut)

    def test_listado_justificaciones_paginacion_conserva_filtros(self):
        """Mantiene filtros activos al navegar paginas de justificaciones."""
        for indice in range(51):
            socio = self.User.objects.create_user(
                username=f'justificacion_filtro_{indice:02d}',
                email=f'justificacion_filtro_{indice:02d}@example.com',
                password='ClaveSegura123',
                first_name='JustificacionFiltro',
                last_name=f'Paginacion {indice:02d}',
                rut=self.rut_prueba(61000000 + indice),
                rol=self.User.SOCIO,
            )
            ausencia_justificada = self.registrar_asistencia_historica(
                socio,
                AsistenciaReunion.AUSENTE,
                date(2026, 1, 1),
            )
            self.registrar_asistencia_historica(
                socio,
                AsistenciaReunion.AUSENTE,
                date(2026, 1, 2),
            )
            DesbloqueoSocio.registrar(
                socio=socio,
                usuario=self.admin_user,
                motivo='Filtro operativo',
                asistencia=ausencia_justificada,
            )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(
            reverse('usuarios:listado_justificaciones'),
            {'nombre': 'JustificacionFiltro'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['justificaciones']), 50)
        self.assertContains(response, 'nombre=JustificacionFiltro&page=2')

    def test_justificar_inasistencia_requiere_motivo(self):
        """Mantiene bloqueado al socio cuando falta el motivo."""
        ausencia_justificada = self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 20),
        )
        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 27),
        )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:justificar_inasistencia', args=[self.socio_user.pk]),
            {'asistencia': ausencia_justificada.pk, 'motivo': '   '},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Este campo es obligatorio.')
        self.assertTrue(AsistenciaReunion.socio_esta_bloqueado(self.socio_user))
        self.assertFalse(DesbloqueoSocio.objects.filter(socio=self.socio_user).exists())

    def test_justificar_inasistencia_bloquea_si_no_tiene_bloqueo(self):
        """Evita justificar socios que no cumplen la regla de bloqueo."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(
            reverse('usuarios:justificar_inasistencia', args=[self.socio_user.pk]),
            follow=True,
        )

        self.assertRedirects(response, reverse('usuarios:listado_socios_asistencia'))
        self.assertContains(response, 'El socio no esta bloqueado por inasistencias.')
        self.assertFalse(DesbloqueoSocio.objects.filter(socio=self.socio_user).exists())

    def test_justificar_inasistencia_solo_disponible_para_administrador(self):
        """Protege la justificacion de inasistencias para usuarios no autorizados."""
        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 20),
        )
        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 27),
        )
        url = reverse('usuarios:justificar_inasistencia', args=[self.socio_user.pk])

        self.client.login(username='encargado', password='ClaveSegura123')
        response = self.client.post(url, {'motivo': 'Compromiso firmado'})
        self.assertRedirects(response, reverse('usuarios:dashboard'))

        self.client.login(username='socio', password='ClaveSegura123')
        response = self.client.post(url, {'motivo': 'Compromiso firmado'})
        self.assertRedirects(response, reverse('usuarios:mis_asistencias'))

        self.assertTrue(AsistenciaReunion.socio_esta_bloqueado(self.socio_user))
        self.assertFalse(DesbloqueoSocio.objects.filter(socio=self.socio_user).exists())

    def test_listado_socios_paginacion_conserva_filtros(self):
        """Mantiene los filtros activos al navegar paginas de socios."""
        for indice in range(51):
            self.User.objects.create_user(
                username=f'socio_filtro_{indice:02d}',
                email=f'socio_filtro_{indice:02d}@example.com',
                password='ClaveSegura123',
                first_name='FiltroSocio',
                last_name=f'Paginacion {indice:02d}',
                rut=self.rut_prueba(81000000 + indice),
                rol=self.User.SOCIO,
            )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(
            reverse('usuarios:listado_socios'),
            {'nombre': 'FiltroSocio'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['socios']), 50)
        self.assertContains(response, 'nombre=FiltroSocio&page=2')

    def test_listado_socios_ordena_columnas_ascendente_y_descendente(self):
        """Ordena socios por columnas seleccionadas desde el encabezado."""
        self.User.objects.create_user(
            username='aaron.socio',
            email='aaron.socio@example.com',
            password='ClaveSegura123',
            first_name='Aaron',
            last_name='Orden',
            rut='82.222.222-6',
            rol=self.User.SOCIO,
        )
        self.User.objects.create_user(
            username='zulu.socio',
            email='zulu.socio@example.com',
            password='ClaveSegura123',
            first_name='Zulu',
            last_name='Orden',
            rut='83.333.333-K',
            rol=self.User.SOCIO,
        )

        self.client.login(username='admin', password='ClaveSegura123')

        response = self.client.get(
            reverse('usuarios:listado_socios'),
            {'orden': 'nombre', 'direccion': 'asc'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['socios'][0].username, 'aaron.socio')
        self.assertContains(response, 'Ordenar Nombre descendente')
        self.assertContains(response, 'aria-current="true"')

        response = self.client.get(
            reverse('usuarios:listado_socios'),
            {'orden': 'nombre', 'direccion': 'desc'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['socios'][0].username, 'zulu.socio')
        self.assertContains(response, 'Ordenar Nombre ascendente')

    def test_listado_socios_paginacion_conserva_orden(self):
        """Mantiene el orden activo al navegar paginas de socios."""
        for indice in range(51):
            self.User.objects.create_user(
                username=f'socio_orden_{indice:02d}',
                email=f'socio_orden_{indice:02d}@example.com',
                password='ClaveSegura123',
                first_name='OrdenSocio',
                last_name=f'Paginacion {indice:02d}',
                rut=self.rut_prueba(84000000 + indice),
                rol=self.User.SOCIO,
            )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(
            reverse('usuarios:listado_socios'),
            {'nombre': 'OrdenSocio', 'orden': 'apellido', 'direccion': 'desc'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['socios']), 50)
        self.assertContains(
            response,
            'nombre=OrdenSocio&amp;orden=apellido&amp;direccion=desc&page=2',
        )

    def test_encargado_accede_a_asistencia_y_ve_solo_socios(self):
        """Permite al encargado ver el listado operativo de socios."""
        self.client.login(username='encargado', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:listado_socios_asistencia'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.socio_user.rut)
        self.assertNotContains(response, self.socio_user.email)
        self.assertNotContains(response, 'Registrar socio')
        self.assertNotContains(response, 'Editar')
        self.assertContains(response, 'aria-label="Ver detalle de asistencia"')
        self.assertNotContains(response, 'aria-label="Sin acceso a esta funcionalidad"')
        self.assertNotContains(response, 'bi-lock-fill')
        self.assertNotContains(response, reverse('usuarios:editar_socio', args=[self.socio_user.pk]))
        self.assertNotContains(response, 'admin@example.com')
        self.assertNotContains(response, 'encargado@example.com')

    def test_formularios_cargan_en_layout_lateral(self):
        """Verifica que los formularios principales carguen con sidebar global."""
        self.client.login(username='admin', password='ClaveSegura123')
        urls = [
            reverse('usuarios:registro_usuario'),
            reverse('usuarios:registro_socio'),
            reverse('usuarios:editar_usuario', args=[self.encargado_user.pk]),
            reverse('usuarios:editar_socio', args=[self.socio_user.pk]),
            reverse('usuarios:cambiar_mi_password'),
        ]

        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'app-sidebar')
                self.assertContains(response, 'Valle San Ramon')

    def test_formularios_con_rut_activan_formateo_visual(self):
        """Expone el atributo usado por el formateo visual de RUT."""
        self.client.login(username='admin', password='ClaveSegura123')
        urls = [
            reverse('usuarios:registro_usuario'),
            reverse('usuarios:registro_socio'),
            reverse('usuarios:editar_usuario', args=[self.encargado_user.pk]),
            reverse('usuarios:editar_socio', args=[self.socio_user.pk]),
        ]

        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'data-rut-format="true"')

    def test_edicion_socio_no_muestra_check_de_estado(self):
        """Reserva activar/desactivar socios para el flujo de gestion de estado."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:editar_socio', args=[self.socio_user.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'email_confirmacion')
        self.assertNotContains(response, 'name="is_active"')
        self.assertNotContains(response, 'Socio activo')

    def test_edicion_usuario_no_muestra_check_de_estado(self):
        """Reserva activar/desactivar usuarios para la accion dedicada del listado."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:editar_usuario', args=[self.encargado_user.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('username', response.context['form'].fields)
        self.assertNotContains(response, 'name="username"')
        self.assertContains(
            response,
            '<strong class="fs-5 text-body">encargado</strong>',
            html=True,
        )
        self.assertNotContains(response, '<p class="h4 mb-0">encargado</p>', html=True)
        self.assertNotContains(response, 'conservar trazabilidad')
        self.assertNotContains(response, 'name="is_active"')
        self.assertNotContains(response, 'Usuario activo')
        self.assertNotContains(response, 'value="SOCIO"')
        self.assertNotContains(response, 'value="SUPERADMINISTRADOR"')

    def test_administrador_crea_usuario(self):
        """Permite al administrador crear un usuario operativo."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:registro_usuario'),
            {
                'username': 'encargado_nuevo',
                'email': 'encargado.nuevo@example.com',
                'first_name': 'Encargado',
                'last_name': 'Registro',
                'rut': '333333333',
                'telefono_movil': '+56933333333',
                'rol': self.User.ENCARGADO_REGISTRO,
                'is_active': 'on',
                'password1': 'ClaveSegura123',
                'password2': 'ClaveSegura123',
            },
            follow=True,
        )
        self.assertRedirects(response, reverse('usuarios:listado_usuarios'))
        usuario = self.User.objects.get(username='encargado_nuevo')
        self.assertEqual(usuario.rut, '33333333-3')
        self.assertEqual(usuario.telefono_movil, '+56933333333')
        self.assertContains(response, 'Usuario encargado_nuevo creado correctamente.')
        self.assertContains(response, 'data-app-message')
        self.assertContains(response, 'data-message-level="success"')
        self.assertContains(response, 'js/app.js')

    def test_formularios_rechazan_rut_con_digito_verificador_incorrecto(self):
        """Valida el digito verificador chileno en ingresos de RUT."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:registro_usuario'),
            {
                'username': 'rut_invalido',
                'email': 'rut.invalido@example.com',
                'first_name': 'Rut',
                'last_name': 'Invalido',
                'rut': '33.333.333-4',
                'telefono_movil': '+56933333333',
                'rol': self.User.ENCARGADO_REGISTRO,
                'is_active': 'on',
                'password1': 'ClaveSegura123',
                'password2': 'ClaveSegura123',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ingrese un RUT valido.')
        self.assertFalse(self.User.objects.filter(username='rut_invalido').exists())

        usuario = self.User(
            username='modelo.rut.invalido',
            email='modelo.rut.invalido@example.com',
            first_name='Modelo',
            last_name='Invalido',
            rut='33.333.333-4',
            rol=self.User.ENCARGADO_REGISTRO,
        )
        with self.assertRaises(ValidationError):
            usuario.full_clean()

    def test_registro_usuario_interno_no_ofrece_rol_socio(self):
        """Reserva el formulario interno para administradores y encargados."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:registro_usuario'))
        self.assertContains(response, 'value="+56"')
        self.assertContains(response, 'data-phone-prefix="+56"')
        self.assertContains(response, 'pattern="\\+56[0-9]{9}"')
        self.assertContains(response, 'ADMINISTRADOR')
        self.assertContains(response, 'ENCARGADO_REGISTRO')
        self.assertNotContains(response, 'value="SOCIO"')
        self.assertNotContains(response, 'value="SUPERADMINISTRADOR"')

    def test_administrador_no_crea_socio_desde_registro_interno(self):
        """Impide crear socios desde el formulario con username y password."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:registro_usuario'),
            {
                'username': 'socio_interno',
                'email': 'socio.interno@example.com',
                'first_name': 'Socio',
                'last_name': 'Interno',
                'rut': '88.888.888-8',
                'rol': self.User.SOCIO,
                'is_active': 'on',
                'password1': 'ClaveSegura123',
                'password2': 'ClaveSegura123',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.User.objects.filter(email='socio.interno@example.com').exists())

    def test_registro_socio_no_solicita_password_inicial(self):
        """Renderiza el formulario de socio sin contrasena inicial."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:registro_socio'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'email_confirmacion')
        self.assertContains(response, 'name="telefono_movil"')
        self.assertContains(response, 'name="apellido_materno"')
        self.assertContains(response, 'name="fecha_ingreso_proyecto"')
        self.assertContains(response, 'type="date"')
        self.assertContains(response, f'value="{timezone.localdate().isoformat()}"')
        self.assertContains(response, 'value="+56"')
        self.assertNotContains(response, 'name="password1"')
        self.assertNotContains(response, 'name="password2"')
        self.assertNotContains(response, 'Sugerencia: usar el RUT del socio como contrasena inicial')
        self.assertNotContains(response, 'name="username"')

    def test_telefono_movil_chileno_exige_prefijo_y_nueve_digitos(self):
        """Valida el formato chileno +56 seguido de nueve dígitos."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:registro_socio'),
            {
                'email': 'socio.telefono@example.com',
                'email_confirmacion': 'socio.telefono@example.com',
                'first_name': 'Socio',
                'last_name': 'Telefono',
                'rut': '76.666.666-3',
                'telefono_movil': '+561234',
                'is_active': 'on',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'Ingrese un teléfono móvil chileno con formato +56 seguido de 9 dígitos.',
        )
        self.assertFalse(self.User.objects.filter(email='socio.telefono@example.com').exists())

    def test_registro_socio_valida_confirmacion_de_correo(self):
        """Exige confirmar el correo al registrar un socio."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:registro_socio'),
            {
                'email': 'socio.nuevo@example.com',
                'email_confirmacion': 'otro.correo@example.com',
                'first_name': 'Socio',
                'last_name': 'Nuevo',
                'apellido_materno': 'Materno',
                'rut': '66.666.666-6',
                'telefono_movil': '+56966666666',
                'fecha_ingreso_proyecto': '',
                'is_active': 'on',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.User.objects.filter(email='socio.nuevo@example.com').exists())

    def test_encargado_no_accede_a_listado_de_usuarios(self):
        """Impide que el encargado entre al listado de gestion."""
        self.client.login(username='encargado', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:listado_usuarios'))
        self.assertRedirects(response, reverse('usuarios:dashboard'))
        response = self.client.get(reverse('usuarios:listado_socios'))
        self.assertRedirects(response, reverse('usuarios:dashboard'))

    def test_administrador_registra_socios(self):
        """Permite al administrador registrar cuentas de socio."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:registro_socio'),
            {
                'email': 'socio.nuevo@example.com',
                'email_confirmacion': 'socio.nuevo@example.com',
                'first_name': 'Socio',
                'last_name': 'Nuevo',
                'apellido_materno': 'Materno',
                'rut': '66.666.666-6',
                'telefono_movil': '+56966666666',
                'fecha_ingreso_proyecto': '',
                'is_active': 'on',
            },
        )
        self.assertRedirects(response, reverse('usuarios:listado_socios'))
        usuario = self.User.objects.get(email='socio.nuevo@example.com')
        self.assertEqual(usuario.rol, self.User.SOCIO)
        self.assertEqual(usuario.username, 'socio.nuevo@example.com')
        self.assertEqual(usuario.telefono_movil, '+56966666666')
        self.assertEqual(usuario.apellido_materno, 'Materno')
        self.assertEqual(usuario.fecha_ingreso_proyecto, timezone.localdate())
        self.assertFalse(usuario.has_usable_password())
        self.assertFalse(usuario.check_password('66666666-6'))

    def test_encargado_no_accede_a_registro_socio(self):
        """Impide que el encargado vea o use el alta de socios."""
        self.client.login(username='encargado', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:registro_socio'))
        self.assertRedirects(response, reverse('usuarios:dashboard'))

        response = self.client.post(
            reverse('usuarios:registro_socio'),
            {
                'email': 'socio.no.permitido@example.com',
                'email_confirmacion': 'socio.no.permitido@example.com',
                'first_name': 'Socio',
                'last_name': 'No Permitido',
                'rut': '66.666.666-6',
                'is_active': 'on',
            },
        )
        self.assertRedirects(response, reverse('usuarios:dashboard'))
        self.assertFalse(self.User.objects.filter(email='socio.no.permitido@example.com').exists())

    def test_encargado_no_accede_a_registro_de_usuarios_internos(self):
        """Impide que el encargado use el alta de usuarios internos."""
        self.client.login(username='encargado', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:registro_usuario'),
            {
                'username': 'admin_no_permitido',
                'email': 'admin.no.permitido@example.com',
                'first_name': 'Admin',
                'last_name': 'No Permitido',
                'rut': '55.555.555-5',
                'rol': self.User.ADMINISTRADOR,
                'is_active': 'on',
                'password1': 'ClaveSegura123',
                'password2': 'ClaveSegura123',
            },
        )
        self.assertRedirects(response, reverse('usuarios:dashboard'))
        self.assertFalse(self.User.objects.filter(username='admin_no_permitido').exists())

    def test_encargado_no_crea_otro_encargado(self):
        """Impide que el encargado cree usuarios internos."""
        self.client.login(username='encargado', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:registro_usuario'),
            {
                'username': 'encargado_no_permitido',
                'email': 'encargado.no.permitido@example.com',
                'first_name': 'Encargado',
                'last_name': 'No Permitido',
                'rut': '77.777.777-7',
                'rol': self.User.ENCARGADO_REGISTRO,
                'is_active': 'on',
                'password1': 'ClaveSegura123',
                'password2': 'ClaveSegura123',
            },
        )
        self.assertRedirects(response, reverse('usuarios:dashboard'))
        self.assertFalse(self.User.objects.filter(username='encargado_no_permitido').exists())

    def test_encargado_no_edita_administrador(self):
        """Impide que el encargado modifique un usuario administrador."""
        self.client.login(username='encargado', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:editar_usuario', args=[self.admin_user.pk]),
            {
                'username': 'admin',
                'email': 'admin@example.com',
                'first_name': 'Admin',
                'last_name': 'Sistema',
                'rut': '11.111.111-1',
                'rol': self.User.SOCIO,
                'is_active': 'on',
            },
        )
        self.assertRedirects(response, reverse('usuarios:dashboard'))
        self.admin_user.refresh_from_db()
        self.assertEqual(self.admin_user.rol, self.User.ADMINISTRADOR)

    def test_encargado_no_edita_socios(self):
        """Impide que el encargado edite socios desde la gestion general."""
        self.client.login(username='encargado', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:editar_usuario', args=[self.socio_user.pk]),
            {
                'username': 'socio_editado',
                'email': 'socio.editado@example.com',
                'first_name': 'Socio',
                'last_name': 'Editado',
                'rut': '22.222.222-2',
                'rol': self.User.SOCIO,
                'is_active': 'on',
            },
        )
        self.assertRedirects(response, reverse('usuarios:dashboard'))
        self.socio_user.refresh_from_db()
        self.assertEqual(self.socio_user.username, 'socio')
        self.assertEqual(self.socio_user.email, 'socio@example.com')

    def test_encargado_no_edita_socio_desde_formulario_especifico(self):
        """Impide que el encargado actualice datos del socio."""
        self.client.login(username='encargado', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:editar_socio', args=[self.socio_user.pk]),
            {
                'email': 'SOCIO.ACTUALIZADO@EXAMPLE.COM',
                'first_name': 'Socio',
                'last_name': 'Actualizado',
                'rut': '99.999.999-9',
            },
        )
        self.assertRedirects(response, reverse('usuarios:dashboard'))
        self.socio_user.refresh_from_db()
        self.assertEqual(self.socio_user.email, 'socio@example.com')
        self.assertEqual(self.socio_user.username, 'socio')
        self.assertEqual(self.socio_user.rut, '22222222-2')
        self.assertEqual(self.socio_user.rol, self.User.SOCIO)

    def test_encargado_no_desactiva_administrador(self):
        """Impide que el encargado desactive cuentas administradoras."""
        self.client.login(username='encargado', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:cambiar_estado_usuario', args=[self.admin_user.pk]),
        )
        self.assertRedirects(response, reverse('usuarios:dashboard'))
        self.admin_user.refresh_from_db()
        self.assertTrue(self.admin_user.is_active)

    def test_encargado_no_cambia_estado_de_socios(self):
        """Impide que el encargado active o desactive usuarios."""
        self.client.login(username='encargado', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:cambiar_estado_usuario', args=[self.socio_user.pk]),
        )
        self.assertRedirects(response, reverse('usuarios:dashboard'))
        self.socio_user.refresh_from_db()
        self.assertTrue(self.socio_user.is_active)

    def test_administrador_edita_usuario_sin_modificar_rut(self):
        """Normaliza email y rol, pero conserva el RUT original al editar."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:editar_usuario', args=[self.encargado_user.pk]),
            {
                'email': 'ENCARGADO.ACTUALIZADO@EXAMPLE.COM',
                'first_name': 'Encargado',
                'last_name': 'Actualizado',
                'rut': '99.999.999-9',
                'telefono_movil': '+56955555555',
                'rol': self.User.ADMINISTRADOR,
                'is_active': 'on',
            },
        )
        self.assertRedirects(response, reverse('usuarios:listado_usuarios'))
        self.encargado_user.refresh_from_db()
        self.assertEqual(self.encargado_user.email, 'encargado.actualizado@example.com')
        self.assertEqual(self.encargado_user.rut, '44444444-4')
        self.assertEqual(self.encargado_user.telefono_movil, '+56955555555')
        self.assertEqual(self.encargado_user.rol, self.User.ADMINISTRADOR)
        self.assertEqual(self.encargado_user.username, 'encargado')

    def test_edicion_usuario_rechaza_cambio_de_username_manipulado(self):
        """Rechaza el POST manipulado antes de mostrar exito."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:editar_usuario', args=[self.encargado_user.pk]),
            {
                'username': 'encargado_editado',
                'email': 'encargado@example.com',
                'first_name': 'Encargado',
                'last_name': 'Registro',
                'rut': '44.444.444-4',
                'telefono_movil': '+56944444444',
                'rol': self.User.ENCARGADO_REGISTRO,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'El nombre de usuario no puede modificarse.')
        self.assertNotContains(response, 'Usuario actualizado correctamente.')
        self.encargado_user.refresh_from_db()
        self.assertEqual(self.encargado_user.username, 'encargado')

    def test_editar_usuario_redirige_socios_a_formulario_especifico(self):
        """Evita editar socios desde el formulario de usuarios internos."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:editar_usuario', args=[self.socio_user.pk]))
        self.assertRedirects(response, reverse('usuarios:editar_socio', args=[self.socio_user.pk]))

    def test_administrador_edita_socio_sin_cambiar_perfil(self):
        """Mantiene a los socios con rol y username inmutables."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:editar_socio', args=[self.socio_user.pk]),
            {
                'email': 'socio.admin@example.com',
                'email_confirmacion': 'socio.admin@example.com',
                'first_name': 'Socio',
                'last_name': 'Admin',
                'apellido_materno': 'Materno',
                'rut': '99.999.999-9',
                'telefono_movil': '+56977777777',
                'fecha_ingreso_proyecto': '2026-05-20',
            },
        )
        self.assertRedirects(response, reverse('usuarios:listado_socios'))
        self.socio_user.refresh_from_db()
        self.assertEqual(self.socio_user.email, 'socio.admin@example.com')
        self.assertEqual(self.socio_user.username, 'socio')
        self.assertEqual(self.socio_user.rut, '22222222-2')
        self.assertEqual(self.socio_user.telefono_movil, '+56977777777')
        self.assertEqual(self.socio_user.apellido_materno, 'Materno')
        self.assertEqual(self.socio_user.fecha_ingreso_proyecto, date(2026, 5, 20))
        self.assertEqual(self.socio_user.rol, self.User.SOCIO)

    def test_modelo_impide_promover_socio_a_rol_interno(self):
        """Protege la integridad aunque se intente cambiar el rol fuera de vistas."""
        self.socio_user.rol = self.User.ADMINISTRADOR

        with self.assertRaises(ValidationError):
            self.socio_user.save()

        self.socio_user.refresh_from_db()
        self.assertEqual(self.socio_user.rol, self.User.SOCIO)

    def test_modelo_impide_privilegios_django_en_socio(self):
        """Evita que un socio sea staff o superusuario por canales alternativos."""
        self.socio_user.is_staff = True

        with self.assertRaises(ValidationError):
            self.socio_user.save()

        self.socio_user.refresh_from_db()
        self.assertFalse(self.socio_user.is_staff)
        self.assertFalse(self.socio_user.is_superuser)

    def test_modelo_impide_convertir_usuario_interno_en_socio(self):
        """Reserva el alta de socios para su flujo especifico."""
        self.encargado_user.rol = self.User.SOCIO

        with self.assertRaises(ValidationError):
            self.encargado_user.save()

        self.encargado_user.refresh_from_db()
        self.assertEqual(self.encargado_user.rol, self.User.ENCARGADO_REGISTRO)

    def test_modelo_impide_modificar_username(self):
        """Protege trazabilidad de logs aunque se intente cambiar fuera de vistas."""
        self.encargado_user.username = 'encargado_editado'

        with self.assertRaises(ValidationError):
            self.encargado_user.save()

        self.encargado_user.refresh_from_db()
        self.assertEqual(self.encargado_user.username, 'encargado')

    def test_admin_deja_campos_sensibles_de_socio_solo_lectura(self):
        """Cierra el bypass del admin Django para cuentas de socio existentes."""
        usuario_admin = UsuarioAdmin(self.User, AdminSite())

        readonly_fields = usuario_admin.get_readonly_fields(None, obj=self.socio_user)

        self.assertIn('username', readonly_fields)
        self.assertIn('rol', readonly_fields)
        self.assertIn('is_staff', readonly_fields)
        self.assertIn('is_superuser', readonly_fields)

    def test_admin_deja_username_solo_lectura_en_usuarios_existentes(self):
        """Evita renombrar cuentas internas desde el admin Django."""
        usuario_admin = UsuarioAdmin(self.User, AdminSite())

        readonly_fields = usuario_admin.get_readonly_fields(None, obj=self.encargado_user)

        self.assertIn('username', readonly_fields)

    def test_create_superuser_usa_rol_superadministrador_por_defecto(self):
        """Separa superusuarios de los administradores del sistema web."""
        usuario = self.User.objects.create_superuser(
            username='supervisor',
            email='supervisor@example.com',
            password='ClaveSegura123',
            first_name='Super',
            last_name='Usuario',
            rut='12.345.678-5',
        )

        self.assertEqual(usuario.rol, self.User.SUPERADMINISTRADOR)
        self.assertTrue(usuario.is_staff)
        self.assertTrue(usuario.is_superuser)

    def test_modelo_impide_rol_superadministrador_sin_superuser(self):
        """Reserva el rol especializado solo para cuentas superuser."""
        usuario = self.User(
            username='super_rol_manual',
            email='super.rol.manual@example.com',
            first_name='Super',
            last_name='Manual',
            rut='14.444.444-2',
            rol=self.User.SUPERADMINISTRADOR,
            is_staff=False,
            is_superuser=False,
        )
        usuario.set_password('ClaveSegura123')

        with self.assertRaises(ValidationError):
            usuario.save()

    def test_modelo_impide_superuser_con_rol_administrador_web(self):
        """Evita mezclar privilegios de Django admin con roles web."""
        self.admin_user.is_staff = True
        self.admin_user.is_superuser = True

        with self.assertRaises(ValidationError):
            self.admin_user.save()

        self.admin_user.refresh_from_db()
        self.assertEqual(self.admin_user.rol, self.User.ADMINISTRADOR)
        self.assertFalse(self.admin_user.is_superuser)

    def test_admin_django_rechaza_staff_no_superusuario(self):
        """Reserva la marca staff y el panel admin para superusuarios."""
        self.admin_user.is_staff = True

        with self.assertRaises(ValidationError):
            self.admin_user.save(update_fields=['is_staff'])

        self.admin_user.refresh_from_db()
        self.client.force_login(self.admin_user)

        response = self.client.get(reverse('admin:index'))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('admin:login'), response['Location'])
        self.assertIn('next=', response['Location'])

    def test_admin_django_permite_superusuario(self):
        """Mantiene disponible el admin tradicional para superusuarios activos."""
        superusuario = self.User.objects.create_superuser(
            username='super_admin',
            email='super.admin@example.com',
            password='ClaveSegura123',
            first_name='Super',
            last_name='Admin',
            rut='98.765.432-5',
        )
        self.client.force_login(superusuario)

        response = self.client.get(reverse('admin:index'))

        self.assertEqual(response.status_code, 200)

    def test_administrador_web_no_modifica_superadministrador(self):
        """Impide administrar superusuarios de Django desde vistas web."""
        superusuario = self.User.objects.create_superuser(
            username='super_protegido',
            email='super.protegido@example.com',
            password='ClaveSegura123',
            first_name='Super',
            last_name='Protegido',
            rut='15.555.555-6',
        )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:editar_usuario', args=[superusuario.pk]),
            {
                'username': 'super_editado',
                'email': 'super.editado@example.com',
                'first_name': 'Super',
                'last_name': 'Editado',
                'rut': '15.555.555-6',
                'rol': self.User.ADMINISTRADOR,
            },
        )
        self.assertRedirects(response, reverse('usuarios:listado_usuarios'))
        superusuario.refresh_from_db()
        self.assertEqual(superusuario.username, 'super_protegido')
        self.assertEqual(superusuario.rol, self.User.SUPERADMINISTRADOR)

        response = self.client.post(
            reverse('usuarios:cambiar_estado_usuario', args=[superusuario.pk]),
        )
        self.assertRedirects(response, reverse('usuarios:listado_usuarios'))
        superusuario.refresh_from_db()
        self.assertTrue(superusuario.is_active)

        response = self.client.post(
            reverse('usuarios:eliminar_usuario', args=[superusuario.pk]),
        )
        self.assertRedirects(response, reverse('usuarios:listado_usuarios'))
        self.assertTrue(self.User.objects.filter(pk=superusuario.pk).exists())

    def test_edicion_socio_valida_confirmacion_de_correo(self):
        """Exige confirmacion cuando se edita el correo del socio."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:editar_socio', args=[self.socio_user.pk]),
            {
                'email': 'socio.admin@example.com',
                'email_confirmacion': 'otro.correo@example.com',
                'first_name': 'Socio',
                'last_name': 'Admin',
                'rut': '22.222.222-2',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'La confirmación del correo no coincide.')
        self.socio_user.refresh_from_db()
        self.assertEqual(self.socio_user.email, 'socio@example.com')
        self.assertEqual(self.socio_user.username, 'socio')

    def test_administrador_edita_password_de_usuario_con_hash(self):
        """Guarda con hash la contraseña cambiada por un administrador."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:editar_usuario', args=[self.encargado_user.pk]),
            {
                'email': 'encargado@example.com',
                'first_name': 'Encargado',
                'last_name': 'Registro',
                'rut': '44.444.444-4',
                'rol': self.User.ENCARGADO_REGISTRO,
                'is_active': 'on',
                'password1': 'NuevaClaveSegura123',
                'password2': 'NuevaClaveSegura123',
            },
        )
        self.assertRedirects(response, reverse('usuarios:listado_usuarios'))
        self.encargado_user.refresh_from_db()
        self.assertTrue(self.encargado_user.check_password('NuevaClaveSegura123'))
        self.assertNotEqual(self.encargado_user.password, 'NuevaClaveSegura123')

    def test_editar_usuario_sin_password_conserva_contraseña_actual(self):
        """Mantiene el hash actual si los campos de password quedan vacios."""
        password_original = self.encargado_user.password
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:editar_usuario', args=[self.encargado_user.pk]),
            {
                'email': 'encargado@example.com',
                'first_name': 'Encargado',
                'last_name': 'Registro',
                'rut': '44.444.444-4',
                'rol': self.User.ENCARGADO_REGISTRO,
                'is_active': 'on',
                'password1': '',
                'password2': '',
            },
        )
        self.assertRedirects(response, reverse('usuarios:listado_usuarios'))
        self.encargado_user.refresh_from_db()
        self.assertEqual(self.encargado_user.password, password_original)

    def test_usuario_cambia_su_propia_contraseña(self):
        """Permite que un usuario cambie su propia contraseña."""
        self.client.login(username='socio', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:cambiar_mi_password'),
            {
                'old_password': 'ClaveSegura123',
                'new_password1': 'OtraClaveSegura123',
                'new_password2': 'OtraClaveSegura123',
            },
        )
        self.assertRedirects(response, reverse('usuarios:mis_asistencias'))
        self.socio_user.refresh_from_db()
        self.assertTrue(self.socio_user.check_password('OtraClaveSegura123'))
        self.assertNotEqual(self.socio_user.password, 'OtraClaveSegura123')

    def test_administrador_no_puede_desactivarse_a_si_mismo(self):
        """Evita que el administrador desactive su propia cuenta."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:cambiar_estado_usuario', args=[self.admin_user.pk]),
        )
        self.assertRedirects(response, reverse('usuarios:listado_usuarios'))
        self.admin_user.refresh_from_db()
        self.assertTrue(self.admin_user.is_active)

    def test_administrador_cambia_estado_de_otro_usuario(self):
        """Permite al administrador activar o desactivar otros usuarios."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:cambiar_estado_usuario', args=[self.encargado_user.pk]),
        )
        self.assertRedirects(response, reverse('usuarios:listado_usuarios'))
        self.encargado_user.refresh_from_db()
        self.assertFalse(self.encargado_user.is_active)

    def test_administrador_elimina_usuario_interno(self):
        """Permite eliminar administradores o encargados distintos del actor."""
        self.client.login(username='admin', password='ClaveSegura123')
        encargado_pk = self.encargado_user.pk
        response = self.client.post(
            reverse('usuarios:eliminar_usuario', args=[encargado_pk]),
            follow=True,
        )

        self.assertRedirects(response, reverse('usuarios:listado_usuarios'))
        self.assertFalse(self.User.objects.filter(pk=encargado_pk).exists())
        self.assertContains(response, 'Usuario Encargado Registro eliminado correctamente.')

    def test_administrador_no_elimina_usuario_con_historial_operativo(self):
        """Bloquea eliminacion de usuarios internos referenciados por asistencia."""
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
            estado=Reunion.HISTORICA,
        )
        AsistenciaReunion.objects.create(
            reunion=reunion,
            socio=self.socio_user,
            estado=AsistenciaReunion.PRESENTE,
            origen=AsistenciaReunion.ORIGEN_RUT,
            registrada_por=self.encargado_user,
        )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:eliminar_usuario', args=[self.encargado_user.pk]),
            follow=True,
        )

        self.assertRedirects(response, reverse('usuarios:listado_usuarios'))
        self.assertTrue(self.User.objects.filter(pk=self.encargado_user.pk).exists())
        self.assertContains(
            response,
            'No se puede eliminar este usuario porque tiene historial operativo registrado.',
        )

    def test_administrador_no_puede_eliminarse_a_si_mismo(self):
        """Evita que un administrador elimine su propia cuenta."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:eliminar_usuario', args=[self.admin_user.pk]),
            follow=True,
        )

        self.assertRedirects(response, reverse('usuarios:listado_usuarios'))
        self.assertTrue(self.User.objects.filter(pk=self.admin_user.pk).exists())
        self.assertContains(response, 'No puedes eliminar tu propio usuario.')

    def test_eliminar_usuario_no_borra_socios(self):
        """Reserva la eliminacion de socios para su flujo especifico."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:eliminar_usuario', args=[self.socio_user.pk]),
            follow=True,
        )

        self.assertRedirects(response, reverse('usuarios:listado_usuarios'))
        self.assertTrue(self.User.objects.filter(pk=self.socio_user.pk).exists())
        self.assertContains(
            response,
            'Solo se pueden eliminar usuarios internos.',
        )

    def test_encargado_no_puede_eliminar_usuarios_internos(self):
        """Impide que un encargado use la eliminacion de usuarios internos."""
        self.client.login(username='encargado', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:eliminar_usuario', args=[self.admin_user.pk]),
        )

        self.assertRedirects(response, reverse('usuarios:dashboard'))
        self.assertTrue(self.User.objects.filter(pk=self.admin_user.pk).exists())

    def test_administrador_cambia_estado_de_socio_desde_listado_socios(self):
        """Redirige al listado de socios al activar o desactivar un socio."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:cambiar_estado_usuario', args=[self.socio_user.pk]),
        )
        self.assertRedirects(response, reverse('usuarios:listado_socios'))
        self.socio_user.refresh_from_db()
        self.assertFalse(self.socio_user.is_active)

    def test_administrador_elimina_socio_sin_asistencias_contabilizadas(self):
        """Permite eliminar socios que todavia no tienen historial operativo."""
        self.client.login(username='admin', password='ClaveSegura123')
        socio_pk = self.socio_user.pk
        response = self.client.post(
            reverse('usuarios:eliminar_socio', args=[socio_pk]),
            follow=True,
        )

        self.assertRedirects(response, reverse('usuarios:listado_socios'))
        self.assertFalse(self.User.objects.filter(pk=socio_pk).exists())
        self.assertContains(response, 'Socio Socio Prueba eliminado correctamente.')

    def test_administrador_no_elimina_socio_con_asistencias_contabilizadas(self):
        """Bloquea la eliminacion cuando el socio tiene historial operativo."""
        self.client.login(username='admin', password='ClaveSegura123')
        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.PRESENTE,
            date(2026, 5, 20),
        )

        response = self.client.post(
            reverse('usuarios:eliminar_socio', args=[self.socio_user.pk]),
            follow=True,
        )

        self.assertRedirects(response, reverse('usuarios:listado_socios'))
        self.assertTrue(self.User.objects.filter(pk=self.socio_user.pk).exists())
        self.assertContains(response, 'Solo se pueden eliminar socios sin asistencias contabilizadas.')

    def test_listado_socios_bloquea_boton_eliminar_con_asistencias(self):
        """Muestra eliminacion deshabilitada si el socio ya tiene asistencias."""
        self.client.login(username='admin', password='ClaveSegura123')
        self.registrar_asistencia_historica(
            self.socio_user,
            AsistenciaReunion.AUSENTE,
            date(2026, 5, 20),
        )

        response = self.client.get(reverse('usuarios:listado_socios'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, reverse('usuarios:eliminar_socio', args=[self.socio_user.pk]))
        self.assertContains(
            response,
            'Tiene asistencias contabilizadas; solo se puede desactivar.',
        )

    def test_no_se_eliminan_encargados_desde_flujo_de_socios(self):
        """Reserva a los encargados para activacion o desactivacion."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:eliminar_socio', args=[self.encargado_user.pk]),
        )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(self.User.objects.filter(pk=self.encargado_user.pk).exists())

    def test_encargado_no_puede_eliminar_socios(self):
        """Impide que encargados usen la eliminacion segura de socios."""
        self.client.login(username='encargado', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:eliminar_socio', args=[self.socio_user.pk]),
        )

        self.assertRedirects(response, reverse('usuarios:dashboard'))
        self.assertTrue(self.User.objects.filter(pk=self.socio_user.pk).exists())

    def test_usuario_inactivo_no_puede_iniciar_sesion(self):
        """Rechaza autenticacion de usuarios desactivados."""
        self.socio_user.is_active = False
        self.socio_user.save(update_fields=['is_active'])
        response = self.client.post(
            reverse('usuarios:login'),
            {'username': 'socio@example.com', 'password': 'ClaveSegura123'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_comando_crea_usuarios_demo_con_acceso_solo_para_roles_internos(self):
        """Verifica que el comando demo no deje password utilizable en socios."""
        output = StringIO()
        call_command('crear_usuarios_prueba', stdout=output)

        for username in ('admin_demo', 'encargado_demo'):
            usuario = self.User.objects.get(username=username)
            self.assertTrue(usuario.check_password(username))
            self.assertNotEqual(usuario.password, username)

        socio = self.User.objects.get(username='socio_demo')
        self.assertFalse(socio.has_usable_password())
        self.assertIn('socio.demo@example.com / sin contrasena de acceso', output.getvalue())

    def test_comando_carga_encargados_paginacion_sin_validacion(self):
        """Carga encargados por bulk sin ejecutar validaciones del modelo."""
        output = StringIO()

        with patch.object(self.User, 'full_clean', side_effect=AssertionError):
            call_command('cargar_encargados_paginacion', stdout=output)
            call_command('cargar_encargados_paginacion', stdout=output)

        encargados = self.User.objects.filter(
            username__startswith='encargado_paginacion_'
        )
        usuario = self.User.objects.get(username='encargado_paginacion_001')

        self.assertEqual(encargados.count(), 100)
        self.assertEqual(usuario.rol, self.User.ENCARGADO_REGISTRO)
        self.assertFalse(usuario.has_usable_password())
        self.assertIn('Encargados creados: 100; actualizados: 0', output.getvalue())
        self.assertIn('Encargados creados: 0; actualizados: 100', output.getvalue())

    @override_settings(DEBUG=True)
    def test_comando_resetea_asistencia_de_pruebas(self):
        """Borra reuniones, asistencias, justificaciones y notificaciones sin eliminar usuarios."""
        reunion = Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
        )
        ausencia = AsistenciaReunion.objects.create(
            reunion=reunion,
            socio=self.socio_user,
            estado=AsistenciaReunion.AUSENTE,
            origen=AsistenciaReunion.ORIGEN_AUTOMATICO,
            registrada_por=self.encargado_user,
        )
        DesbloqueoSocio.objects.create(
            socio=self.socio_user,
            asistencia=ausencia,
            motivo='Prueba local',
            desbloqueado_por=self.admin_user,
            inasistencias_al_desbloquear=1,
        )
        NotificacionBloqueoSocio.objects.create(
            socio=self.socio_user,
            enviada_por=self.admin_user,
            firma_bloqueo='bloqueo-prueba',
            email_destino=self.socio_user.email,
            total_inasistencias_efectivas=2,
        )
        output = StringIO()

        call_command('resetdata', '--confirmar=true', stdout=output)

        self.assertFalse(Reunion.objects.exists())
        self.assertFalse(AsistenciaReunion.objects.exists())
        self.assertFalse(DesbloqueoSocio.objects.exists())
        self.assertFalse(NotificacionBloqueoSocio.objects.exists())
        self.assertTrue(self.User.objects.filter(pk=self.socio_user.pk).exists())
        self.assertIn('Reset de asistencia completado', output.getvalue())
        self.assertIn('notificaciones eliminadas: 1', output.getvalue())

    @override_settings(DEBUG=True)
    def test_comando_reset_asistencia_exige_confirmacion(self):
        """Evita borrar datos operativos sin confirmacion explicita."""
        Reunion.objects.create(
            fecha=date(2026, 5, 20),
            hora=time(18, 30),
            locacion='Sede social',
            creador=self.admin_user,
        )

        with self.assertRaises(CommandError):
            call_command('resetdata')

        self.assertEqual(Reunion.objects.count(), 1)

    @override_settings(DEBUG=False)
    def test_comando_reset_asistencia_bloquea_produccion(self):
        """Impide ejecutar el reset cuando DEBUG esta desactivado."""
        with self.assertRaises(CommandError):
            call_command('resetdata', confirmar=True)
