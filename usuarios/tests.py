from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class UsuariosModuloTests(TestCase):
    def setUp(self):
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

    def test_login_permite_correo_electronico(self):
        response = self.client.post(
            reverse('usuarios:login'),
            {'username': 'admin@example.com', 'password': 'ClaveSegura123'},
        )
        self.assertRedirects(response, reverse('usuarios:dashboard'))

    def test_socio_no_accede_a_gestion_de_usuarios(self):
        self.client.login(username='socio', password='ClaveSegura123')
        response = self.client.get(reverse('usuarios:listado_usuarios'))
        self.assertRedirects(response, reverse('usuarios:dashboard'))

    def test_administrador_crea_usuario(self):
        self.client.login(username='admin', password='ClaveSegura123')
        response = self.client.post(
            reverse('usuarios:registro_usuario'),
            {
                'username': 'encargado',
                'email': 'encargado@example.com',
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
        self.assertTrue(self.User.objects.filter(username='encargado').exists())
