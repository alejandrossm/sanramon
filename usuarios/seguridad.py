"""Controles de fuerza bruta y reautenticacion para operaciones sensibles."""

from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import salted_hmac

from .models import IntentoAcceso


SESION_REAUTENTICADA_HASTA = 'seguridad_reautenticada_hasta'


def _entero_configurado(nombre, predeterminado):
    valor = int(getattr(settings, nombre, predeterminado))
    return valor if valor > 0 else predeterminado


def hash_identificador(valor, proposito):
    """Seudonimiza identificadores e IP con una clave del servidor."""
    normalizado = str(valor or '').strip().casefold()
    return salted_hmac(
        f'seguridad-{proposito}',
        normalizado,
        secret=settings.SECRET_KEY,
        algorithm='sha256',
    ).hexdigest()


def obtener_ip_hash(request):
    """Usa la IP observada por Django sin conservarla en texto legible."""
    return hash_identificador(request.META.get('REMOTE_ADDR', ''), 'ip')


def _configuracion_tipo(tipo):
    if tipo == IntentoAcceso.RECUPERACION:
        return {
            'ventana': _entero_configurado(
                'SEGURIDAD_RECUPERACION_VENTANA_MINUTOS',
                60,
            ),
            'max_identificador': _entero_configurado(
                'SEGURIDAD_RECUPERACION_MAX_IDENTIFICADOR',
                3,
            ),
            'max_ip': _entero_configurado('SEGURIDAD_RECUPERACION_MAX_IP', 10),
        }
    if tipo == IntentoAcceso.REAUTENTICACION:
        return {
            'ventana': _entero_configurado(
                'SEGURIDAD_LOGIN_VENTANA_MINUTOS',
                15,
            ),
            'max_identificador': _entero_configurado(
                'SEGURIDAD_LOGIN_MAX_IDENTIFICADOR',
                5,
            ),
            'max_ip': _entero_configurado('SEGURIDAD_LOGIN_MAX_IP', 20),
        }
    return {
        'ventana': _entero_configurado('SEGURIDAD_LOGIN_VENTANA_MINUTOS', 15),
        'max_identificador': _entero_configurado(
            'SEGURIDAD_LOGIN_MAX_IDENTIFICADOR',
            5,
        ),
        'max_ip': _entero_configurado('SEGURIDAD_LOGIN_MAX_IP', 20),
    }


def acceso_limitado(tipo, identificador, request):
    """Evalua limites persistentes por identificador e IP."""
    configuracion = _configuracion_tipo(tipo)
    desde = timezone.now() - timedelta(minutes=configuracion['ventana'])
    identificador_hash = hash_identificador(identificador, tipo)
    ip_hash = obtener_ip_hash(request)
    intentos = IntentoAcceso.objects.filter(tipo=tipo, fecha__gte=desde)
    return (
        intentos.filter(identificador_hash=identificador_hash).count()
        >= configuracion['max_identificador']
        or intentos.filter(ip_hash=ip_hash).count() >= configuracion['max_ip']
    )


def registrar_intento(tipo, identificador, request):
    """Registra un intento fallido o una solicitud de recuperacion."""
    purgar_intentos_antiguos()
    return IntentoAcceso.objects.create(
        tipo=tipo,
        identificador_hash=hash_identificador(identificador, tipo),
        ip_hash=obtener_ip_hash(request),
    )


def limpiar_intentos(tipo, identificador):
    """Retira fallos del identificador despues de autenticacion correcta."""
    IntentoAcceso.objects.filter(
        tipo=tipo,
        identificador_hash=hash_identificador(identificador, tipo),
    ).delete()


def purgar_intentos_antiguos():
    """Limita a una vez al dia la eliminacion de intentos antiguos."""
    clave = 'seguridad:purga-intentos:v1'
    if not cache.add(clave, True, timeout=24 * 60 * 60):
        return 0
    dias = _entero_configurado('SEGURIDAD_INTENTOS_RETENCION_DIAS', 30)
    eliminados, _detalle = IntentoAcceso.objects.filter(
        fecha__lt=timezone.now() - timedelta(days=dias),
    ).delete()
    return eliminados


def marcar_reautenticacion(request):
    """Marca la sesion como recientemente autenticada."""
    minutos = _entero_configurado('SEGURIDAD_REAUTENTICACION_MINUTOS', 10)
    request.session[SESION_REAUTENTICADA_HASTA] = (
        timezone.now() + timedelta(minutes=minutos)
    ).isoformat()


def reautenticacion_vigente(request):
    """Comprueba el vencimiento de la autenticacion reciente."""
    valor = request.session.get(SESION_REAUTENTICADA_HASTA)
    if not valor:
        return False
    try:
        limite = datetime.fromisoformat(valor)
    except (TypeError, ValueError):
        request.session.pop(SESION_REAUTENTICADA_HASTA, None)
        return False
    if timezone.is_naive(limite):
        limite = timezone.make_aware(limite)
    if limite <= timezone.now():
        request.session.pop(SESION_REAUTENTICADA_HASTA, None)
        return False
    return True


def reautenticacion_reciente_required(view_func):
    """Exige contraseña reciente antes de una descarga sensible."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if reautenticacion_vigente(request):
            return view_func(request, *args, **kwargs)
        messages.info(
            request,
            'Confirma tu contraseña para realizar esta descarga sensible.',
        )
        consulta = urlencode({'next': request.get_full_path()})
        return redirect(f"{reverse('usuarios:reauth_seguridad')}?{consulta}")

    return wrapper
