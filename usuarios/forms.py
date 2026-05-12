import re

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Column, Layout, Row, Submit
from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, UserCreationForm
from django.contrib.auth.password_validation import validate_password

from .models import (
    TELEFONO_MOVIL_MENSAJE_CHILE,
    TELEFONO_MOVIL_PREFIJO_CHILE,
    TELEFONO_MOVIL_REGEX_CHILE,
    Usuario,
    normalizar_rut,
    normalizar_telefono_movil,
)
from .permisos import (
    PERM_ADMINISTRAR_PRIVILEGIOS,
    ROLES_INTERNOS_GESTIONABLES,
    ROL_SOCIO,
    filtrar_choices_por_roles,
    rol_es_socio,
    rol_es_superadministrador,
    usuario_tiene_permiso,
)


def marcar_campo_rut(field):
    """Agrega atributos usados por el formateo visual de RUT en cliente."""
    field.widget.attrs.update(
        {
            'data-rut-format': 'true',
            'autocomplete': 'off',
            'inputmode': 'text',
        }
    )


def configurar_campo_telefono_movil(field, valor_inicial=None):
    """Prepara el campo de teléfono para capturar móviles chilenos."""
    field.initial = valor_inicial or TELEFONO_MOVIL_PREFIJO_CHILE
    field.help_text = 'Debe comenzar con +56 y continuar con 9 dígitos.'
    field.widget.attrs.update(
        {
            'autocomplete': 'tel',
            'data-phone-prefix': TELEFONO_MOVIL_PREFIJO_CHILE,
            'inputmode': 'tel',
            'maxlength': '12',
            'pattern': r'\+56[0-9]{9}',
            'placeholder': '+56912345678',
            'title': TELEFONO_MOVIL_MENSAJE_CHILE,
        }
    )


class TelefonoMovilFormMixin:
    """Normaliza el teléfono móvil chileno usado por formularios de usuario."""

    def configurar_telefono_movil(self):
        """Deja el prefijo +56 listo cuando no hay teléfono guardado."""
        telefono_guardado = ''
        if getattr(self, 'instance', None) and self.instance.pk:
            telefono_guardado = normalizar_telefono_movil(self.instance.telefono_movil)
        valor_inicial = telefono_guardado or TELEFONO_MOVIL_PREFIJO_CHILE
        configurar_campo_telefono_movil(self.fields['telefono_movil'], valor_inicial)
        self.initial['telefono_movil'] = valor_inicial

    def clean_telefono_movil(self):
        """Valida que el teléfono use +56 y exactamente 9 dígitos posteriores."""
        telefono = normalizar_telefono_movil(self.cleaned_data.get('telefono_movil'))
        if not telefono:
            return ''
        if not re.fullmatch(TELEFONO_MOVIL_REGEX_CHILE, telefono):
            raise forms.ValidationError(TELEFONO_MOVIL_MENSAJE_CHILE)
        return telefono


class LoginForm(AuthenticationForm):
    """Formulario de acceso que acepta username o correo electrónico."""

    username = forms.CharField(
        label='Usuario o correo electrónico',
        widget=forms.TextInput(attrs={'autofocus': True, 'autocomplete': 'username'}),
    )

    def __init__(self, *args, **kwargs):
        """Configura crispy forms para renderizar el formulario de login."""
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            'username',
            'password',
            Submit('submit', 'Ingresar', css_class='btn btn-primary w-100'),
        )


