from io import StringIO
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.staticfiles import finders
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from .admin import UsuarioAdmin
from .forms import UsuarioCreationForm, UsuarioUpdateForm
from .permisos import (
    GRUPO_ADMINISTRADOR,
    GRUPO_ENCARGADO_REGISTRO,
    GRUPO_SOCIO,
    PERM_ACCEDER_ASISTENCIA,
    PERM_ADMINISTRAR_PRIVILEGIOS,
    PERM_GESTIONAR_USUARIOS,
    ROLES_INTERNOS_GESTIONABLES,
)
from .views import (
    ROLES_FILTRABLES_USUARIOS,
    obtener_indicador_asistencia,
    obtener_resumen_estado_asistencia_socios,
    puede_acceder_asistencia,
    puede_gestionar_usuarios,
    puede_registrar_socios,
    puede_registrar_usuarios,
)


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class UsuariosModuloTests(TestCase):
    """Pruebas de autenticacion, roles, permisos y gestion de usuarios."""

    def setUp(self):
        """Crea usuarios base para validar reglas por rol."""
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
        self.assertContains(response, 'vendor/bootstrap/bootstrap.bundle.min.js')
        self.assertContains(response, 'vendor/sweetalert2/sweetalert2.all.min.js')
        self.assertContains(response, 'vendor/chart.js/chart.min.js')
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
        ]
        for ruta in rutas_estaticas:
            with self.subTest(ruta=ruta):
                self.assertIsNotNone(finders.find(ruta))

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
        self.assertNotContains(response, 'Gestionar usuarios')
        self.assertNotContains(response, 'Registrar usuario')
        self.assertNotContains(response, 'Gestionar socios')
        self.assertNotContains(response, 'Registrar socio')

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
        self.assertNotContains(response, 'Listado asistencia')

    def test_menu_lateral_admin_agrupa_usuarios_y_socios(self):
        """Agrupa acciones administrativas de usuarios y socios en el sidebar."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:dashboard'))
        self.assertContains(response, 'Listado usuarios')
        self.assertContains(response, 'Registrar usuario')
        self.assertContains(response, 'Listado socios')
        self.assertContains(response, 'Registrar socio')
        self.assertContains(response, 'Listado asistencia')
        self.assertNotContains(response, '<p class="sidebar-section-title">Asistencia</p>', html=True)

    def test_administrador_accede_a_asistencia_y_ve_solo_socios(self):
        """Permite al administrador ver el listado operativo de socios."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:listado_socios_asistencia'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Listado operativo de socios')
        self.assertContains(response, 'Reuniones')
        self.assertContains(response, 'Asistencias')
        self.assertContains(response, 'Ausencias')
        self.assertContains(response, 'Sin ausencias')
        self.assertContains(response, 'Gestionar estado')
        self.assertNotContains(response, reverse('usuarios:editar_socio', args=[self.socio_user.pk]))
        self.assertContains(response, 'socio@example.com')
        self.assertContains(response, '+56922222222')
        self.assertNotContains(response, 'admin@example.com')
        self.assertNotContains(response, 'encargado@example.com')

    def test_listado_asistencia_filtra_y_separa_nombre_apellido(self):
        """Aplica filtros operativos y muestra datos personales separados."""
        socio_filtrado = self.User.objects.create_user(
            username='ana.asistencia',
            email='ana.asistencia@example.com',
            password='ClaveSegura123',
            first_name='Ana',
            last_name='Asistencia',
            rut='77.777.777-7',
            rol=self.User.SOCIO,
        )
        self.User.objects.create_user(
            username='bruno.asistencia',
            email='bruno.asistencia@example.com',
            password='ClaveSegura123',
            first_name='Bruno',
            last_name='Asistencia',
            rut='88.888.888-8',
            rol=self.User.SOCIO,
        )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(
            reverse('usuarios:listado_socios_asistencia'),
            {
                'rut': '77.777.777-7',
                'nombre': 'Ana',
                'apellido': 'Asistencia',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ordenar RUT ascendente')
        self.assertContains(response, 'Ordenar Nombre ascendente')
        self.assertContains(response, 'Ordenar Apellido ascendente')
        self.assertContains(response, socio_filtrado.email)
        self.assertContains(response, '<td class="fw-semibold">77777777-7</td>', html=True)
        self.assertContains(response, '<td>Ana</td>', html=True)
        self.assertContains(response, '<td>Asistencia</td>', html=True)
        self.assertContains(response, 'value="77.777.777-7"')
        self.assertContains(response, 'value="Ana"')
        self.assertContains(response, 'value="Asistencia"')
        self.assertNotContains(response, 'bruno.asistencia@example.com')
        self.assertNotContains(response, 'admin@example.com')

    def test_listado_asistencia_filtra_por_indicador(self):
        """Permite filtrar socios por indicador de asistencia."""
        socio_riesgo = self.User.objects.create_user(
            username='riesgo.asistencia',
            email='riesgo.asistencia@example.com',
            password='ClaveSegura123',
            first_name='Riesgo',
            last_name='Asistencia',
            rut='88.111.111-1',
            rol=self.User.SOCIO,
        )
        socio_bloqueado = self.User.objects.create_user(
            username='bloqueado.asistencia',
            email='bloqueado.asistencia@example.com',
            password='ClaveSegura123',
            first_name='Bloqueado',
            last_name='Asistencia',
            rut='88.222.222-2',
            rol=self.User.SOCIO,
        )
        ausencias_por_pk = {
            self.socio_user.pk: 0,
            socio_riesgo.pk: 1,
            socio_bloqueado.pk: 2,
        }

        def resumen_mock(socio):
            total_ausencias = ausencias_por_pk[socio.pk]
            return {
                'total_reuniones': 2,
                'total_asistencias': 2 - total_ausencias,
                'total_ausencias': total_ausencias,
            }

        self.client.login(username='admin', password='ClaveSegura123')
        with patch('usuarios.views.obtener_resumen_asistencia_socio', resumen_mock):
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
        self.assertContains(response, socio_bloqueado.email)
        self.assertNotContains(response, socio_riesgo.email)
        self.assertNotContains(response, 'socio@example.com')

    def test_listado_asistencia_tiene_lista_responsiva_para_movil(self):
        """Replica el formato responsivo usado por los listados administrativos."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:listado_socios_asistencia'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'd-none d-md-block')
        self.assertContains(response, 'list-group shadow-sm border rounded overflow-hidden d-md-none')
        self.assertContains(response, '<dt class="col-4 text-muted fw-semibold">NOMBRE</dt>', html=True)
        self.assertContains(response, '<dt class="col-4 text-muted fw-semibold">APELLIDO</dt>', html=True)
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
                rut=f'91.000.{indice:03d}-{indice % 10}',
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
            rut='92.222.222-2',
            rol=self.User.SOCIO,
        )
        self.User.objects.create_user(
            username='zulu.asistencia',
            email='zulu.asistencia@example.com',
            password='ClaveSegura123',
            first_name='Zulu',
            last_name='Orden',
            rut='93.333.333-3',
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

        ausencias_por_pk = {
            self.socio_user.pk: 0,
            socio_riesgo.pk: 1,
            socio_bloqueado.pk: 2,
        }

        def resumen_mock(socio):
            return {
                'total_reuniones': 2,
                'total_asistencias': 2 - ausencias_por_pk[socio.pk],
                'total_ausencias': ausencias_por_pk[socio.pk],
            }

        with patch('usuarios.views.obtener_resumen_asistencia_socio', resumen_mock):
            resumen = obtener_resumen_estado_asistencia_socios()

        totales = {item['label']: item['total'] for item in resumen['items']}
        self.assertEqual(resumen['total'], 3)
        self.assertEqual(totales['Socios totales'], 3)
        self.assertEqual(totales['Sin falta'], 1)
        self.assertEqual(totales['En riesgo'], 1)
        self.assertEqual(totales['Bloqueados por inasistencia'], 1)

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
            rut='12.000.000-1',
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
                rut=f'70.000.{indice:03d}-{indice % 10}',
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
        self.assertContains(response, '<td>Ana</td>', html=True)
        self.assertContains(response, '<td>Zapata</td>', html=True)
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
                rut=f'71.000.{indice:03d}-{indice % 10}',
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
            rut='72.222.222-2',
            rol=self.User.ENCARGADO_REGISTRO,
        )
        self.User.objects.create_user(
            username='zulu.orden',
            email='zulu.orden@example.com',
            password='ClaveSegura123',
            first_name='Zulu',
            last_name='Orden',
            rut='73.333.333-3',
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
                rut=f'74.000.{indice:03d}-{indice % 10}',
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
        self.assertContains(response, 'socio@example.com')
        self.assertContains(response, '+56922222222')
        self.assertContains(response, reverse('usuarios:editar_socio', args=[self.socio_user.pk]))
        self.assertContains(response, 'data-confirm-title="Desactivar socio"')
        self.assertContains(response, reverse('usuarios:eliminar_socio', args=[self.socio_user.pk]))
        self.assertContains(response, 'data-confirm-title="Eliminar socio"')
        self.assertNotContains(response, 'admin@example.com')
        self.assertNotContains(response, 'encargado@example.com')

    def test_listado_socios_filtra_y_separa_nombre_apellido(self):
        """Aplica filtros administrativos y muestra nombre y apellido separados."""
        socio_filtrado = self.User.objects.create_user(
            username='ana.socia',
            email='ana.socia@example.com',
            password='ClaveSegura123',
            first_name='Ana',
            last_name='Zapata',
            rut='77.777.777-7',
            rol=self.User.SOCIO,
        )
        self.User.objects.create_user(
            username='bruno.socio',
            email='bruno.socio@example.com',
            password='ClaveSegura123',
            first_name='Bruno',
            last_name='Zapata',
            rut='88.888.888-8',
            rol=self.User.SOCIO,
        )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(
            reverse('usuarios:listado_socios'),
            {
                'rut': '77.777.777-7',
                'nombre': 'Ana',
                'apellido': 'Zapata',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ordenar RUT ascendente')
        self.assertContains(response, 'Ordenar Nombre ascendente')
        self.assertContains(response, 'Ordenar Apellido ascendente')
        self.assertContains(response, socio_filtrado.email)
        self.assertContains(response, '<td class="fw-semibold">77777777-7</td>', html=True)
        self.assertContains(response, '<td>Ana</td>', html=True)
        self.assertContains(response, '<td>Zapata</td>', html=True)
        self.assertContains(response, 'value="77.777.777-7"')
        self.assertContains(response, 'value="Ana"')
        self.assertContains(response, 'value="Zapata"')
        self.assertNotContains(response, 'bruno.socio@example.com')
        self.assertNotContains(response, 'admin@example.com')

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
        self.assertContains(response, socio_inactivo.email)
        self.assertNotContains(response, 'socio@example.com')

    def test_listado_socios_tiene_lista_responsiva_para_movil(self):
        """Replica el formato responsivo del listado administrativo de usuarios."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:listado_socios'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'd-none d-md-block')
        self.assertContains(response, 'list-group shadow-sm border rounded overflow-hidden d-md-none')
        self.assertContains(response, '<dt class="col-4 text-muted fw-semibold">NOMBRE</dt>', html=True)
        self.assertContains(response, '<dt class="col-4 text-muted fw-semibold">APELLIDO</dt>', html=True)
        self.assertContains(response, '<dt class="col-4 text-muted fw-semibold">EMAIL</dt>', html=True)
        self.assertContains(response, '<dt class="col-4 text-muted fw-semibold">TELÉFONO</dt>', html=True)

    def test_listado_socios_paginacion_conserva_filtros(self):
        """Mantiene los filtros activos al navegar paginas de socios."""
        for indice in range(51):
            self.User.objects.create_user(
                username=f'socio_filtro_{indice:02d}',
                email=f'socio_filtro_{indice:02d}@example.com',
                password='ClaveSegura123',
                first_name='FiltroSocio',
                last_name=f'Paginacion {indice:02d}',
                rut=f'81.000.{indice:03d}-{indice % 10}',
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
            rut='82.222.222-2',
            rol=self.User.SOCIO,
        )
        self.User.objects.create_user(
            username='zulu.socio',
            email='zulu.socio@example.com',
            password='ClaveSegura123',
            first_name='Zulu',
            last_name='Orden',
            rut='83.333.333-3',
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
                rut=f'84.000.{indice:03d}-{indice % 10}',
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
        self.assertContains(response, 'socio@example.com')
        self.assertNotContains(response, 'Registrar socio')
        self.assertNotContains(response, 'Editar')
        self.assertContains(response, 'Gestionar estado')
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
        self.assertContains(response, 'Operación completada')
        self.assertContains(response, "confirmButtonText: 'Aceptar'")
        self.assertNotContains(response, 'toast: true')

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

    def test_registro_socio_no_muestra_usuario_ni_password_y_pide_confirmacion(self):
        """Renderiza el formulario de socio sin credenciales tradicionales."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:registro_socio'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'email_confirmacion')
        self.assertContains(response, 'name="telefono_movil"')
        self.assertContains(response, 'value="+56"')
        self.assertNotContains(response, 'name="username"')
        self.assertNotContains(response, 'name="password1"')
        self.assertNotContains(response, 'name="password2"')

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
                'rut': '76.666.666-6',
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
                'rut': '66.666.666-6',
                'telefono_movil': '+56966666666',
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
                'rut': '66.666.666-6',
                'telefono_movil': '+56966666666',
                'is_active': 'on',
            },
        )
        self.assertRedirects(response, reverse('usuarios:listado_socios'))
        usuario = self.User.objects.get(email='socio.nuevo@example.com')
        self.assertEqual(usuario.rol, self.User.SOCIO)
        self.assertEqual(usuario.username, 'socio.nuevo@example.com')
        self.assertEqual(usuario.telefono_movil, '+56966666666')
        self.assertFalse(usuario.has_usable_password())

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
                'rut': '99.999.999-9',
                'telefono_movil': '+56977777777',
            },
        )
        self.assertRedirects(response, reverse('usuarios:listado_socios'))
        self.socio_user.refresh_from_db()
        self.assertEqual(self.socio_user.email, 'socio.admin@example.com')
        self.assertEqual(self.socio_user.username, 'socio')
        self.assertEqual(self.socio_user.rut, '22222222-2')
        self.assertEqual(self.socio_user.telefono_movil, '+56977777777')
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
            rut='14.444.444-4',
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
            rut='98.765.432-1',
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
            rut='15.555.555-5',
        )

        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:editar_usuario', args=[superusuario.pk]),
            {
                'username': 'super_editado',
                'email': 'super.editado@example.com',
                'first_name': 'Super',
                'last_name': 'Editado',
                'rut': '15.555.555-5',
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
        resumen = {
            'total_reuniones': 1,
            'total_asistencias': 1,
            'total_ausencias': 0,
        }

        with patch('usuarios.views.obtener_resumen_asistencia_socio', return_value=resumen):
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
        resumen = {
            'total_reuniones': 1,
            'total_asistencias': 0,
            'total_ausencias': 1,
        }

        with patch('usuarios.views.obtener_resumen_asistencia_socio', return_value=resumen):
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

    def test_comando_crea_usuarios_demo_con_username_como_password(self):
        """Verifica que el comando demo cree passwords hasheados por username."""
        output = StringIO()
        call_command('crear_usuarios_prueba', stdout=output)

        for username in ('admin_demo', 'encargado_demo', 'socio_demo'):
            usuario = self.User.objects.get(username=username)
            self.assertTrue(usuario.check_password(username))
            self.assertNotEqual(usuario.password, username)

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
