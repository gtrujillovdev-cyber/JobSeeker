#!/bin/bash
# Watchdog para JobSeekerGA bot - ejecutar via cron cada 5 min
# Crontab: */5 * * * * /Users/GabrielTrujilloVallejo/Documents/GtrujilloMacDoc/GitHub/GitGa/Developer/Projects/JobSeekerGA/deploy/watchdog.sh

BOT_DIR="/Users/GabrielTrujilloVallejo/Documents/GtrujilloMacDoc/GitHub/GitGa/Developer/Projects/JobSeekerGA"
PID_FILE="${BOT_DIR}/data/bot.pid"
LOG="${BOT_DIR}/logs/watchdog.log"
PYTHON="${BOT_DIR}/.venv/bin/python"

is_running() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            return 0
        fi
    fi
    # Fallback: buscar por nombre de proceso
    pgrep -f "main.py --bot" > /dev/null 2>&1
    return $?
}

if is_running; then
    exit 0
fi

# Bot caido - reiniciar
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Bot caido. Reiniciando..." >> "$LOG"

cd "$BOT_DIR"
PYTHONUNBUFFERED=1 nohup "$PYTHON" main.py --bot >> logs/bot_stdout.log 2>> logs/bot_stderr.log &
echo $! > "$PID_FILE"

sleep 3
if is_running; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Bot reiniciado OK (PID: $(cat $PID_FILE))" >> "$LOG"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: Bot no arranco tras reinicio" >> "$LOG"
fi