class UsuarioCreationForm(TelefonoMovilFormMixin, UserCreationForm):
    """Formulario de alta de usuarios con control de roles según actor."""

    class Meta:
        """Campos permitidos al crear usuarios desde el módulo propio."""

        model = Usuario
        fields = (
            'username',
            'first_name',
            'last_name',
            'rut',
            'email',
            'telefono_movil',
            'rol',
            'is_active',
        )
        labels = {
            'username': 'Usuario',
            'first_name': 'Nombre',
            'last_name': 'Apellido',
            'email': 'Correo electrónico',
            'telefono_movil': 'Teléfono móvil',
            'is_active': 'Usuario activo',
        }

    def __init__(self, *args, **kwargs):
        """Recibe el usuario actor y adapta layout y roles disponibles."""
        self.actor = kwargs.pop('actor', None)
        super().__init__(*args, **kwargs)
        self.fields['is_active'].initial = True
        marcar_campo_rut(self.fields['rut'])
        self.configurar_telefono_movil()
        self._limitar_roles_por_actor()
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Row(
                Column('username', css_class='col-md-6'),
                Column('email', css_class='col-md-6'),
            ),
            Row(
                Column('first_name', css_class='col-md-6'),
                Column('last_name', css_class='col-md-6'),
            ),
            Row(
                Column('rut', css_class='col-md-6'),
                Column('telefono_movil', css_class='col-md-6'),
            ),
            Row(
                Column('rol', css_class='col-md-6'),
            ),
            Row(
                Column('password1', css_class='col-md-6'),
                Column('password2', css_class='col-md-6'),
            ),
            'is_active',
            Submit('submit', 'Guardar usuario', css_class='btn btn-primary'),
        )

    def clean_email(self):
        """Valida que el correo sea único sin distinguir mayúsculas."""
        email = self.cleaned_data['email'].strip().lower()
        if Usuario.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('Ya existe un usuario con este correo.')
        return email

    def clean_rut(self):
        """Normaliza y valida unicidad del RUT ingresado."""
        rut = normalizar_rut(self.cleaned_data['rut'])
        if Usuario.objects.filter(rut__iexact=rut).exists():
            raise forms.ValidationError('Ya existe un usuario con este RUT.')
        return rut

    def clean_rol(self):
        """Impide crear socios desde el formulario de usuarios internos."""
        rol = self.cleaned_data['rol']
        if not self._actor_es_administrador():
            raise forms.ValidationError('No tienes permisos para registrar usuarios internos.')
        if rol_es_socio(rol):
            raise forms.ValidationError('Usa el formulario de registro de socios.')
        if rol_es_superadministrador(rol):
            raise forms.ValidationError('El superadministrador solo se administra desde Django admin.')
        return rol

    def _actor_es_administrador(self):
        """Indica si el actor puede administrar privilegios de alto nivel."""
        return usuario_tiene_permiso(self.actor, PERM_ADMINISTRAR_PRIVILEGIOS)

    def _limitar_roles_por_actor(self):
        """Limita el alta interna a roles administrativos y operativos."""
        self.fields['rol'].choices = filtrar_choices_por_roles(
            self.fields['rol'].choices,
            ROLES_INTERNOS_GESTIONABLES,
        )


class SocioCreationForm(TelefonoMovilFormMixin, forms.ModelForm):
    """Formulario de alta de socios sin credenciales de acceso tradicional."""

    email_confirmacion = forms.EmailField(label='Confirmar correo electrónico')

    class Meta:
        """Campos requeridos para crear una cuenta de socio."""

        model = Usuario
        fields = (
            'first_name',
            'last_name',
            'rut',
            'email',
            'telefono_movil',
            'is_active',
        )
        labels = {
            'first_name': 'Nombre',
            'last_name': 'Apellido',
            'email': 'Correo electrónico',
            'telefono_movil': 'Teléfono móvil',
            'is_active': 'Socio activo',
        }

    def __init__(self, *args, **kwargs):
        """Configura crispy forms para el registro operativo de socios."""
        super().__init__(*args, **kwargs)
        self.fields['is_active'].initial = True
        marcar_campo_rut(self.fields['rut'])
        self.configurar_telefono_movil()
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Row(
                Column('first_name', css_class='col-md-6'),
                Column('last_name', css_class='col-md-6'),
            ),
            Row(
                Column('rut', css_class='col-md-6'),
                Column('telefono_movil', css_class='col-md-6'),
            ),
            Row(
                Column('email', css_class='col-md-6'),
                Column('email_confirmacion', css_class='col-md-6'),
            ),
            'is_active',
            Submit('submit', 'Guardar socio', css_class='btn btn-primary'),
        )

    def clean_email(self):
        """Valida que el correo sea único sin distinguir mayúsculas."""
        email = self.cleaned_data['email'].strip().lower()
        if Usuario.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('Ya existe un usuario con este correo.')
        if Usuario.objects.filter(username__iexact=email).exists():
            raise forms.ValidationError('Ya existe un usuario técnico con este correo.')
        return email

    def clean_rut(self):
        """Normaliza y valida unicidad del RUT ingresado."""
        rut = normalizar_rut(self.cleaned_data['rut'])
        if Usuario.objects.filter(rut__iexact=rut).exists():
            raise forms.ValidationError('Ya existe un usuario con este RUT.')
        return rut

    def clean(self):
        """Verifica que el correo ingresado coincida con su confirmación."""
        cleaned_data = super().clean()
        email = (cleaned_data.get('email') or '').strip().lower()
        email_confirmacion = (cleaned_data.get('email_confirmacion') or '').strip().lower()
        if email and email_confirmacion and email != email_confirmacion:
            self.add_error('email_confirmacion', 'La confirmación del correo no coincide.')
        return cleaned_data

    def save(self, commit=True):
        """Crea un socio sin password utilizable y con username interno."""
        socio = super().save(commit=False)
        socio.rol = Usuario.SOCIO
        socio.username = socio.email
        socio.set_unusable_password()
        if commit:
            socio.save()
            self.save_m2m()
        return socio


