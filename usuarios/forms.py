import csv
import io
import re

from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Column, Layout, Row, Submit
from django import forms
from django.conf import settings
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    PasswordResetForm,
    SetPasswordForm,
    UserCreationForm,
)
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone

from .identificacion import (
    MENSAJE_RUT_INVALIDO,
    ORIGEN_QR_REGISTRO_CIVIL,
    normalizar_rut,
    parsear_lectura_rut,
)
from .models import (
    AsistenciaReunion,
    DesbloqueoSocio,
    Reunion,
    TELEFONO_MOVIL_MENSAJE_CHILE,
    TELEFONO_MOVIL_PREFIJO_CHILE,
    TELEFONO_MOVIL_REGEX_CHILE,
    Usuario,
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
from .privacidad import TEXTO_ACEPTACION_CONSULTA


def marcar_campo_rut(field):
    """Agrega atributos usados por el formateo visual de RUT en cliente."""
    field.widget.attrs.update(
        {
            'data-rut-format': 'true',
            'autocomplete': 'off',
            'inputmode': 'text',
        }
    )


TIPOS_CONTENIDO_CSV = {
    'application/csv',
    'application/octet-stream',
    'application/vnd.ms-excel',
    'text/csv',
    'text/plain',
}


def validar_archivo_csv(archivo):
    """Valida tamaño, tipo declarado y estructura textual CSV basica."""
    maximo = int(getattr(settings, 'CARGA_CSV_MAX_BYTES', 2 * 1024 * 1024))
    if archivo.size > maximo:
        raise forms.ValidationError(
            f'El archivo supera el máximo permitido de {maximo // (1024 * 1024)} MB.'
        )
    if not archivo.name.lower().endswith('.csv'):
        raise forms.ValidationError('El archivo debe tener extensión .csv.')

    tipo = (getattr(archivo, 'content_type', '') or '').lower()
    if tipo and tipo not in TIPOS_CONTENIDO_CSV:
        raise forms.ValidationError('El tipo de contenido del archivo no corresponde a CSV.')

    posicion = archivo.tell()
    try:
        muestra_binaria = archivo.read(min(65536, maximo))
    finally:
        archivo.seek(posicion)
    if not muestra_binaria:
        raise forms.ValidationError('El archivo CSV está vacío.')
    if b'\x00' in muestra_binaria:
        raise forms.ValidationError('El archivo contiene datos binarios y no es un CSV válido.')

    try:
        muestra = muestra_binaria.decode('utf-8-sig')
    except UnicodeDecodeError:
        try:
            muestra = muestra_binaria.decode('cp1252')
        except UnicodeDecodeError as error:
            raise forms.ValidationError(
                'El archivo debe utilizar codificación UTF-8 o Windows-1252.'
            ) from error

    controles = sum(
        1
        for caracter in muestra
        if ord(caracter) < 32 and caracter not in {'\r', '\n', '\t'}
    )
    if controles:
        raise forms.ValidationError('El archivo contiene caracteres de control no permitidos.')

    primera_linea, _separador, resto = muestra.partition('\n')
    if primera_linea.strip().lower().startswith('sep='):
        muestra = resto
    try:
        dialecto = csv.Sniffer().sniff(muestra[:4096], delimiters=';,')
        encabezados = next(csv.reader(io.StringIO(muestra), dialect=dialecto), [])
    except csv.Error as error:
        raise forms.ValidationError('No fue posible reconocer una estructura CSV válida.') from error
    if len(encabezados) < 2:
        raise forms.ValidationError('El CSV debe contener al menos dos columnas.')
    return archivo


def normalizar_rut_formulario(valor):
    """Normaliza un RUT ingresado por formulario y valida su digito verificador."""
    lectura_rut = parsear_lectura_rut(valor)
    if not lectura_rut:
        raise forms.ValidationError(MENSAJE_RUT_INVALIDO)
    return lectura_rut.rut


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


class FechaIngresoProyectoFormMixin:
    """Configura la fecha de ingreso de socios con default al dia actual."""

    def configurar_fecha_ingreso_proyecto(self):
        """Prepara el campo como fecha opcional con valor por defecto visible."""
        valor_inicial = timezone.localdate()
        if getattr(self, 'instance', None) and self.instance.pk:
            valor_inicial = self.instance.fecha_ingreso_proyecto or valor_inicial
        field = self.fields['fecha_ingreso_proyecto']
        field.required = False
        field.initial = valor_inicial
        field.input_formats = ['%Y-%m-%d']
        field.widget = forms.DateInput(
            attrs={'type': 'date'},
            format='%Y-%m-%d',
        )
        self.initial['fecha_ingreso_proyecto'] = valor_inicial

    def clean_fecha_ingreso_proyecto(self):
        """Usa la fecha actual cuando no se informa fecha de ingreso."""
        return self.cleaned_data.get('fecha_ingreso_proyecto') or timezone.localdate()


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


class RecuperarPasswordForm(PasswordResetForm):
    """Formulario publico para solicitar enlace de recuperacion de usuarios internos."""

    email = forms.EmailField(
        label='Correo electrónico',
        widget=forms.EmailInput(
            attrs={
                'autocomplete': 'email',
                'autofocus': True,
                'placeholder': 'nombre@correo.cl',
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        """Configura crispy forms para el envio del enlace de recuperacion."""
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            'email',
            Submit('submit', 'Enviar enlace', css_class='btn btn-primary w-100'),
        )

    def get_users(self, email):
        """Excluye socios porque no usan contrasena para consultar asistencia."""
        return (
            usuario
            for usuario in super().get_users(email)
            if not rol_es_socio(usuario.rol)
        )


class ReautenticacionForm(forms.Form):
    """Solicita nuevamente la contraseña para operaciones sensibles."""

    password = forms.CharField(
        label='Contraseña',
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                'autocomplete': 'current-password',
                'autofocus': True,
                'class': 'form-control',
            }
        ),
    )


class ConsultaPublicaRutForm(forms.Form):
    """Formulario publico para solicitar una verificacion por correo."""

    MENSAJE_GENERICO = 'No fue posible encontrar informacion para los datos ingresados.'

    rut = forms.CharField(
        label='RUT',
        max_length=12,
        widget=forms.TextInput(
            attrs={
                'autocomplete': 'off',
                'autofocus': True,
                'class': 'form-control form-control-lg',
                'inputmode': 'text',
                'placeholder': '12.345.678-5',
            }
        ),
    )
    anio = forms.IntegerField(
        label='Año',
        required=False,
        min_value=2000,
        widget=forms.NumberInput(
            attrs={
                'class': 'form-control form-control-lg',
                'inputmode': 'numeric',
                'placeholder': '2026',
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        """Configura los campos publicos de solicitud."""
        super().__init__(*args, **kwargs)
        self.fields['anio'].initial = timezone.localdate().year
        self.fields['anio'].max_value = timezone.localdate().year + 1
        marcar_campo_rut(self.fields['rut'])

    def clean_rut(self):
        """Normaliza el RUT sin consultar ni revelar si existe un socio."""
        lectura_rut = parsear_lectura_rut(self.cleaned_data['rut'])
        if not lectura_rut:
            raise forms.ValidationError(self.MENSAJE_GENERICO)
        return lectura_rut.rut

    def clean_anio(self):
        """Usa el año actual cuando la consulta no especifica periodo."""
        anio = self.cleaned_data.get('anio') or timezone.localdate().year
        maximo = timezone.localdate().year + 1
        if anio > maximo:
            raise forms.ValidationError('Ingrese un año válido.')
        return anio


class CodigoConsultaAsistenciaForm(forms.Form):
    """Valida el codigo de un solo uso sin incluirlo en la URL."""

    codigo = forms.CharField(
        label='Código de verificación',
        min_length=6,
        max_length=6,
        widget=forms.TextInput(
            attrs={
                'autocomplete': 'one-time-code',
                'autofocus': True,
                'class': 'form-control form-control-lg',
                'inputmode': 'numeric',
                'pattern': '[0-9]{6}',
                'placeholder': '000000',
            }
        ),
    )

    def clean_codigo(self):
        """Exige exactamente seis digitos decimales."""
        codigo = (self.cleaned_data['codigo'] or '').strip()
        if not codigo.isdecimal() or len(codigo) != 6:
            raise forms.ValidationError('Ingresa el código de seis dígitos.')
        return codigo


class AceptacionPrivacidadConsultaForm(forms.Form):
    """Recoge una accion afirmativa para la version vigente del aviso."""

    acepta = forms.BooleanField(
        required=True,
        label=TEXTO_ACEPTACION_CONSULTA,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        error_messages={
            'required': 'Debes aceptar para utilizar la consulta digital.',
        },
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
        rut = normalizar_rut_formulario(self.cleaned_data['rut'])
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


class SocioCreationForm(TelefonoMovilFormMixin, FechaIngresoProyectoFormMixin, forms.ModelForm):
    """Formulario de alta de socios sin contrasena de acceso."""

    email_confirmacion = forms.EmailField(label='Confirmar correo electrónico')

    class Meta:
        """Campos requeridos para crear una cuenta de socio."""

        model = Usuario
        fields = (
            'first_name',
            'last_name',
            'apellido_materno',
            'rut',
            'email',
            'telefono_movil',
            'fecha_ingreso_proyecto',
            'is_active',
        )
        labels = {
            'first_name': 'Nombre',
            'last_name': 'Apellido paterno',
            'apellido_materno': 'Apellido materno',
            'email': 'Correo electrónico',
            'telefono_movil': 'Teléfono móvil',
            'fecha_ingreso_proyecto': 'Fecha de ingreso al proyecto',
            'is_active': 'Socio activo',
        }

    def __init__(self, *args, **kwargs):
        """Configura crispy forms para el registro operativo de socios."""
        super().__init__(*args, **kwargs)
        self.fields['is_active'].initial = True
        marcar_campo_rut(self.fields['rut'])
        self.configurar_telefono_movil()
        self.configurar_fecha_ingreso_proyecto()
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Row(
                Column('first_name', css_class='col-md-4'),
                Column('last_name', css_class='col-md-4'),
                Column('apellido_materno', css_class='col-md-4'),
            ),
            Row(
                Column('rut', css_class='col-md-6'),
                Column('telefono_movil', css_class='col-md-6'),
            ),
            Row(
                Column('fecha_ingreso_proyecto', css_class='col-md-6'),
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
        rut = normalizar_rut_formulario(self.cleaned_data['rut'])
        if Usuario.objects.filter(rut__iexact=rut).exists():
            raise forms.ValidationError('Ya existe un usuario con este RUT.')
        return rut

    def clean(self):
        """Verifica la confirmacion de correo del socio."""
        cleaned_data = super().clean()
        email = (cleaned_data.get('email') or '').strip().lower()
        email_confirmacion = (cleaned_data.get('email_confirmacion') or '').strip().lower()
        if email and email_confirmacion and email != email_confirmacion:
            self.add_error('email_confirmacion', 'La confirmación del correo no coincide.')

        return cleaned_data

    def save(self, commit=True):
        """Crea un socio con username tecnico y contrasena no utilizable."""
        socio = super().save(commit=False)
        socio.rol = Usuario.SOCIO
        socio.username = socio.email
        socio.set_unusable_password()
        if commit:
            socio.save()
            self.save_m2m()
        return socio


class ReunionCreationForm(forms.ModelForm):
    """Formulario para programar una nueva reunion."""

    HORA_24H_REGEX = r'([01][0-9]|2[0-3]):[0-5][0-9]'
    HORA_24H_MENSAJE = 'Ingresa la hora en formato 24 horas HH:MM.'
    hora = forms.TimeField(
        label='Hora',
        input_formats=['%H:%M'],
        widget=forms.TextInput(
            attrs={
                'type': 'time',
                'autocomplete': 'off',
                'lang': 'es-CL',
                'min': '00:00',
                'max': '23:59',
                'pattern': HORA_24H_REGEX,
                'step': '60',
                'title': HORA_24H_MENSAJE,
            }
        ),
        error_messages={'invalid': HORA_24H_MENSAJE},
    )
    REUNION_DUPLICADA_MENSAJE = (
        'Ya existe una reunion programada para la misma fecha y hora. '
        'Ajusta la fecha u hora antes de guardar.'
    )
    REUNION_PASADA_HISTORICA_MENSAJE = (
        'Las reuniones con fecha y hora anteriores al momento actual deben '
        'registrarse como historicas.'
    )
    ESTADOS_CREACION = (
        (Reunion.PROGRAMADA, 'Programada'),
        (Reunion.HISTORICA, 'Histórica'),
    )

    class Meta:
        """Campos editables al crear una reunion."""

        model = Reunion
        fields = ('fecha', 'hora', 'locacion', 'estado')
        labels = {
            'fecha': 'Fecha',
            'hora': 'Hora',
            'locacion': 'Locación',
            'estado': 'Estado',
        }
        widgets = {
            'fecha': forms.DateInput(attrs={'type': 'date'}),
            'locacion': forms.TextInput(attrs={'autocomplete': 'off'}),
        }

    def __init__(self, *args, **kwargs):
        """Recibe al creador para asociarlo al guardar."""
        self.creador = kwargs.pop('creador', None)
        self.reunion_duplicada = False
        self.reunion_pasada_requiere_historica = False
        super().__init__(*args, **kwargs)
        ahora = timezone.localtime()
        self.fields['estado'].choices = self.ESTADOS_CREACION
        self.fields['estado'].initial = Reunion.PROGRAMADA
        self.fields['fecha'].widget.attrs.update(
            {
                'data-reunion-date': 'true',
                'data-today': ahora.date().isoformat(),
            }
        )
        self.fields['hora'].widget.attrs.update(
            {
                'data-reunion-time': 'true',
                'data-current-time': ahora.strftime('%H:%M'),
            }
        )
        self.fields['estado'].widget.attrs.update(
            {
                'data-reunion-status': 'true',
                'data-historical-value': Reunion.HISTORICA,
            }
        )
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Row(
                Column('fecha', css_class='col-md-4'),
                Column('hora', css_class='col-md-4'),
                Column('locacion', css_class='col-md-4'),
            ),
            Row(
                Column(
                    'estado',
                    css_class='col-md-4',
                ),
                Column(
                    HTML(
                        '''
                        <div class="pt-md-4 d-flex flex-column flex-sm-row align-items-sm-center gap-2">
                            <a href="{% url 'usuarios:descargar_plantilla_asistencia_historica_csv' %}" class="btn btn-outline-primary btn-sm d-inline-flex align-items-center gap-2 flex-shrink-0">
                                {% include "includes/icon.html" with name="file-spreadsheet" %}
                                <span>Plantilla CSV</span>
                            </a>
                            <p class="form-text m-0">
                                Plantilla CSV para carga hist&oacute;rica: usar solo RUT y Situaci&oacute;n. El RUT debe ir sin puntos y con guion, por ejemplo 12345678-9. Situaci&oacute;n acepta A/a para Ausente y P/p para Presente.
                            </p>
                        </div>
                        '''
                    ),
                    css_class='col-md-8 col-lg-6',
                ),
            ),
            Submit('submit', 'Guardar reunion', css_class='btn btn-primary'),
        )

    def clean_hora(self):
        """Exige hora en formato 24 horas con cero inicial."""
        valor = self.data.get(self.add_prefix('hora'), '').strip()
        if not re.fullmatch(self.HORA_24H_REGEX, valor):
            raise forms.ValidationError(self.HORA_24H_MENSAJE)
        return self.cleaned_data['hora']

    def clean(self):
        """Valida reglas de fecha, estado y duplicidad antes de guardar."""
        cleaned_data = super().clean()
        fecha = cleaned_data.get('fecha')
        hora = cleaned_data.get('hora')
        estado = cleaned_data.get('estado')

        if (
            fecha
            and hora
            and self._reunion_es_pasada(fecha, hora)
            and estado != Reunion.HISTORICA
        ):
            self.reunion_pasada_requiere_historica = True
            raise forms.ValidationError(self.REUNION_PASADA_HISTORICA_MENSAJE)

        if fecha and hora and Reunion.objects.filter(fecha=fecha, hora=hora).exists():
            self.reunion_duplicada = True
            raise forms.ValidationError(self.REUNION_DUPLICADA_MENSAJE)

        return cleaned_data

    def _reunion_es_pasada(self, fecha, hora):
        """Compara fecha y hora de la reunion contra el momento local actual."""
        ahora = timezone.localtime()
        hora_actual = ahora.replace(second=0, microsecond=0).time()
        return fecha < ahora.date() or (fecha == ahora.date() and hora < hora_actual)

    def save(self, commit=True):
        """Guarda la reunion con creador y estado validado por el formulario."""
        reunion = super().save(commit=False)
        reunion.creador = self.creador
        if commit:
            reunion.save()
            self.save_m2m()
        return reunion


class ReunionCancelacionForm(forms.Form):
    """Formulario para registrar el motivo obligatorio de cancelacion."""

    motivo_cancelacion = forms.CharField(
        label='Motivo de cancelacion',
        required=True,
        max_length=500,
        widget=forms.Textarea(
            attrs={
                'rows': 4,
                'autocomplete': 'off',
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        """Configura layout consistente con formularios operativos."""
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            'motivo_cancelacion',
            Submit('submit', 'Cancelar reunion', css_class='btn btn-danger'),
        )

    def clean_motivo_cancelacion(self):
        """Normaliza y exige un motivo no vacio."""
        motivo = (self.cleaned_data['motivo_cancelacion'] or '').strip()
        if not motivo:
            raise forms.ValidationError('El motivo de cancelacion es obligatorio.')
        return motivo


class CargaAsistenciaHistoricaForm(forms.Form):
    """Formulario para cargar asistencia historica desde CSV."""

    archivo = forms.FileField(
        label='Archivo CSV',
        required=True,
        help_text=(
            'El CSV debe incluir solo RUT y Situacion. Use RUT sin puntos y con '
            'guion, por ejemplo 12345678-9. Situacion acepta A/a para Ausente '
            'y P/p para Presente.'
        ),
        widget=forms.ClearableFileInput(
            attrs={
                'accept': '.csv,text/csv',
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        """Configura layout y enctype para carga de archivos."""
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_enctype = 'multipart/form-data'
        self.helper.layout = Layout(
            'archivo',
            Submit('submit', 'Cargar asistencia', css_class='btn btn-primary'),
        )

    def clean_archivo(self):
        """Acepta archivos CSV exportados desde planillas."""
        return validar_archivo_csv(self.cleaned_data['archivo'])


class CargaMasivaSociosForm(forms.Form):
    """Formulario para crear socios en lote desde CSV."""

    archivo = forms.FileField(
        label='Archivo CSV',
        required=True,
        help_text=(
            'El CSV debe incluir nombre, apellido_paterno, rut, '
            'correo_electronico, telefono_movil y fecha_ingreso_proyecto. '
            'La fecha debe usar formato YYYY-MM-DD.'
        ),
        widget=forms.ClearableFileInput(
            attrs={
                'accept': '.csv,text/csv',
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        """Configura layout y enctype para carga de archivos."""
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_enctype = 'multipart/form-data'
        self.helper.layout = Layout(
            'archivo',
            Submit('submit', 'Cargar socios', css_class='btn btn-primary'),
        )

    def clean_archivo(self):
        """Acepta archivos CSV exportados desde planillas."""
        return validar_archivo_csv(self.cleaned_data['archivo'])


class JustificacionInasistenciaForm(forms.Form):
    """Formulario para registrar el motivo obligatorio de justificacion."""

    anio = forms.IntegerField(required=False, widget=forms.HiddenInput())
    asistencia = forms.ModelChoiceField(
        label='Reunion a justificar',
        queryset=AsistenciaReunion.objects.none(),
        empty_label='Seleccione una reunion',
        required=True,
    )
    motivo = forms.CharField(
        label='Motivo de justificacion',
        required=True,
        max_length=500,
        widget=forms.Textarea(
            attrs={
                'rows': 4,
                'autocomplete': 'off',
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        """Recibe el socio y responsable de la justificacion."""
        self.socio = kwargs.pop('socio')
        self.usuario = kwargs.pop('usuario')
        self.anio = kwargs.pop('anio', None)
        super().__init__(*args, **kwargs)
        self.fields['anio'].initial = self.anio
        self.fields['asistencia'].queryset = (
            AsistenciaReunion.obtener_ausencias_justificables(
                self.socio,
            )
        )
        self.fields['asistencia'].label_from_instance = self.etiquetar_asistencia
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            'anio',
            'asistencia',
            'motivo',
            Submit('submit', 'Justificar inasistencia', css_class='btn btn-primary'),
        )

    @staticmethod
    def etiquetar_asistencia(asistencia):
        """Muestra fecha, hora y locacion de la reunion ausente."""
        return (
            f'{asistencia.reunion.fecha:%d-%m-%Y} '
            f'{asistencia.reunion.hora:%H:%M} - {asistencia.reunion.locacion}'
        )

    def clean_motivo(self):
        """Normaliza y exige un motivo no vacio."""
        motivo = (self.cleaned_data['motivo'] or '').strip()
        if not motivo:
            raise forms.ValidationError('El motivo de justificacion es obligatorio.')
        return motivo

    def clean(self):
        """Evita registrar justificaciones para socios no bloqueados."""
        cleaned_data = super().clean()
        if self.errors:
            return cleaned_data

        if not AsistenciaReunion.socio_esta_bloqueado(self.socio):
            raise forms.ValidationError('El socio no esta bloqueado por inasistencias.')

        asistencia = cleaned_data.get('asistencia')
        if asistencia and asistencia.socio_id != self.socio.pk:
            self.add_error('asistencia', 'La inasistencia debe pertenecer al socio justificado.')
        if asistencia and asistencia.estado != AsistenciaReunion.AUSENTE:
            self.add_error('asistencia', 'Solo se pueden justificar ausencias.')

        return cleaned_data

    def save(self):
        """Crea el registro administrativo de justificacion."""
        return DesbloqueoSocio.registrar(
            socio=self.socio,
            usuario=self.usuario,
            motivo=self.cleaned_data['motivo'],
            asistencia=self.cleaned_data['asistencia'],
        )


class RegistroAsistenciaRutForm(forms.Form):
    """Formulario para registrar asistencia de un socio existente por RUT."""

    rut = forms.CharField(
        label='RUT',
        required=False,
        max_length=12,
        widget=forms.TextInput(
            attrs={
                'placeholder': '12.345.678-5',
                'autocomplete': 'off',
                'inputmode': 'text',
                'data-rut-manual-input': 'true',
                'aria-disabled': 'true',
                'disabled': 'disabled',
                'readonly': 'readonly',
                'tabindex': '-1',
            }
        ),
    )
    lectura_qr = forms.CharField(
        required=False,
        max_length=512,
        widget=forms.HiddenInput(),
    )

    def __init__(self, *args, **kwargs):
        """Recibe la reunion activa y el usuario que registra."""
        self.reunion = kwargs.pop('reunion')
        self.registrador = kwargs.pop('registrador')
        self.socio = None
        self.lectura_rut = None
        super().__init__(*args, **kwargs)
        marcar_campo_rut(self.fields['rut'])
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Row(
                Column('rut', css_class='col-md-8'),
            ),
            Submit(
                'submit',
                'Registrar por RUT',
                css_class='btn btn-primary',
                data_rut_manual_submit='true',
                disabled='disabled',
                aria_disabled='true',
            ),
        )

    def clean(self):
        """Valida que el RUT o QR corresponda a un socio existente."""
        cleaned_data = super().clean()
        entrada = cleaned_data.get('lectura_qr') or cleaned_data.get('rut')
        lectura_rut = parsear_lectura_rut(entrada)
        if not lectura_rut:
            raise forms.ValidationError('Ingrese un RUT valido o escanee un QR con bloque RUN.')

        rut = lectura_rut.rut
        socio = Usuario.objects.filter(rut__iexact=rut, rol=Usuario.SOCIO).first()

        if not socio:
            raise forms.ValidationError('Solo se pueden registrar socios existentes.')

        if not socio.is_active:
            raise forms.ValidationError('El socio esta inactivo.')

        if AsistenciaReunion.objects.filter(reunion=self.reunion, socio=socio).exists():
            raise forms.ValidationError('El socio ya tiene asistencia registrada en esta reunion.')

        if AsistenciaReunion.socio_esta_bloqueado(socio):
            raise forms.ValidationError(AsistenciaReunion.MENSAJE_SOCIO_BLOQUEADO)

        self.socio = socio
        self.lectura_rut = lectura_rut
        cleaned_data['rut'] = rut
        if self.reunion.estado != Reunion.ACTIVA:
            raise forms.ValidationError('Solo se puede registrar asistencia en una reunion activa.')
        return cleaned_data

    def save(self):
        """Crea el registro de asistencia presente segun el origen detectado."""
        origen = AsistenciaReunion.ORIGEN_RUT
        if self.lectura_rut and self.lectura_rut.origen == ORIGEN_QR_REGISTRO_CIVIL:
            origen = AsistenciaReunion.ORIGEN_QR

        return AsistenciaReunion.registrar_presente(
            reunion=self.reunion,
            socio=self.socio,
            usuario=self.registrador,
            origen=origen,
        )


class SocioUpdateForm(TelefonoMovilFormMixin, FechaIngresoProyectoFormMixin, forms.ModelForm):
    """Formulario específico para editar socios sin exponer rol ni password."""

    email_confirmacion = forms.EmailField(label='Confirmar correo electrónico')

    class Meta:
        """Campos editables para mantener datos operativos del socio."""

        model = Usuario
        fields = (
            'first_name',
            'last_name',
            'apellido_materno',
            'rut',
            'email',
            'telefono_movil',
            'fecha_ingreso_proyecto',
        )
        labels = {
            'first_name': 'Nombre',
            'last_name': 'Apellido paterno',
            'apellido_materno': 'Apellido materno',
            'fecha_ingreso_proyecto': 'Fecha de ingreso al proyecto',
            'email': 'Correo electrónico',
            'telefono_movil': 'Teléfono móvil',
        }

    def __init__(self, *args, **kwargs):
        """Construye layout de edición sin permitir cambiar el RUT."""
        super().__init__(*args, **kwargs)
        self.fields['rut'].disabled = True
        marcar_campo_rut(self.fields['rut'])
        self.configurar_telefono_movil()
        self.configurar_fecha_ingreso_proyecto()
        self.fields['rut'].help_text = 'El RUT no puede modificarse una vez creado.'
        if self.instance.pk:
            self.initial['rut'] = normalizar_rut(self.instance.rut)
            self.initial['email_confirmacion'] = self.instance.email
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Row(
                Column('first_name', css_class='col-md-4'),
                Column('last_name', css_class='col-md-4'),
                Column('apellido_materno', css_class='col-md-4'),
            ),
            Row(
                Column('rut', css_class='col-md-6'),
                Column('telefono_movil', css_class='col-md-6'),
            ),
            Row(
                Column('fecha_ingreso_proyecto', css_class='col-md-6'),
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
        return normalizar_rut_formulario(self.cleaned_data['rut'])

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

        rut = normalizar_rut_formulario(self.cleaned_data['rut'])
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


class RestablecerPasswordForm(SetPasswordForm):
    """Formulario para definir una nueva contrasena desde un token valido."""

    new_password1 = forms.CharField(
        label='Nueva contraseña',
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )
    new_password2 = forms.CharField(
        label='Confirmar nueva contraseña',
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )

    def __init__(self, *args, **kwargs):
        """Configura crispy forms para el restablecimiento publico."""
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Row(
                Column('new_password1', css_class='col-md-6'),
                Column('new_password2', css_class='col-md-6'),
            ),
            Submit('submit', 'Guardar contraseña', css_class='btn btn-primary'),
        )
