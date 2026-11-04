#!/bin/bash
# ========================================================
# Runner de ejecución para JobSeekerGA en macOS
# ========================================================

PROJECT_DIR="/Users/gabrieltrujillovallejo/Documents/GtrujilloMacDoc/GitHub/GitGa/Developer/Projects/JobSeekerGA"
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"

cd "$PROJECT_DIR" || exit 1

# Mantener despierto el sistema durante la ejecución
caffeinate -i "$VENV_PYTHON" main.py >> "$PROJECT_DIR/logs/cron.log" 2>&1
