#!/bin/bash
# ========================================================
# Runner de Pase Diario JobSeekerGA (macOS)
# Ejecuta 1 pase al día y termina liberando 100% de la RAM
# ========================================================

PROJECT_DIR="/Users/gabrieltrujillovallejo/Documents/GtrujilloMacDoc/GitHub/GitGa/Developer/Projects/JobSeekerGA"
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"

cd "$PROJECT_DIR" || exit 1
mkdir -p "$PROJECT_DIR/logs"

# Mantener despierto el sistema SOLO mientras dura la ejecución del pase (2-3 min)
export PYTHONUNBUFFERED=1
caffeinate -dims "$VENV_PYTHON" -u scripts/daily_pass.py "$@" >> "$PROJECT_DIR/logs/daily_run.log" 2>&1
