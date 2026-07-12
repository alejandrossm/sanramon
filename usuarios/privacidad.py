"""Controles para la consulta de asistencia protegida por codigo de correo."""

import hashlib
import secrets
from datetime import datetime, timedelta

from django.conf import settings
from django.core.cache import cache
from django.core.mail import BadHeaderError, send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from smtplib import SMTPException

from .models import AceptacionPrivacidadConsulta, SolicitudCodigoConsulta


POLITICA_PRIVACIDAD_VERSION = '2026-06-29'
TEXTO_ACEPTACION_CONSULTA = (
    'He leído la política de privacidad y autorizo el tratamiento de mis '
    'datos personales para verificar mi identidad por correo y consultar '
    'digitalmente mi historial de asistencia.'
)

SESION_SOLICITUD_ID = 'consulta_asistencia_solicitud_id'
SESION_ANIO = 'consulta_asistencia_anio'
SESION_SOCIO_ID = 'consulta_asistencia_socio_id'
SESION_AUTORIZADA_HASTA = 'consulta_asistencia_autorizada_hasta'

RESULTADO_CODIGO_VALIDO = 'VALIDO'
RESULTADO_CODIGO_INVALIDO = 'INVALIDO'
RESULTADO_CODIGO_EXPIRADO = 'EXPIRADO'
RESULTADO_CODIGO_BLOQUEADO = 'BLOQUEADO'


def _configuracion_entera(nombre, predeterminado):
    """Obtiene una configuracion positiva con un valor seguro por defecto."""
    valor = int(getattr(settings, nombre, predeterminado))
    return valor if valor > 0 else predeterminado


def duracion_codigo():
    """Duracion configurada del codigo de verificacion."""
    minutos = _configuracion_entera('CONSULTA_CODIGO_DURACION_MINUTOS', 10)
    return timedelta(minutes=minutos)


def duracion_sesion_autorizada():
    """Duracion configurada de la sesion de consulta verificada."""
    minutos = _configuracion_entera('CONSULTA_SESION_DURACION_MINUTOS', 15)
    return timedelta(minutes=minutos)


def maximo_intentos_codigo():
    """Numero maximo de intentos permitidos por codigo."""
    return _configuracion_entera('CONSULTA_CODIGO_MAX_INTENTOS', 5)


def hash_texto_aceptacion():
    """Huella del texto exacto aceptado por el socio."""
    return hashlib.sha256(TEXTO_ACEPTACION_CONSULTA.encode('utf-8')).hexdigest()


def hash_dato_seguridad(valor, proposito):
    """Seudonimiza IP u otro dato auxiliar usando la clave del servidor."""
    return salted_hmac(
        f'consulta-asistencia-{proposito}',
        str(valor or ''),
        secret=settings.SECRET_KEY,
        algorithm='sha256',
    ).hexdigest()


def obtener_ip_hash(request):
    """Obtiene una huella no reversible de la IP observada por Django."""
    return hash_dato_seguridad(request.META.get('REMOTE_ADDR', ''), 'ip')


def generar_codigo():
    """Genera un codigo decimal de seis digitos con fuente criptografica."""
    return f'{secrets.randbelow(1_000_000):06d}'


def _hash_codigo(solicitud_id, codigo):
    return salted_hmac(
        'consulta-asistencia-codigo',
        f'{solicitud_id}:{codigo}',
        secret=settings.SECRET_KEY,
        algorithm='sha256',
    ).hexdigest()


def _limite_alcanzado(socio, ahora):
    ventana_minutos = _configuracion_entera(
        'CONSULTA_CODIGO_VENTANA_MINUTOS',
        2,
    )
    desde = ahora - timedelta(minutes=ventana_minutos)
    if socio is None:
        return False

    maximo_socio = _configuracion_entera(
        'CONSULTA_CODIGO_MAX_SOLICITUDES_SOCIO',
        3,
    )
    return SolicitudCodigoConsulta.objects.filter(
        socio=socio,
        fecha_solicitud__gte=desde,
    ).count() >= maximo_socio


def purgar_solicitudes_antiguas(ahora=None):
    """Elimina OTP antiguos de forma oportunista, como maximo una vez al dia."""
    clave_cache = 'privacidad:purga-solicitudes-otp:v1'
    if not cache.add(clave_cache, True, timeout=24 * 60 * 60):
        return 0

    ahora = ahora or timezone.now()
    dias = _configuracion_entera('CONSULTA_CODIGO_RETENCION_DIAS', 30)
    eliminados, _detalle = SolicitudCodigoConsulta.objects.filter(
        fecha_solicitud__lt=ahora - timedelta(days=dias),
    ).delete()
    return eliminados


