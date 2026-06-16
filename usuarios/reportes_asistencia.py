import csv
import io
import textwrap
import zipfile
from xml.sax.saxutils import escape as xml_escape


COLUMNAS_REPORTE_ASISTENCIA = [
    ('anio', 'Ano'),
    ('rut', 'RUT'),
    ('username', 'Usuario'),
    ('first_name', 'Nombre'),
    ('last_name', 'Apellido paterno'),
    ('apellido_materno', 'Apellido materno'),
    ('email', 'Correo electronico'),
    ('telefono_movil', 'Telefono movil'),
    ('fecha_ingreso_proyecto', 'Fecha ingreso proyecto'),
    ('date_joined', 'Fecha alta sistema'),
    ('rol', 'Rol'),
    ('estado_actual', 'Estado actual'),
    ('total_reuniones', 'Reuniones realizadas'),
    ('total_asistencias', 'Asistencias'),
    ('total_ausencias', 'Inasistencias'),
    ('total_ausencias_efectivas', 'Inasistencias efectivas'),
    ('total_justificaciones', 'Justificaciones'),
    ('indicador', 'Indicador'),
]


def construir_dataset_asistencia_anual(socios, anio):
    """Construye encabezados y filas completas para reportes de asistencia anual."""
    encabezados = [etiqueta for _clave, etiqueta in COLUMNAS_REPORTE_ASISTENCIA]
    filas = []

    for socio in socios:
        filas.append(
            [
                anio,
                socio.rut,
                socio.username,
                socio.first_name,
                socio.last_name,
                socio.apellido_materno,
                socio.email,
                socio.telefono_movil or '',
                socio.fecha_ingreso_proyecto.isoformat()
                if socio.fecha_ingreso_proyecto
                else '',
                socio.date_joined.date().isoformat() if socio.date_joined else '',
                socio.get_rol_display(),
                'Activo' if socio.is_active else 'Inactivo',
                socio.total_reuniones,
                socio.total_asistencias,
                socio.total_ausencias,
                socio.total_ausencias_efectivas,
                socio.total_justificaciones,
                socio.indicador_asistencia['label'],
            ]
        )

    return encabezados, filas


def construir_csv(encabezados, filas):
    """Genera CSV UTF-8 con BOM para abrir correctamente en planillas."""
    salida = io.StringIO(newline='')
    salida.write('\ufeff')
    writer = csv.writer(salida)
    writer.writerow(encabezados)
    writer.writerows(filas)
    return salida.getvalue().encode('utf-8')


def construir_xlsx(encabezados, filas, nombre_hoja='Asistencia anual'):
    """Genera un XLSX basico sin dependencias externas."""
    salida = io.BytesIO()
    todas_las_filas = [encabezados, *filas]

    with zipfile.ZipFile(salida, 'w', compression=zipfile.ZIP_DEFLATED) as archivo:
        archivo.writestr(
            '[Content_Types].xml',
            (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                '</Types>'
            ),
        )
        archivo.writestr(
            '_rels/.rels',
            (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                '</Relationships>'
            ),
        )
        archivo.writestr(
            'xl/workbook.xml',
            (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<sheets>'
                f'<sheet name="{xml_escape(nombre_hoja)}" sheetId="1" r:id="rId1"/>'
                '</sheets>'
                '</workbook>'
            ),
        )
        archivo.writestr(
            'xl/_rels/workbook.xml.rels',
            (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
                '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                '</Relationships>'
            ),
        )
        archivo.writestr(
            'xl/styles.xml',
            (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                '<numFmts count="0"/>'
                '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
                '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
                '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
                '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
                '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>'
                '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
                '<dxfs count="0"/>'
                '<tableStyles count="0" defaultTableStyle="TableStyleMedium9" defaultPivotStyle="PivotStyleLight16"/>'
                '</styleSheet>'
            ),
        )
        archivo.writestr(
            'xl/worksheets/sheet1.xml',
            _construir_worksheet_xml(todas_las_filas),
        )

    return salida.getvalue()


