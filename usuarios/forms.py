from crispy_forms.helper import FormHelper
from crispy_forms.layout import Column, Layout, Row, Submit
from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

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
        super().__init__(*args, **kwargs)
        self.fields['is_active'].initial = True
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


class UsuarioUpdateForm(forms.ModelForm):
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
        super().__init__(*args, **kwargs)
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
