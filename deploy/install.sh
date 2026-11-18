#!/bin/bash
# ============================================================
# install.sh — Instala los LaunchAgents de JobSeekerGA en este Mac.
# Corre LOCALMENTE en el Mac destino (mbp1 o workstation).
# Uso: bash deploy/install.sh
# ============================================================

set -e

INSTALL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PYTHON="${INSTALL_DIR}/.venv/bin/python3"
LAUNCHAGENTS_DIR="${HOME}/Library/LaunchAgents"
LOG_DIR="${INSTALL_DIR}/logs"

echo "======================================================"
echo " INSTALL JobSeekerGA LaunchAgents"
echo "======================================================"
echo " INSTALL_DIR : ${INSTALL_DIR}"
echo " HOME        : ${HOME}"
echo ""

# Verificar que el venv existe
if [ ! -f "${VENV_PYTHON}" ]; then
    echo "[!] No se encontro el venv en ${VENV_PYTHON}"
    echo "    Ejecuta primero: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
    exit 1
fi

# Crear directorios necesarios
echo "[1/4] Creando directorios..."
mkdir -p "${LOG_DIR}"
mkdir -p "${LAUNCHAGENTS_DIR}"
mkdir -p "${INSTALL_DIR}/data"
mkdir -p "${INSTALL_DIR}/assets/.browser_profiles"
echo "      OK"

# Generar e instalar plist del bot Telegram (daemon permanente)
echo "[2/4] Instalando com.jobseekerga.bot.plist..."
BOT_PLIST="${LAUNCHAGENTS_DIR}/com.jobseekerga.bot.plist"
launchctl unload "${BOT_PLIST}" 2>/dev/null || true

cat > "${BOT_PLIST}" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.jobseekerga.bot</string>
    <key>ProgramArguments</key>
    <array>
        <string>${VENV_PYTHON}</string>
        <string>${INSTALL_DIR}/main.py</string>
        <string>--bot</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${INSTALL_DIR}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/bot_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/bot_stderr.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
    </dict>
    <key>ProcessType</key>
    <string>Background</string>
    <key>Nice</key>
    <integer>10</integer>
    <key>ThrottleInterval</key>
    <integer>10</integer>
</dict>
</plist>
PLIST_EOF

launchctl load "${BOT_PLIST}" 2>/dev/null || echo "      (Aviso: LaunchAgent no cargado en sesión SSH headless; el watchdog de cron gestiona el proceso)"
echo "      OK -> ${BOT_PLIST}"

# Generar e instalar plist del session_keeper (latido diario 08:00)
echo "[3/4] Instalando com.jobseekerga.session_keeper.plist..."
SK_PLIST="${LAUNCHAGENTS_DIR}/com.jobseekerga.session_keeper.plist"
launchctl unload "${SK_PLIST}" 2>/dev/null || true

sed "s|__INSTALL_DIR__|${INSTALL_DIR}|g" \
    "${INSTALL_DIR}/deploy/com.jobseekerga.session_keeper.plist" \
    > "${SK_PLIST}"

launchctl load "${SK_PLIST}" 2>/dev/null || true
echo "      OK -> ${SK_PLIST}"

# Verificar
echo "[4/4] Verificando servicios..."
sleep 2

BOT_STATUS=$(launchctl list | grep "com.jobseekerga.bot" | awk '{print $1}')
SK_STATUS=$(launchctl list | grep "com.jobseekerga.session_keeper" | awk '{print $1}')

if [ -n "${BOT_STATUS}" ]; then
    echo "      [OK] com.jobseekerga.bot    cargado (PID/status: ${BOT_STATUS})"
else
    echo "      [!!] com.jobseekerga.bot    NO aparece en launchctl list"
fi

if [ -n "${SK_STATUS}" ]; then
    echo "      [OK] com.jobseekerga.session_keeper cargado (PID/status: ${SK_STATUS})"
else
    echo "      [!!] com.jobseekerga.session_keeper NO aparece en launchctl list"
fi

echo ""
echo "======================================================"
echo " INSTALACION COMPLETADA"
echo "======================================================"
echo ""
echo "Comandos utiles:"
echo "  # Ver bot en tiempo real"
echo "  tail -f ${LOG_DIR}/bot_stdout.log"
echo ""
echo "  # Forzar heartbeat ahora (sin esperar las 08:00)"
echo "  launchctl start com.jobseekerga.session_keeper"
echo ""
echo "  # Logs del session_keeper"
echo "  tail -f ${LOG_DIR}/session_keeper.log"
echo ""
echo "  # Reiniciar bot"
echo "  launchctl unload ${BOT_PLIST} && launchctl load ${BOT_PLIST}"
echo ""
echo "  # Desinstalar todo"
echo "  launchctl unload ${BOT_PLIST} ${SK_PLIST} && rm ${BOT_PLIST} ${SK_PLIST}"
echo ""