def _construir_worksheet_xml(filas):
    filas_xml = []
    for indice_fila, fila in enumerate(filas, start=1):
        celdas = []
        for indice_columna, valor in enumerate(fila, start=1):
            referencia = f'{_columna_excel(indice_columna)}{indice_fila}'
            celdas.append(_construir_celda_xml(referencia, valor))
        filas_xml.append(f'<row r="{indice_fila}">{"".join(celdas)}</row>')

    anchos_base = [
        10,
        14,
        20,
        18,
        20,
        20,
        32,
        16,
        18,
        18,
        18,
        14,
        18,
        14,
        14,
        20,
        18,
        18,
    ]
    total_columnas = len(filas[0]) if filas and filas[0] else 1
    anchos = ''.join(
        f'<col min="{indice}" max="{indice}" width="{ancho}" customWidth="1"/>'
        for indice, ancho in enumerate(
            anchos_base[:total_columnas],
            start=1,
        )
    )
    ultima_columna = _columna_excel(len(filas[0])) if filas and filas[0] else 'A'
    ultima_fila = max(len(filas), 1)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<dimension ref="A1:{ultima_columna}{ultima_fila}"/>'
        '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        '<sheetFormatPr defaultRowHeight="15"/>'
        f'<cols>{anchos}</cols>'
        f'<sheetData>{"".join(filas_xml)}</sheetData>'
        '<pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75" header="0.3" footer="0.3"/>'
        '</worksheet>'
    )


def _construir_celda_xml(referencia, valor):
    if isinstance(valor, int):
        return f'<c r="{referencia}"><v>{valor}</v></c>'

    texto = xml_escape(str(valor))
    return (
        f'<c r="{referencia}" t="inlineStr">'
        f'<is><t>{texto}</t></is>'
        '</c>'
    )


def _columna_excel(indice):
    letras = ''
    while indice:
        indice, resto = divmod(indice - 1, 26)
        letras = chr(65 + resto) + letras
    return letras


def construir_pdf(encabezados, filas, titulo, subtitulo):
    """Genera un PDF simple con todos los campos de cada socio."""
    ancho_pagina = 841.89
    alto_pagina = 595.28
    margen = 36
    ancho_columna = 58
    paginas = []
    pagina_actual = []
    y = alto_pagina - margen

    def agregar_pagina():
        nonlocal pagina_actual, y
        pagina_actual = []
        paginas.append(pagina_actual)
        y = alto_pagina - margen
        pagina_actual.append((margen, y, titulo, 'F2', 13))
        y -= 16
        pagina_actual.append((margen, y, subtitulo, 'F1', 9))
        y -= 18

    def asegurar_espacio(alto_necesario):
        if y - alto_necesario < margen:
            agregar_pagina()

    agregar_pagina()

    if not filas:
        pagina_actual.append(
            (margen, y, 'No hay socios para los filtros seleccionados.', 'F1', 9)
        )
    else:
        for numero, fila in enumerate(filas, start=1):
            registro = dict(zip(encabezados, fila))
            asegurar_espacio(120)
            nombre_socio = _nombre_socio_desde_registro(registro)
            estado_socio = registro.get('Estado actual', '')
            detalle_estado = f' ({estado_socio})' if estado_socio else ''
            encabezado = (
                f"{numero}. {registro['RUT']} - "
                f"{nombre_socio}{detalle_estado}"
            )
            pagina_actual.append((margen, y, encabezado, 'F2', 9))
            y -= 13

            campos = [(clave, registro[clave]) for clave in encabezados]
            for indice in range(0, len(campos), 2):
                izquierda = _envolver_pdf(campos[indice], ancho_columna)
                derecha = []
                if indice + 1 < len(campos):
                    derecha = _envolver_pdf(campos[indice + 1], ancho_columna)
                alto = max(len(izquierda), len(derecha), 1)
                asegurar_espacio(alto * 10 + 2)
                y_inicial = y
                for linea in izquierda:
                    pagina_actual.append((margen + 10, y, linea, 'F1', 7))
                    y -= 10
                y = y_inicial
                for linea in derecha:
                    pagina_actual.append((margen + 395, y, linea, 'F1', 7))
                    y -= 10
                y = min(y, y_inicial - (alto * 10))
            y -= 8

    total_paginas = len(paginas)
    for indice, pagina in enumerate(paginas, start=1):
        pagina.append(
            (
                ancho_pagina - margen - 80,
                margen - 12,
                f'Pagina {indice} de {total_paginas}',
                'F1',
                7,
            )
        )

    return _renderizar_pdf(paginas, ancho_pagina, alto_pagina)


