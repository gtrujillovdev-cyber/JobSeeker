#!/bin/bash
# ============================================================
# Deploy de JobSeekerGA al MacBook Pro Intel (produccion)
# Uso: ./deploy/deploy.sh
# ============================================================

set -e

REMOTE_HOST="100.108.212.124"
REMOTE_USER="GabrielTrujilloVallejo"
REMOTE_DIR="/Users/${REMOTE_USER}/Documents/GtrujilloMacDoc/GitHub/GitGa/Developer/Projects/JobSeekerGA"
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
ssh "${REMOTE_HOST}" "launchctl unload '${PLIST_REMOTE}' 2>/dev/null || true"

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
    --exclude='data/published_history.json' \
    --exclude='data/engagement_history.json' \
    --exclude='data/job_scan_results.json' \
    --exclude='data/pending_drafts.json' \
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

# 4. Copiar plist e iniciar servicio
echo "[4/5] Instalando servicio launchd..."
scp "${LOCAL_DIR}/deploy/${PLIST_NAME}.plist" "${REMOTE_HOST}:${PLIST_REMOTE}"
ssh "${REMOTE_HOST}" "launchctl load '${PLIST_REMOTE}'"

# 5. Verificar
echo "[5/5] Verificando..."
sleep 3
ssh "${REMOTE_HOST}" "
    if launchctl list | grep -q '${PLIST_NAME}'; then
        PID=\$(launchctl list | grep '${PLIST_NAME}' | awk '{print \$1}')
        echo '[OK] Bot activo (PID: '\${PID}')'
    else
        echo '[ERROR] No arranco. Revisa:'
        echo '  cat ${REMOTE_DIR}/logs/bot_stderr.log'
        exit 1
    fi
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
echo "  # Reiniciar"
echo "  ssh ${REMOTE_HOST} 'launchctl unload ${PLIST_REMOTE} && launchctl load ${PLIST_REMOTE}'"
echo ""
echo "  # Detener"
echo "  ssh ${REMOTE_HOST} 'launchctl unload ${PLIST_REMOTE}'"
