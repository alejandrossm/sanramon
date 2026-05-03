# Django Chart Optimization - San Ramón Project

## Gráfico: "Estado de asistencia de socios"

### Problema Original

Gráfico HTML/CSS con barras verticales que se veían feas:

- Barras casi invisibles con valores bajos (< 10%)
- Espaciado pobre en el contenedor
- Sin transiciones suaves
- Complejo de mantener con CSS puro

### Solución Implementada: Chart.js Local

#### Instalación

```bash
# No requiere npm en runtime ni en produccion.
# Chart.js queda versionado en: static/vendor/chart.js/chart.min.js
```

#### Archivos Modificados

**1. `templates/base.html`**

- Agregado script local: `<script src="{% static 'vendor/chart.js/chart.min.js' %}"></script>`

**2. `usuarios/templates/usuarios/dashboard.html`**

- Reemplazado: Divs HTML/CSS → Canvas elemento
- Agregado: Script JavaScript con configuración Chart.js
- Tipo gráfico: Barras horizontales (`indexAxis: 'y'`)
- Colores: Integrados con paleta del tema (#2f5d50, #2e7d5b, #c9964a, #b42318)
- Efectos: Hover effects, tooltips personalizados, animaciones suaves
- Responsive: Altura dinámica (300px base)

**3. `.gitignore`**

- Agregado: `node_modules/`, `package-lock.json`, `npm-debug.log`

#### Ventajas de Chart.js

✅ Librería ligera (~208KB minificado)
✅ Animaciones suaves nativas
✅ Responsive automático
✅ Accesibilidad integrada
✅ Extensible para futuros gráficos (líneas, pie, etc.)
✅ Funciona 100% local (sin CDN)

#### Deployment en PythonAnywhere

- Solo sube: `static/` con archivos compilados
- No necesita: npm, node_modules, Python tools
- No requiere: node_modules en producción
- `package.json` no declara dependencias npm; existe solo para evitar falsos positivos si se ejecuta `npm list`.

### Notas

- Chart.js está bajo `static/vendor/chart.js/` (no en node_modules)
- Dashboard data viene de `obtener_resumen_estado_asistencia_socios()` en views.py
- Template usa contexto: `estado_asistencia_socios_items`, `estado_asistencia_socios_total`

### Fecha de implementación

2 de Mayo de 2026
