from crispy_forms.helper import FormHelper
from crispy_forms.layout import Column, Layout, Row, Submit
from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, UserCreationForm
from django.contrib.auth.password_validation import validate_password

from .models import Usuario, normalizar_rut


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label='Usuario o correo electronico',
        widget=forms.TextInput(attrs={'autofocus': True, 'autocomplete': 'username'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            'username',
            'password',
            Submit('submit', 'Ingresar', css_class='btn btn-primary w-100'),
        )


class UsuarioCreationForm(UserCreationForm):
    class Meta:
        model = Usuario
        fields = (
            'username',
            'first_name',
            'last_name',
            'rut',
            'email',
            'rol',
            'is_active',
        )
        labels = {
            'username': 'Usuario',
            'first_name': 'Nombre',
            'last_name': 'Apellido',
            'email': 'Correo electronico',
            'is_active': 'Usuario activo',
        }

    def __init__(self, *args, **kwargs):
        self.actor = kwargs.pop('actor', None)
        super().__init__(*args, **kwargs)
        self.fields['is_active'].initial = True
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
        email = self.cleaned_data['email'].strip().lower()
        if Usuario.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('Ya existe un usuario con este correo.')
        return email

    def clean_rut(self):
        rut = normalizar_rut(self.cleaned_data['rut'])
        if Usuario.objects.filter(rut__iexact=rut).exists():
            raise forms.ValidationError('Ya existe un usuario con este RUT.')
        return rut

    def clean_rol(self):
        rol = self.cleaned_data['rol']
        if rol == Usuario.ADMINISTRADOR and not self._actor_es_administrador():
            raise forms.ValidationError('No tienes permisos para asignar rol administrador.')
        return rol

    def _actor_es_administrador(self):
        return bool(
            self.actor
            and self.actor.is_authenticated
            and (
                self.actor.is_superuser
                or getattr(self.actor, 'rol', None) == Usuario.ADMINISTRADOR
            )
        )

    def _limitar_roles_por_actor(self):
        if not self._actor_es_administrador():
            self.fields['rol'].choices = [
                choice
                for choice in self.fields['rol'].choices
                if choice[0] != Usuario.ADMINISTRADOR
            ]


class UsuarioUpdateForm(forms.ModelForm):
    password1 = forms.CharField(
        label='Nueva contrasena',
        required=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
        help_text='Dejar en blanco para conservar la contrasena actual.',
    )
    password2 = forms.CharField(
        label='Confirmar nueva contrasena',
        required=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )

    class Meta:
        model = Usuario
        fields = (
            'username',
            'first_name',
            'last_name',
            'rut',
            'email',
            'rol',
            'is_active',
        )
        labels = {
            'username': 'Usuario',
            'first_name': 'Nombre',
            'last_name': 'Apellido',
            'email': 'Correo electronico',
            'is_active': 'Usuario activo',
        }

    def __init__(self, *args, **kwargs):
        self.actor = kwargs.pop('actor', None)
        super().__init__(*args, **kwargs)
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
                Column('rol', css_class='col-md-6'),
            ),
            Row(
                Column('password1', css_class='col-md-6'),
                Column('password2', css_class='col-md-6'),
            ),
            'is_active',
            Submit('submit', 'Actualizar usuario', css_class='btn btn-primary'),
        )

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        qs = Usuario.objects.filter(email__iexact=email)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('Ya existe un usuario con este correo.')
        return email

    def clean_rut(self):
        rut = normalizar_rut(self.cleaned_data['rut'])
        qs = Usuario.objects.filter(rut__iexact=rut)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('Ya existe un usuario con este RUT.')
        return rut

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')

        if password1 or password2:
            if password1 != password2:
                self.add_error('password2', 'Las contrasenas no coinciden.')
            elif password1:
                validate_password(password1, self.instance)

        return cleaned_data

    def clean_rol(self):
        rol = self.cleaned_data['rol']
        if rol == Usuario.ADMINISTRADOR and not self._actor_es_administrador():
            raise forms.ValidationError('No tienes permisos para asignar rol administrador.')
        return rol

    def save(self, commit=True):
        usuario = super().save(commit=False)
        password = self.cleaned_data.get('password1')
        if password:
            usuario.set_password(password)
        if commit:
            usuario.save()
            self.save_m2m()
        return usuario

    def _actor_es_administrador(self):
        return bool(
            self.actor
            and self.actor.is_authenticated
            and (
                self.actor.is_superuser
                or getattr(self.actor, 'rol', None) == Usuario.ADMINISTRADOR
            )
        )

    def _limitar_roles_por_actor(self):
        if not self._actor_es_administrador():
            self.fields['rol'].choices = [
                choice
                for choice in self.fields['rol'].choices
                if choice[0] != Usuario.ADMINISTRADOR
            ]


class CambioPasswordForm(PasswordChangeForm):
    old_password = forms.CharField(
        label='Contrasena actual',
        widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}),
    )
    new_password1 = forms.CharField(
        label='Nueva contrasena',
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )
    new_password2 = forms.CharField(
        label='Confirmar nueva contrasena',
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            'old_password',
            Row(
                Column('new_password1', css_class='col-md-6'),
                Column('new_password2', css_class='col-md-6'),
            ),
            Submit('submit', 'Actualizar contrasena', css_class='btn btn-primary'),
        )