class SocioUpdateForm(TelefonoMovilFormMixin, forms.ModelForm):
    """Formulario específico para editar socios sin exponer rol ni password."""

    email_confirmacion = forms.EmailField(label='Confirmar correo electrónico')

    class Meta:
        """Campos editables para mantener datos operativos del socio."""

        model = Usuario
        fields = (
            'first_name',
            'last_name',
            'rut',
            'email',
            'telefono_movil',
        )
        labels = {
            'first_name': 'Nombre',
            'last_name': 'Apellido',
            'email': 'Correo electrónico',
            'telefono_movil': 'Teléfono móvil',
        }

    def __init__(self, *args, **kwargs):
        """Construye layout de edición sin permitir cambiar el RUT."""
        super().__init__(*args, **kwargs)
        self.fields['rut'].disabled = True
        marcar_campo_rut(self.fields['rut'])
        self.configurar_telefono_movil()
        self.fields['rut'].help_text = 'El RUT no puede modificarse una vez creado.'
        if self.instance.pk:
            self.initial['rut'] = normalizar_rut(self.instance.rut)
            self.initial['email_confirmacion'] = self.instance.email
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Row(
                Column('first_name', css_class='col-md-6'),
                Column('last_name', css_class='col-md-6'),
            ),
            Row(
                Column('rut', css_class='col-md-6'),
                Column('telefono_movil', css_class='col-md-6'),
            ),
            Row(
                Column('email', css_class='col-md-6'),
                Column('email_confirmacion', css_class='col-md-6'),
            ),
            Submit('submit', 'Actualizar socio', css_class='btn btn-primary'),
        )

    def clean_email(self):
        """Valida unicidad de correo y username técnico excluyendo al socio."""
        email = self.cleaned_data['email'].strip().lower()
        email_qs = Usuario.objects.filter(email__iexact=email)
        username_qs = Usuario.objects.filter(username__iexact=email)
        if self.instance.pk:
            email_qs = email_qs.exclude(pk=self.instance.pk)
            username_qs = username_qs.exclude(pk=self.instance.pk)
        if email_qs.exists():
            raise forms.ValidationError('Ya existe un usuario con este correo.')
        if username_qs.exists():
            raise forms.ValidationError('Ya existe un usuario técnico con este correo.')
        return email

    def clean(self):
        """Verifica que el correo editado coincida con su confirmación."""
        cleaned_data = super().clean()
        email = (cleaned_data.get('email') or '').strip().lower()
        email_confirmacion = (cleaned_data.get('email_confirmacion') or '').strip().lower()
        if email and email_confirmacion and email != email_confirmacion:
            self.add_error('email_confirmacion', 'La confirmación del correo no coincide.')
        return cleaned_data

    def clean_rut(self):
        """Mantiene el RUT original aunque el POST intente modificarlo."""
        if self.instance.pk:
            return normalizar_rut(self.instance.rut)
        return normalizar_rut(self.cleaned_data['rut'])

    def save(self, commit=True):
        """Actualiza el socio conservando siempre su rol y username."""
        socio = super().save(commit=False)
        socio.rol = Usuario.SOCIO
        if commit:
            socio.save()
            self.save_m2m()
        return socio


