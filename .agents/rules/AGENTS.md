# Reglas — GitHub Telemetry Engine

## 1. Arquitectura (SRP)
- **`scripts/update_metrics.py`**: Extractor puro. Filtra `--source` (`isFork: false`), auto-detecta `User`/`Org` y exporta `data.json`. Prohibido mutar HTML.
- **`index.html`**: Hidratación reactiva con `fetch('data.json')`. Cero datos hardcodeados. Tabla sortable interactiva.
- **`scripts/generate_preview.py`**: Renderiza `og-preview.png` (2400x1260 px) vía Playwright sobre `templates/share.html`.
- **Despliegue**: Solo a rama aislada `gh-pages`. `main`/`dev` sin commits de bots.

## 2. Estilo Visual (Swiss Minimalist)
- **Colores planos**: `#1e3a8a`, `#046a38`, `#b45309`, `#09090b`, `#f8fafc`. Sin degradados.
- **Bordes 1px**: `border-zinc-300` / `border-zinc-200`.
- **Tipografía**: `Inter` (copies) + `JetBrains Mono` (métricas).
- **Branding**: Logo compacto `{{shellaquiles.org}}` y footer fijo con atribución a Shellaquiles.

## 3. Telemetría y Versión
- **Bots**: Excluir cuentas `[bot]` y `actions-user`.
- **Antigüedad**: Computada automáticamente desde el repo más antiguo.
- **Versión**: `VERSION` es la fuente única de verdad. Sincronizar en `CHANGELOG.md`.
