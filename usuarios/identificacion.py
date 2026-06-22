import re
from dataclasses import dataclass

from django.core.exceptions import ValidationError


ORIGEN_RUT_MANUAL = 'RUT'
ORIGEN_QR_REGISTRO_CIVIL = 'QR'
MENSAJE_RUT_INVALIDO = 'Ingrese un RUT valido.'


@dataclass(frozen=True)
class LecturaRut:
    """Resultado normalizado de una lectura de RUT/RUN."""

    rut: str
    origen: str


RUN_QR_REGEX = re.compile(
    r'(?:^|[^A-Z0-9])RUN\s*=\s*([0-9]{7,8})\s*-?\s*([0-9K])(?=[^0-9K]|$)',
    re.IGNORECASE,
)
RUT_MANUAL_REGEX = re.compile(
    r'^\s*([0-9]{1,2}(?:\.[0-9]{3}){2}|[0-9]{7,8})\s*-?\s*([0-9K])\s*$',
    re.IGNORECASE,
)


def normalizar_rut(rut):
    """Normaliza el RUT al formato cuerpo-digito, sin puntos."""
    valor = ''.join(
        caracter
        for caracter in (rut or '').upper()
        if caracter not in '.-' and not caracter.isspace()
    )
    if len(valor) <= 1:
        return valor
    return f'{valor[:-1]}-{valor[-1]}'


def calcular_digito_verificador_rut(cuerpo):
    """Calcula el digito verificador chileno usando modulo 11."""
    cuerpo = ''.join(caracter for caracter in str(cuerpo or '') if caracter.isdigit())
    if not cuerpo:
        return ''

    multiplicador = 2
    total = 0
    for digito in reversed(cuerpo):
        total += int(digito) * multiplicador
        multiplicador = 2 if multiplicador == 7 else multiplicador + 1

    resultado = 11 - (total % 11)
    if resultado == 11:
        return '0'
    if resultado == 10:
        return 'K'
    return str(resultado)


def rut_tiene_digito_verificador_valido(rut):
    """Indica si el RUT tiene un digito verificador chileno correcto."""
    normalizado = normalizar_rut(rut)
    if '-' not in normalizado:
        return False

    cuerpo, digito_verificador = normalizado.split('-', 1)
    if not (cuerpo.isdigit() and len(cuerpo) in {7, 8} and len(digito_verificador) == 1):
        return False

    return calcular_digito_verificador_rut(cuerpo) == digito_verificador.upper()


def validar_rut_chileno(rut):
    """Valida un RUT chileno con formato aceptado y digito verificador."""
    if not RUT_MANUAL_REGEX.fullmatch(str(rut or '').strip()):
        raise ValidationError(MENSAJE_RUT_INVALIDO)
    if not rut_tiene_digito_verificador_valido(rut):
        raise ValidationError(MENSAJE_RUT_INVALIDO)


def normalizar_lectura_scanner(valor):
    """Corrige caracteres frecuentes cuando el scanner usa otra distribucion."""
    return (
        (valor or '')
        .strip()
        .upper()
        .replace('Ñ', ':')
        .replace('¿', '=')
        .replace("'", '-')
        .replace('’', '-')
        .replace('´', '-')
    )


def parsear_lectura_rut(valor):
    """Extrae un RUT normalizado desde un RUT manual o payload QR con bloque RUN."""
    lectura = normalizar_lectura_scanner(valor)
    if not lectura:
        return None

    run_match = RUN_QR_REGEX.search(lectura)
    if run_match:
        rut = normalizar_rut(f'{run_match.group(1)}-{run_match.group(2)}')
        if not rut_tiene_digito_verificador_valido(rut):
            return None
        return LecturaRut(
            rut=rut,
            origen=ORIGEN_QR_REGISTRO_CIVIL,
        )

    rut_match = RUT_MANUAL_REGEX.fullmatch(lectura)
    if rut_match:
        rut = normalizar_rut(f'{rut_match.group(1)}-{rut_match.group(2)}')
        if not rut_tiene_digito_verificador_valido(rut):
            return None
        return LecturaRut(
            rut=rut,
            origen=ORIGEN_RUT_MANUAL,
        )

    return None
