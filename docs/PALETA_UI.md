# Paleta UI

Analisis base desde `static/images/logo.png`:

- Color dominante del logo: `#D9C0AA`
- Variaciones detectadas: `#D8C1A9`, `#E1D3C3`, `#F2EBE1`
- El logo usa una familia calida beige/arena, por lo que conviene usarla como identidad visual y no como unico color de interfaz.

## Paleta recomendada

| Uso | Nombre | HEX | Notas |
| --- | --- | --- | --- |
| Primario UI | Verde San Ramon | `#2F5D50` | Botones principales, navbar, links activos. Contrasta bien con fondos claros. |
| Primario hover | Verde profundo | `#24483E` | Hover/focus de acciones principales. |
| Secundario | Teal operativo | `#3C7A73` | Estados informativos, acciones secundarias, iconos de modulos. |
| Marca logo | Arena logo | `#D9C0AA` | Acentos de marca, bordes destacados, fondos suaves. |
| Marca suave | Arena clara | `#F2EBE1` | Paneles destacados, chips, bloques informativos. |
| Acento | Oro sobrio | `#C9964A` | Alertas no criticas, indicadores de atencion, detalles puntuales. |
| Texto principal | Tinta | `#24313A` | Titulos y texto de alta prioridad. |
| Texto secundario | Gris pizarra | `#5D6B74` | Ayudas, labels secundarios, metadatos. |
| Fondo app | Fondo calido | `#F7F4EF` | Background general. |
| Superficie | Blanco calido | `#FFFCF8` | Cards, formularios, tablas. |
| Borde | Borde arena | `#E3D7CA` | Bordes suaves y separadores. |
| Error | Rojo controlado | `#B42318` | Errores y acciones destructivas. |
| Exito | Verde exito | `#2E7D5B` | Confirmaciones y estados activos. |

## Tokens CSS sugeridos

```css
:root {
    --color-primary: #2f5d50;
    --color-primary-hover: #24483e;
    --color-secondary: #3c7a73;
    --color-logo-sand: #d9c0aa;
    --color-logo-sand-light: #f2ebe1;
    --color-accent: #c9964a;
    --color-text: #24313a;
    --color-text-muted: #5d6b74;
    --color-bg: #f7f4ef;
    --color-surface: #fffcf8;
    --color-border: #e3d7ca;
    --color-danger: #b42318;
    --color-success: #2e7d5b;
}
```

## Uso recomendado

- Usar `#2F5D50` como color principal de navegacion y acciones.
- Reservar `#D9C0AA` para detalles de marca, no para botones principales.
- Mantener tablas y formularios sobre `#FFFCF8` para lectura limpia.
- Usar `#F7F4EF` como fondo general para que el sitio conecte con el logo sin quedar monocromatico.
- Usar `#C9964A` con moderacion para avisos o llamados de atencion.
