#!/usr/bin/env bash
# ==============================================================================
# JobSeekerGA - Headless Watchdog & Autonomous Daemon Manager (Armonizado con GTAVIHub en mbp1)
# Crontab recomendado (fuera de ~/Documents para evitar bloqueos TCC de macOS):
# 2-59/5 * * * * /Users/GabrielTrujilloVallejo/Developer/Projects/JobSeekerGA/deploy/watchdog.sh
# ==============================================================================
set -e

export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
export PLAYWRIGHT_NODEJS_PATH="/Users/GabrielTrujilloVallejo/tools/node20/bin/node"
export CHROMIUM_EXECUTABLE_PATH="/Users/GabrielTrujilloVallejo/tools/chromium_mac11/chrome-mac/Chromium.app/Contents/MacOS/Chromium"

BOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${BOT_DIR}/.venv/bin/python"
LOG_DIR="${BOT_DIR}/logs"
HEARTBEAT="${BOT_DIR}/data/heartbeat.txt"
PID_FILE="${BOT_DIR}/data/bot.pid"

mkdir -p "$LOG_DIR"

# 1. Comprobación de Heartbeat (detectar si el proceso está congelado/pillado)
NOW=$(date +%s)
if [ -f "$HEARTBEAT" ] && pgrep -f "main.py --bot" >/dev/null 2>&1; then
    LAST_BEAT=$(cat "$HEARTBEAT" 2>/dev/null || echo 0)
    DIFF=$((NOW - LAST_BEAT))
    # Si han pasado más de 10 minutos (600 s) sin latido, matar proceso colgado y Chromium huérfanos
    if [ "$DIFF" -gt 600 ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] [Watchdog] Heartbeat caducado (${DIFF}s > 600s). Bot pillado. Matando y reiniciando..." >> "$LOG_DIR/watchdog.log"
        pkill -9 -f "main.py --bot" 2>/dev/null || true
        pkill -9 -f "chromium_mac11.*--headless" 2>/dev/null || true
        sleep 1
    fi
fi

# 2. Asegurar que el bot + scheduler esté siempre corriendo (Auto-healing 24/7 con prioridad nice 15 -> estado SN)
if ! pgrep -f "main.py --bot" >/dev/null 2>&1; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [Watchdog] Bot de JobSeekerGA no detectado o tras reinicio. Arrancando con nice -n 15..." >> "$LOG_DIR/watchdog.log"
    cd "$BOT_DIR"
    PYTHONUNBUFFERED=1 nohup /usr/bin/nice -n 15 "$PYTHON" -u "$BOT_DIR/main.py" --bot >> "$LOG_DIR/bot_stdout.log" 2>> "$LOG_DIR/bot_stderr.log" &
    echo $! > "$PID_FILE"
fi