def _envolver_pdf(campo, ancho):
    return textwrap.wrap(
        f'{campo[0]}: {campo[1]}',
        width=ancho,
        break_long_words=False,
        break_on_hyphens=False,
    ) or ['']


def _nombre_socio_desde_registro(registro):
    nombre = ' '.join(
        parte
        for parte in (
            registro.get('Nombre', ''),
            registro.get('Apellido paterno', ''),
            registro.get('Apellido materno', ''),
        )
        if parte
    )
    return nombre or registro['Usuario']


def _renderizar_pdf(paginas, ancho_pagina, alto_pagina):
    objetos = {
        1: b'<< /Type /Catalog /Pages 2 0 R >>',
        3: b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>',
        4: b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>',
    }
    ids_paginas = []

    for indice, lineas in enumerate(paginas):
        contenido_id = 5 + indice * 2
        pagina_id = 6 + indice * 2
        ids_paginas.append(pagina_id)
        stream = b''.join(
            _texto_pdf(x, y, texto, fuente, tamano)
            for x, y, texto, fuente, tamano in lineas
        )
        objetos[contenido_id] = (
            f'<< /Length {len(stream)} >>\nstream\n'.encode('ascii')
            + stream
            + b'endstream'
        )
        objetos[pagina_id] = (
            f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {ancho_pagina:.2f} {alto_pagina:.2f}] '
            f'/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> '
            f'/Contents {contenido_id} 0 R >>'
        ).encode('ascii')

    kids = ' '.join(f'{pagina_id} 0 R' for pagina_id in ids_paginas)
    objetos[2] = (
        f'<< /Type /Pages /Kids [{kids}] /Count {len(ids_paginas)} >>'
    ).encode('ascii')

    max_id = max(objetos)
    pdf = bytearray(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')
    offsets = [0] * (max_id + 1)
    for objeto_id in range(1, max_id + 1):
        offsets[objeto_id] = len(pdf)
        pdf.extend(f'{objeto_id} 0 obj\n'.encode('ascii'))
        pdf.extend(objetos[objeto_id])
        pdf.extend(b'\nendobj\n')

    inicio_xref = len(pdf)
    pdf.extend(f'xref\n0 {max_id + 1}\n'.encode('ascii'))
    pdf.extend(b'0000000000 65535 f \n')
    for offset in offsets[1:]:
        pdf.extend(f'{offset:010d} 00000 n \n'.encode('ascii'))
    pdf.extend(
        (
            f'trailer\n<< /Size {max_id + 1} /Root 1 0 R >>\n'
            f'startxref\n{inicio_xref}\n%%EOF'
        ).encode('ascii')
    )
    return bytes(pdf)


def _texto_pdf(x, y, texto, fuente, tamano):
    return (
        f'BT /{fuente} {tamano} Tf {x:.2f} {y:.2f} Td '.encode('ascii')
        + b'('
        + _escapar_texto_pdf(texto)
        + b') Tj ET\n'
    )


def _escapar_texto_pdf(texto):
    salida = bytearray()
    for byte in str(texto).encode('cp1252', errors='replace'):
        if byte in (40, 41, 92):
            salida.extend(b'\\')
            salida.append(byte)
        elif byte < 32 or byte > 126:
            salida.extend(f'\\{byte:03o}'.encode('ascii'))
        else:
            salida.append(byte)
    return bytes(salida)
