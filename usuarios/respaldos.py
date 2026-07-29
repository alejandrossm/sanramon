"""Creacion consistente y cifrado autenticado de respaldos SQLite."""

import sqlite3
from pathlib import Path
from tempfile import NamedTemporaryFile

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings


class ErrorCifradoRespaldo(Exception):
    """Indica configuracion o contenido invalido del respaldo."""


def obtener_cifrador_respaldos():
    """Construye MultiFernet; la primera clave cifra y todas pueden descifrar."""
    claves = getattr(settings, 'RESPALDO_ENCRYPTION_KEYS', [])
    if isinstance(claves, str):
        claves = [clave.strip() for clave in claves.split(',') if clave.strip()]
    if not claves:
        raise ErrorCifradoRespaldo(
            'No hay una clave de cifrado de respaldos configurada.'
        )
    try:
        return MultiFernet([Fernet(clave.encode('ascii')) for clave in claves])
    except (TypeError, ValueError) as error:
        raise ErrorCifradoRespaldo(
            'La clave de cifrado de respaldos no es valida.'
        ) from error


def crear_copia_sqlite_consistente(ruta_origen):
    """Genera bytes de una copia SQLite mediante la API nativa de backup."""
    ruta_origen = Path(ruta_origen)
    with NamedTemporaryFile(suffix='.sqlite3', delete=False) as temporal:
        ruta_temporal = Path(temporal.name)

    origen = None
    destino = None
    try:
        origen = sqlite3.connect(str(ruta_origen))
        destino = sqlite3.connect(str(ruta_temporal))
        origen.backup(destino)
        destino.close()
        destino = None
        origen.close()
        origen = None
        return ruta_temporal.read_bytes()
    except sqlite3.Error as error:
        raise ErrorCifradoRespaldo(
            'No fue posible crear una copia SQLite consistente.'
        ) from error
    finally:
        if destino is not None:
            destino.close()
        if origen is not None:
            origen.close()
        ruta_temporal.unlink(missing_ok=True)


def cifrar_respaldo_sqlite(ruta_origen):
    """Cifra y autentica una copia consistente de la base SQLite."""
    contenido = crear_copia_sqlite_consistente(ruta_origen)
    return obtener_cifrador_respaldos().encrypt(contenido)


def descifrar_respaldo(contenido):
    """Descifra un respaldo para restauracion controlada o pruebas."""
    try:
        return obtener_cifrador_respaldos().decrypt(contenido)
    except InvalidToken as error:
        raise ErrorCifradoRespaldo(
            'El respaldo no es autentico o no corresponde a las claves configuradas.'
        ) from error