class UsuarioUpdateForm(TelefonoMovilFormMixin, forms.ModelForm):
    """Formulario de edición de usuario con cambio opcional de password."""

    password1 = forms.CharField(
        label='Nueva contraseña',
        required=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
        help_text='Dejar en blanco para conservar la contraseña actual.',
    )
    password2 = forms.CharField(
        label='Confirmar nueva contraseña',
        required=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )

    class Meta:
        """Campos editables desde la pantalla de administración de usuarios."""

        model = Usuario
        fields = (
            'first_name',
            'last_name',
            'rut',
            'email',
            'telefono_movil',
            'rol',
        )
        labels = {
            'first_name': 'Nombre',
            'last_name': 'Apellido',
            'email': 'Correo electrónico',
            'telefono_movil': 'Teléfono móvil',
        }

    def __init__(self, *args, **kwargs):
        """Recibe el usuario actor y construye el layout de edición."""
        self.actor = kwargs.pop('actor', None)
        super().__init__(*args, **kwargs)
        self.fields['rut'].disabled = True
        marcar_campo_rut(self.fields['rut'])
        self.configurar_telefono_movil()
        self.fields['rut'].help_text = 'El RUT no puede modificarse una vez creado.'
        if self.instance.pk:
            self.initial['rut'] = normalizar_rut(self.instance.rut)
        self._limitar_roles_por_actor()
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Row(
                Column('first_name', css_class='col-md-6'),
                Column('last_name', css_class='col-md-6'),
            ),
            Row(
                Column('rut', css_class='col-md-6'),
                Column('telefono_movil', css_class='col-md-6'),
            ),
            Row(
                Column('email', css_class='col-md-6'),
                Column('rol', css_class='col-md-6'),
            ),
            Row(
                Column('password1', css_class='col-md-6'),
                Column('password2', css_class='col-md-6'),
            ),
            Submit('submit', 'Actualizar usuario', css_class='btn btn-primary'),
        )

    def clean_email(self):
        """Valida unicidad del correo excluyendo el usuario editado."""
        email = self.cleaned_data['email'].strip().lower()
        qs = Usuario.objects.filter(email__iexact=email)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('Ya existe un usuario con este correo.')
        return email

    def clean_rut(self):
        """Mantiene el RUT original aunque el POST intente modificarlo."""
        if self.instance.pk:
            return normalizar_rut(self.instance.rut)

        rut = normalizar_rut(self.cleaned_data['rut'])
        qs = Usuario.objects.filter(rut__iexact=rut)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('Ya existe un usuario con este RUT.')
        return rut

    def clean(self):
        """Valida coincidencia y seguridad del password cuando se informa."""
        cleaned_data = super().clean()
        if self.instance.pk and self.add_prefix('username') in self.data:
            raise forms.ValidationError('El nombre de usuario no puede modificarse.')

        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')

        if password1 or password2:
            if password1 != password2:
                self.add_error('password2', 'Las contraseñas no coinciden.')
            elif password1:
                validate_password(password1, self.instance)

        return cleaned_data

    def clean_rol(self):
        """Impide que actores no administradores asignen roles internos."""
        rol = self.cleaned_data['rol']
        if rol_es_socio(rol):
            raise forms.ValidationError('Usa el formulario de registro de socios.')
        if rol_es_superadministrador(rol):
            raise forms.ValidationError('El superadministrador solo se administra desde Django admin.')
        if not self._actor_es_administrador() and not rol_es_socio(rol):
            raise forms.ValidationError('Solo puedes asignar rol socio.')
        return rol

    def save(self, commit=True):
        """Guarda el usuario y aplica hashing si se cambio la contraseña."""
        usuario = super().save(commit=False)
        password = self.cleaned_data.get('password1')
        if password:
            usuario.set_password(password)
        if commit:
            usuario.save()
            self.save_m2m()
        return usuario

    def _actor_es_administrador(self):
        """Indica si el actor puede editar privilegios administrativos."""
        return usuario_tiene_permiso(self.actor, PERM_ADMINISTRAR_PRIVILEGIOS)

    def _limitar_roles_por_actor(self):
        """Limita a rol socio para actores sin privilegios."""
        if self._actor_es_administrador():
            roles_permitidos = ROLES_INTERNOS_GESTIONABLES
        else:
            roles_permitidos = (ROL_SOCIO,)
        self.fields['rol'].choices = filtrar_choices_por_roles(
            self.fields['rol'].choices,
            roles_permitidos,
        )


class CambioPasswordForm(PasswordChangeForm):
    """Formulario para que cada usuario cambie su propia contraseña."""

    old_password = forms.CharField(
        label='Contraseña actual',
        widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}),
    )
    new_password1 = forms.CharField(
        label='Nueva contraseña',
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )
    new_password2 = forms.CharField(
        label='Confirmar nueva contraseña',
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )

    def __init__(self, *args, **kwargs):
        """Configura crispy forms para el flujo de cambio de contraseña."""
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            'old_password',
            Row(
                Column('new_password1', css_class='col-md-6'),
                Column('new_password2', css_class='col-md-6'),
            ),
            Submit('submit', 'Actualizar contraseña', css_class='btn btn-primary'),
        )