def crear_solicitud_codigo(socio, ip_hash, anio):
    """Crea una solicitud real o indistinguible y envia el codigo si procede."""
    ahora = timezone.now()
    purgar_solicitudes_antiguas(ahora)
    limitado = _limite_alcanzado(socio, ahora)
    socio_solicitud = socio if socio is not None and not limitado else None
    codigo = generar_codigo()
    solicitud = SolicitudCodigoConsulta(
        socio=socio_solicitud,
        codigo_hash='',
        ip_hash=ip_hash,
        fecha_solicitud=ahora,
        fecha_expiracion=ahora + duracion_codigo(),
    )
    solicitud.codigo_hash = _hash_codigo(solicitud.pk, codigo)
    solicitud.save()

    if socio_solicitud is None:
        return solicitud

    SolicitudCodigoConsulta.objects.filter(
        socio=socio_solicitud,
        fecha_uso__isnull=True,
        fecha_expiracion__gt=ahora,
    ).exclude(pk=solicitud.pk).update(fecha_expiracion=ahora)

    try:
        enviados = send_mail(
            'Codigo para consultar tu asistencia',
            render_to_string(
                'usuarios/emails/codigo_consulta_asistencia.txt',
                {
                    'codigo': codigo,
                    'minutos_vigencia': int(duracion_codigo().total_seconds() // 60),
                    'anio': anio,
                },
            ),
            None,
            [socio_solicitud.email],
            fail_silently=False,
        )
    except (BadHeaderError, OSError, SMTPException):
        enviados = 0

    if enviados:
        solicitud.email_enviado = True
        solicitud.save(update_fields=['email_enviado'])
    else:
        solicitud.fecha_expiracion = ahora
        solicitud.save(update_fields=['fecha_expiracion'])

    return solicitud


@transaction.atomic
def verificar_codigo(solicitud_id, codigo):
    """Valida de forma atomica expiracion, intentos, uso unico y codigo."""
    try:
        solicitud = (
            SolicitudCodigoConsulta.objects
            .select_for_update()
            .select_related('socio')
            .get(pk=solicitud_id)
        )
    except (SolicitudCodigoConsulta.DoesNotExist, ValueError):
        return RESULTADO_CODIGO_INVALIDO, None

    ahora = timezone.now()
    if solicitud.fecha_uso is not None or solicitud.fecha_expiracion <= ahora:
        return RESULTADO_CODIGO_EXPIRADO, None

    if solicitud.intentos_fallidos >= maximo_intentos_codigo():
        return RESULTADO_CODIGO_BLOQUEADO, None

    codigo_valido = constant_time_compare(
        solicitud.codigo_hash,
        _hash_codigo(solicitud.pk, codigo),
    )
    if not solicitud.esta_vigente(ahora) or not codigo_valido:
        solicitud.intentos_fallidos += 1
        solicitud.save(update_fields=['intentos_fallidos'])
        if solicitud.intentos_fallidos >= maximo_intentos_codigo():
            return RESULTADO_CODIGO_BLOQUEADO, None
        return RESULTADO_CODIGO_INVALIDO, None

    solicitud.fecha_uso = ahora
    solicitud.save(update_fields=['fecha_uso'])
    return RESULTADO_CODIGO_VALIDO, solicitud.socio


def autorizar_sesion_consulta(request, socio):
    """Vincula temporalmente la sesion anonima con el socio verificado."""
    request.session.cycle_key()
    request.session[SESION_SOCIO_ID] = socio.pk
    request.session[SESION_AUTORIZADA_HASTA] = (
        timezone.now() + duracion_sesion_autorizada()
    ).isoformat()
    request.session.pop(SESION_SOLICITUD_ID, None)


def obtener_socio_autorizado(request):
    """Devuelve el socio mientras la autorizacion temporal siga vigente."""
    socio_id = request.session.get(SESION_SOCIO_ID)
    autorizada_hasta = request.session.get(SESION_AUTORIZADA_HASTA)
    if not socio_id or not autorizada_hasta:
        return None

    try:
        limite = datetime.fromisoformat(autorizada_hasta)
    except (TypeError, ValueError):
        limpiar_sesion_consulta(request)
        return None

    if timezone.is_naive(limite):
        limite = timezone.make_aware(limite)
    if limite <= timezone.now():
        limpiar_sesion_consulta(request)
        return None

    from .models import Usuario

    return Usuario.objects.filter(pk=socio_id, rol=Usuario.SOCIO).first()


def limpiar_sesion_consulta(request):
    """Elimina solo las claves asociadas al flujo publico de asistencia."""
    for clave in (
        SESION_SOLICITUD_ID,
        SESION_ANIO,
        SESION_SOCIO_ID,
        SESION_AUTORIZADA_HASTA,
    ):
        request.session.pop(clave, None)


def aceptacion_privacidad_vigente(socio):
    """Comprueba version y huella para invalidar textos modificados."""
    return AceptacionPrivacidadConsulta.objects.filter(
        socio=socio,
        version_politica=POLITICA_PRIVACIDAD_VERSION,
        texto_hash=hash_texto_aceptacion(),
    ).exists()


def registrar_aceptacion_privacidad(socio, ip_hash):
    """Crea idempotentemente la evidencia del aviso aceptado."""
    aceptacion, _creada = AceptacionPrivacidadConsulta.objects.update_or_create(
        socio=socio,
        version_politica=POLITICA_PRIVACIDAD_VERSION,
        defaults={
            'texto_hash': hash_texto_aceptacion(),
            'metodo_verificacion': (
                AceptacionPrivacidadConsulta.METODO_EMAIL_OTP
            ),
            'ip_hash': ip_hash,
            'fecha_aceptacion': timezone.now(),
        },
    )
    return aceptacion
