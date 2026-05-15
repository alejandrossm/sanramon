import re
from dataclasses import dataclass


ORIGEN_RUT_MANUAL = 'RUT'
ORIGEN_QR_REGISTRO_CIVIL = 'QR'


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
        return LecturaRut(
            rut=normalizar_rut(f'{run_match.group(1)}-{run_match.group(2)}'),
            origen=ORIGEN_QR_REGISTRO_CIVIL,
        )

    rut_match = RUT_MANUAL_REGEX.fullmatch(lectura)
    if rut_match:
        return LecturaRut(
            rut=normalizar_rut(f'{rut_match.group(1)}-{rut_match.group(2)}'),
            origen=ORIGEN_RUT_MANUAL,
        )

    return None
