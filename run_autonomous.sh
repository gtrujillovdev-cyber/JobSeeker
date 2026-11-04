#!/bin/bash
# ========================================================
# Runner de ejecución autónoma para JobSeekerGA en macOS
# Funciona tanto en MacBook Air M4 como en MacBook Pro 2014
# ========================================================

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"

cd "$PROJECT_DIR" || exit 1
mkdir -p "$PROJECT_DIR/logs"

# Mantener despierto el sistema en modo headless
caffeinate -dimsu "$VENV_PYTHON" src/autonomous_scheduler.py >> "$PROJECT_DIR/logs/autonomous.log" 2>&1
