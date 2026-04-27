from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse


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
            rol=self.User.ADMINISTRADOR,
        )
        self.socio_user = self.User.objects.create_user(
            username='socio',
            email='socio@example.com',
            password='ClaveSegura123',
            first_name='Socio',
            last_name='Prueba',
            rut='22.222.222-2',
            rol=self.User.SOCIO,
        )
        self.encargado_user = self.User.objects.create_user(
            username='encargado',
            email='encargado@example.com',
            password='ClaveSegura123',
            first_name='Encargado',
            last_name='Registro',
            rut='44.444.444-4',
            rol=self.User.ENCARGADO_REGISTRO,
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
                'rut': '33.333.333-3',
                'rol': self.User.ENCARGADO_REGISTRO,
                'is_active': 'on',
                'password1': 'ClaveSegura123',
                'password2': 'ClaveSegura123',
            },
        )
        self.assertRedirects(response, reverse('usuarios:listado_usuarios'))
        self.assertTrue(self.User.objects.filter(username='encargado_nuevo').exists())

    def test_encargado_accede_a_listado_sin_administradores(self):
        """Oculta cuentas administradoras al encargado de registro."""
        self.client.login(username='encargado', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:listado_usuarios'))
        self.assertContains(response, 'socio@example.com')
        self.assertNotContains(response, 'admin@example.com')

    def test_encargado_no_crea_administrador(self):
        """Impide que el encargado cree usuarios administradores."""
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
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.User.objects.filter(username='admin_no_permitido').exists())

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
        self.assertRedirects(response, reverse('usuarios:listado_usuarios'))
        self.admin_user.refresh_from_db()
        self.assertEqual(self.admin_user.rol, self.User.ADMINISTRADOR)

    def test_encargado_no_desactiva_administrador(self):
        """Impide que el encargado desactive cuentas administradoras."""
        self.client.login(username='encargado', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:cambiar_estado_usuario', args=[self.admin_user.pk]),
        )
        self.assertRedirects(response, reverse('usuarios:listado_usuarios'))
        self.admin_user.refresh_from_db()
        self.assertTrue(self.admin_user.is_active)

    def test_administrador_edita_usuario_y_normaliza_datos(self):
        """Normaliza email, RUT y rol al editar un usuario."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:editar_usuario', args=[self.socio_user.pk]),
            {
                'username': 'socio',
                'email': 'SOCIO.ACTUALIZADO@EXAMPLE.COM',
                'first_name': 'Socio',
                'last_name': 'Actualizado',
                'rut': '22.222.222-2',
                'rol': self.User.ENCARGADO_REGISTRO,
                'is_active': 'on',
            },
        )
        self.assertRedirects(response, reverse('usuarios:listado_usuarios'))
        self.socio_user.refresh_from_db()
        self.assertEqual(self.socio_user.email, 'socio.actualizado@example.com')
        self.assertEqual(self.socio_user.rut, '22222222-2')
        self.assertEqual(self.socio_user.rol, self.User.ENCARGADO_REGISTRO)

    def test_administrador_edita_password_de_usuario_con_hash(self):
        """Guarda con hash la contrasena cambiada por un administrador."""
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:editar_usuario', args=[self.socio_user.pk]),
            {
                'username': 'socio',
                'email': 'socio@example.com',
                'first_name': 'Socio',
                'last_name': 'Prueba',
                'rut': '22.222.222-2',
                'rol': self.User.SOCIO,
                'is_active': 'on',
                'password1': 'NuevaClaveSegura123',
                'password2': 'NuevaClaveSegura123',
            },
        )
        self.assertRedirects(response, reverse('usuarios:listado_usuarios'))
        self.socio_user.refresh_from_db()
        self.assertTrue(self.socio_user.check_password('NuevaClaveSegura123'))
        self.assertNotEqual(self.socio_user.password, 'NuevaClaveSegura123')

    def test_editar_usuario_sin_password_conserva_contrasena_actual(self):
        """Mantiene el hash actual si los campos de password quedan vacios."""
        password_original = self.socio_user.password
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:editar_usuario', args=[self.socio_user.pk]),
            {
                'username': 'socio',
                'email': 'socio@example.com',
                'first_name': 'Socio',
                'last_name': 'Prueba',
                'rut': '22.222.222-2',
                'rol': self.User.SOCIO,
                'is_active': 'on',
                'password1': '',
                'password2': '',
            },
        )
        self.assertRedirects(response, reverse('usuarios:listado_usuarios'))
        self.socio_user.refresh_from_db()
        self.assertEqual(self.socio_user.password, password_original)

    def test_usuario_cambia_su_propia_contrasena(self):
        """Permite que un usuario cambie su propia contrasena."""
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
            reverse('usuarios:cambiar_estado_usuario', args=[self.socio_user.pk]),
        )
        self.assertRedirects(response, reverse('usuarios:listado_usuarios'))
        self.socio_user.refresh_from_db()
        self.assertFalse(self.socio_user.is_active)

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
