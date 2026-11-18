#!/bin/bash
# ============================================================
# Deploy de JobSeekerGA al MacBook Pro Intel (produccion)
# Uso: ./deploy/deploy.sh
# ============================================================

set -e

REMOTE_HOST="100.108.212.124"
REMOTE_USER="GabrielTrujilloVallejo"
REMOTE_DIR="/Users/${REMOTE_USER}/Developer/Projects/JobSeekerGA"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLIST_NAME="com.jobseekerga.bot"
PLIST_REMOTE="/Users/${REMOTE_USER}/Library/LaunchAgents/${PLIST_NAME}.plist"

echo "======================================"
echo " DEPLOY JOBSEEKERGA -> MacBook Pro"
echo "======================================"
echo "Host:   ${REMOTE_HOST}"
echo "Ruta:   ${REMOTE_DIR}"
echo ""

# 1. Detener servicio anterior si existe
echo "[1/5] Deteniendo servicio anterior..."
ssh "${REMOTE_HOST}" "launchctl unload '${PLIST_REMOTE}' 2>/dev/null || true; pkill -f 'main.py --bot' 2>/dev/null || true"

# 2. Crear directorio remoto y sincronizar archivos
echo "[2/5] Sincronizando archivos..."
ssh "${REMOTE_HOST}" "mkdir -p '${REMOTE_DIR}'"

rsync -avz --delete \
    --exclude='.venv/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='.DS_Store' \
    --exclude='assets/.browser_profiles/' \
    --exclude='output/' \
    --exclude='logs/' \
    --exclude='data/' \
    --exclude='.env' \
    --exclude='.pytest_cache/' \
    --exclude='.git/' \
    "${LOCAL_DIR}/" "${REMOTE_HOST}:${REMOTE_DIR}/"

# 3. Setup venv + dependencias en remoto
echo "[3/5] Instalando dependencias..."
ssh "${REMOTE_HOST}" "
    cd '${REMOTE_DIR}'
    if [ ! -d .venv ]; then
        /usr/local/bin/python3.13 -m venv .venv
    fi
    .venv/bin/pip install -q -r requirements.txt
    .venv/bin/python -m playwright install chromium 2>/dev/null || true
    mkdir -p data output/screenshots logs assets/.browser_profiles
"

# 4. Instalar LaunchAgents en remoto via install.sh
echo "[4/5] Instalando LaunchAgents (bot + session_keeper) y watchdog..."
ssh "${REMOTE_HOST}" "bash '${REMOTE_DIR}/deploy/install.sh'"
ssh "${REMOTE_HOST}" "bash '${REMOTE_DIR}/deploy/watchdog.sh'"

# 5. Verificar bot en tiempo real
echo "[5/5] Verificando..."
sleep 3
ssh "${REMOTE_HOST}" "
    pgrep -fl 'main.py --bot' || echo 'Bot no visible aún, el cron lo levantará en <5 min'
    tail -5 '${REMOTE_DIR}/logs/bot_stdout.log' 2>/dev/null || echo '(log vacio, el bot acaba de arrancar)'
"

echo ""
echo "======================================"
echo " DEPLOY COMPLETADO"
echo "======================================"
echo ""
echo "Comandos utiles:"
echo "  # Logs en tiempo real"
echo "  ssh ${REMOTE_HOST} 'tail -f ${REMOTE_DIR}/logs/bot_stdout.log'"
echo ""
echo "  # Forzar heartbeat de sesion ahora"
echo "  ssh ${REMOTE_HOST} 'launchctl start com.jobseekerga.session_keeper'"
echo ""
echo "  # Logs del session_keeper"
echo "  ssh ${REMOTE_HOST} 'tail -f ${REMOTE_DIR}/logs/session_keeper.log'"
echo ""
echo "  # Reiniciar bot"
echo "  ssh ${REMOTE_HOST} 'launchctl unload ~/Library/LaunchAgents/com.jobseekerga.bot.plist && launchctl load ~/Library/LaunchAgents/com.jobseekerga.bot.plist'"
