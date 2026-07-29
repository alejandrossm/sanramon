"""Construye un ZIP reproducible con solo los archivos necesarios en produccion."""

from __future__ import annotations

import hashlib
import re
import subprocess
import zipfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / 'dist'
ARCHIVOS_RAIZ = {'manage.py', 'requirements.txt'}
DIRECTORIOS_COMPLETOS = {'templates'}
ARCHIVOS_STATIC = {
    'static/css/styles.css',
    'static/images/f01.jpeg',
    'static/images/f02.jpeg',
    'static/images/f03.jpeg',
    'static/images/logo.png',
    'static/js/app.js',
    'static/js/dashboard.js',
    'static/js/reuniones.js',
    'static/vendor/bootstrap-icons/LICENSE',
    'static/vendor/bootstrap-icons/bootstrap-icons.min.css',
    'static/vendor/bootstrap-icons/fonts/bootstrap-icons.woff',
    'static/vendor/bootstrap-icons/fonts/bootstrap-icons.woff2',
    'static/vendor/bootstrap/bootstrap.bundle.min.js',
    'static/vendor/bootstrap/bootstrap.min.css',
    'static/vendor/chart.js/chart.min.js',
    'static/vendor/sweetalert2/sweetalert2.all.min.js',
}
ARCHIVOS_CONFIG = {
    'config/__init__.py',
    'config/admin.py',
    'config/apps.py',
    'config/settings.py',
    'config/urls.py',
    'config/wsgi.py',
}
REQUERIDOS = {
    'manage.py',
    'requirements.txt',
    'config/settings.py',
    'config/wsgi.py',
    'usuarios/models.py',
    'usuarios/migrations/__init__.py',
    'templates/base.html',
    'static/css/styles.css',
}
FECHA_ZIP_REPRODUCIBLE = (2026, 1, 1, 0, 0, 0)


def obtener_archivos_versionados() -> list[str]:
    """Obtiene archivos de Git para no incluir datos locales o generados."""
    resultado = subprocess.run(
        ['git', 'ls-files', '-z'],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return sorted(
        ruta
        for ruta in resultado.stdout.decode('utf-8').split('\0')
        if ruta
    )


def es_archivo_runtime(ruta: str) -> bool:
    """Aplica una lista permitida cerrada para el contenido desplegable."""
    posix = PurePosixPath(ruta)
    if ruta in ARCHIVOS_RAIZ or ruta in ARCHIVOS_CONFIG or ruta in ARCHIVOS_STATIC:
        return True
    if posix.parts and posix.parts[0] in DIRECTORIOS_COMPLETOS:
        return True
    if ruta == 'usuarios/__init__.py':
        return True
    if len(posix.parts) == 2 and posix.parts[0] == 'usuarios':
        return posix.suffix == '.py' and posix.name != 'tests.py'
    if ruta.startswith('usuarios/migrations/'):
        return posix.suffix == '.py'
    if ruta.startswith('usuarios/templates/'):
        return True
    return False


def informacion_zip(ruta: str) -> zipfile.ZipInfo:
    """Fija metadatos para producir el mismo ZIP desde el mismo contenido."""
    info = zipfile.ZipInfo(ruta, FECHA_ZIP_REPRODUCIBLE)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    info.create_system = 3
    return info


def construir() -> tuple[Path, Path, list[str]]:
    """Crea el paquete y su checksum SHA-256."""
    version = (ROOT / 'VERSION').read_text(encoding='utf-8').strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise RuntimeError('VERSION debe usar el formato X.Y.Z.')

    archivos = [
        ruta
        for ruta in obtener_archivos_versionados()
        if es_archivo_runtime(ruta)
    ]
    faltantes = sorted(REQUERIDOS.difference(archivos))
    if faltantes:
        raise RuntimeError(
            'Faltan archivos obligatorios del release: '
            + ', '.join(faltantes)
        )

    DIST.mkdir(exist_ok=True)
    destino = DIST / f'sanramon-{version}.zip'
    checksums = []
    with zipfile.ZipFile(
        destino,
        mode='w',
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as paquete:
        for ruta in archivos:
            contenido = (ROOT / Path(ruta)).read_bytes()
            checksums.append(f'{hashlib.sha256(contenido).hexdigest()}  {ruta}')
            paquete.writestr(informacion_zip(ruta), contenido)

        manifiesto = (
            f'Version: {version}\n'
            f'Archivos: {len(archivos)}\n\n'
            + '\n'.join(checksums)
            + '\n'
        ).encode('utf-8')
        paquete.writestr(
            informacion_zip('RELEASE-MANIFEST.txt'),
            manifiesto,
        )

    digest = hashlib.sha256(destino.read_bytes()).hexdigest()
    checksum = destino.with_suffix('.zip.sha256')
    checksum.write_text(
        f'{digest}  {destino.name}\n',
        encoding='utf-8',
        newline='\n',
    )
    return destino, checksum, archivos


if __name__ == '__main__':
    zip_release, checksum_release, incluidos = construir()
    print(f'Artefacto: {zip_release.relative_to(ROOT)}')
    print(f'Checksum: {checksum_release.relative_to(ROOT)}')
    print(f'Archivos runtime: {len(incluidos)}')
