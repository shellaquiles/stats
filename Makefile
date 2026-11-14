# ── CONFIGURACIÓN DEL ENTORNO & PYTHON ─────────────────────────────────────────
VENV_DIR  := .venv
VENV_BIN  := $(shell if [ -d "$(VENV_DIR)/bin" ]; then echo "$(VENV_DIR)/bin/"; fi)
PYTHON    := $(VENV_BIN)python3
PIP       := $(VENV_BIN)pip
PORT      := 8000

# ── ESTILOS & COLORES ANSI ───────────────────────────────────────────────────
BOLD      := \033[1m
DIM       := \033[2m
RESET     := \033[0m
BLUE      := \033[38;5;33m
EMERALD   := \033[38;5;42m
AMBER     := \033[38;5;214m
CYAN      := \033[38;5;51m
RED       := \033[38;5;196m
GRAY      := \033[38;5;244m

.PHONY: all help dev sync preview serve setup venv clean

all: help

## ── AYUDA & COMANDOS ──────────────────────────────────────────────────────────
help:
	@printf "\n"
	@printf "  $(BOLD)$(EMERALD)shell$(RESET)$(BOLD)aquiles$(RESET)$(RED).org$(RESET) $(DIM)• Telemetry & Stats Engine$(RESET)\n"
	@printf "  $(GRAY)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(RESET)\n"
	@printf "  Dashboard de métricas públicas de GitHub: repositorios, tráfico,\n"
	@printf "  colaboradores y tarjeta social generada automáticamente en CI/CD.\n"
	@printf "  $(GRAY)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(RESET)\n"
	@printf "  $(BOLD)Uso:$(RESET) make $(CYAN)<comando>$(RESET)\n\n"
	@printf "  $(BOLD)Comandos Principales:$(RESET)\n"
	@printf "    $(CYAN)make dev$(RESET)       $(GRAY)→$(RESET) Sincroniza métricas y levanta servidor en http://localhost:$(PORT)\n"
	@printf "    $(CYAN)make sync$(RESET)      $(GRAY)→$(RESET) Extrae telemetría de GitHub y genera $(BOLD)data.json$(RESET)\n"
	@printf "    $(CYAN)make preview$(RESET)   $(GRAY)→$(RESET) Genera tarjeta para redes sociales ($(BOLD)og-preview.png$(RESET))\n"
	@printf "    $(CYAN)make serve$(RESET)     $(GRAY)→$(RESET) Inicia servidor HTTP local en puerto $(PORT)\n\n"
	@printf "  $(BOLD)Entorno & Mantenimiento:$(RESET)\n"
	@printf "    $(CYAN)make setup$(RESET)     $(GRAY)→$(RESET) Crea entorno virtual e instala Playwright/Chromium\n"
	@printf "    $(CYAN)make clean$(RESET)     $(GRAY)→$(RESET) Limpia artefactos generados ($(BOLD)data.json$(RESET), $(BOLD)og-preview.png$(RESET), cachés)\n"
	@printf "  $(GRAY)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(RESET)\n\n"

## ── FLUJOS DE DESARROLLO ─────────────────────────────────────────────────────
dev: sync serve

sync:
	@printf "  $(BLUE)📡 Extrayendo telemetría de GitHub vía gh CLI...$(RESET)\n"
	@$(PYTHON) scripts/update_metrics.py
	@printf "  $(EMERALD)✔ data.json actualizado correctamente.$(RESET)\n"

preview:
	@printf "  $(AMBER)📸 Renderizando tarjeta de alta resolución (2x Retina)...$(RESET)\n"
	@$(PYTHON) scripts/generate_preview.py

serve:
	@printf "\n  $(BOLD)$(EMERALD)🚀 Servidor local activo:$(RESET) $(CYAN)http://localhost:$(PORT)$(RESET)\n"
	@printf "  $(DIM)   Presiona Ctrl+C para detener el servidor.$(RESET)\n\n"
	@$(PYTHON) -m http.server $(PORT)

## ── SETUP & ENTORNO VIRTUAL ──────────────────────────────────────────────────
setup: venv
	@printf "  $(BLUE)📦 Instalando dependencias de Playwright...$(RESET)\n"
	@$(PIP) install --quiet playwright
	@$(VENV_BIN)playwright install chromium
	@printf "  $(EMERALD)✔ Entorno virtual y navegadores listos en $(VENV_DIR).$(RESET)\n"

venv:
	@if [ ! -d "$(VENV_DIR)" ]; then \
		printf "  $(BLUE)⚙️ Creando entorno virtual en $(VENV_DIR)...$(RESET)\n"; \
		python3.11 -m venv $(VENV_DIR) 2>/dev/null || python3 -m venv $(VENV_DIR); \
	fi

clean:
	@rm -f data.json og-preview.png
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@printf "  $(EMERALD)🧹 Artefactos temporales y cachés eliminados.$(RESET)\n"
