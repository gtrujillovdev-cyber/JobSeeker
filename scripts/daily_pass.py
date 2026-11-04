#!/usr/bin/env python3
"""
Pase diario autónomo de JobSeekerGA para macOS.
Diseñado para ejecutarse 1 sola vez al día (vía cron o al encender el Mac).
1. Comprueba si ya se ha ejecutado hoy (si es así, sale inmediatamente en 0.05s).
2. Escanea ofertas Junior / Prácticas IT en Sevilla.
3. Busca y envía solicitudes de conexión a recruiters/RRHH de esas empresas (máx 5/día).
4. Genera y publica 1 artículo técnico de proyecto rotativo acorde a tu CV DAM/Ciberseguridad.
5. Envía reporte completo a tu bot de Telegram (@JobGaBot).
6. Termina y libera el 100% de los recursos.
"""

import sys
import json
import time
import random
from pathlib import Path
from datetime import datetime, date

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from config import (
    DATA_DIR, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    MAX_DAILY_CONNECTIONS
)
from src.job_scanner import JobScanner
from src.engagement_engine import EngagementEngine
from src.anti_ban import AntiBanValidator
from src.dev_diary import DevDiaryGenerator
from src.resource_governor import ResourceGovernor
from config import BROWSER_PROFILE_DIR
import requests

LAST_RUN_FILE = DATA_DIR / "last_daily_run.json"

def notify_telegram(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "Markdown"
            },
            timeout=15
        )
    except Exception as e:
        print(f"[DailyPass] Error notificando a Telegram: {e}")

def has_run_today() -> bool:
    if not LAST_RUN_FILE.exists():
        return False
    try:
        data = json.loads(LAST_RUN_FILE.read_text())
        return data.get("last_run_date") == date.today().isoformat()
    except Exception:
        return False

def mark_run_today(summary: dict):
    try:
        payload = {
            "last_run_date": date.today().isoformat(),
            "timestamp": datetime.now().isoformat(),
            "summary": summary
        }
        LAST_RUN_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"[DailyPass] Error guardando registro de ejecución: {e}")

def run_daily_pass(force: bool = False):
    today_str = date.today().isoformat()
    now_time = datetime.now().strftime("%H:%M")

    if not force and has_run_today():
        print(f"[{now_time}] [DailyPass] Ya se ha ejecutado hoy ({today_str}). Nada pendiente.")
        return

    print(f"\n=======================================================")
    print(f"🚀 INICIANDO PASE DIARIO JOBSEEKERGA ({today_str} {now_time})")
    print(f"=======================================================")

    notify_telegram(
        f"🚀 *JobSeekerGA: Pase diario iniciado*\n"
        f"📅 Fecha: `{today_str}` | Hora: `{now_time}`\n"
        f"Buscando ofertas Junior en Sevilla y conectando con RRHH..."
    )

    summary = {
        "date": today_str,
        "jobs_found": 0,
        "connections_sent": 0,
        "connection_targets": [],
        "post_published": None,
        "status": "success"
    }

    # 1. Escaneo de ofertas Junior / Prácticas en Sevilla
    try:
        print("\n[1/3] 📡 Escaneando ofertas en Sevilla...")
        jobs = JobScanner.scan()
        summary["jobs_found"] = len(jobs)
        print(f"[✓] {len(jobs)} ofertas encontradas.")
    except Exception as e:
        print(f"[!] Error en escaneo de ofertas: {e}")

    # 2. Conexiones con RRHH / Recruiter de empresas target
    try:
        print("\n[2/3] 🤝 Conectando con responsables de RRHH de las empresas...")
        actions = EngagementEngine.propose_actions(max_actions=MAX_DAILY_CONNECTIONS)
        conn_actions = [a for a in actions if a.get("type") == "connection"]

        if conn_actions:
            print(f"[*] Ejecutando {len(conn_actions)} solicitudes de conexión...")
            results = EngagementEngine._execute_actions(conn_actions)
            for r in results:
                target_str = f"{r.get('target_name', 'Recruiter')} ({r.get('target_company')})"
                status = r.get("status")
                summary["connection_targets"].append({"target": target_str, "status": status})
                if status == "success":
                    summary["connections_sent"] += 1
            print(f"[✓] {summary['connections_sent']} conexiones enviadas con éxito.")
        else:
            print("[*] No hay cupo de conexiones hoy (límite anti-ban protegido).")
    except Exception as e:
        print(f"[!] Error en conexiones con RRHH: {e}")

    # 3. Preparación del borrador del Diario de Desarrollo (SIEMPRE con confirmación previa en Telegram)
    today_records = [
        r for r in AntiBanValidator.get_records()
        if r.get("date", "").startswith(today_str) and r.get("status") == "success"
    ]
    if not today_records and AntiBanValidator.check_daily_limit():
        try:
            print("\n[3/3] 📓 Generando borrador del Diario de Desarrollo y enviándolo a Telegram para tu aprobación...")
            diary_record = DevDiaryGenerator.prepare_daily_diary_draft(wait_approval=True)
            if diary_record:
                summary["post_published"] = (
                    f"{diary_record['display_name']} [{diary_record.get('status', 'pendiente de confirmación')}]"
                )
                print(f"[✓] Borrador gestionado: {summary['post_published']}")
        except Exception as e:
            print(f"[!] Error preparando Diario de Desarrollo: {e}")
    else:
        if today_records:
            summary["post_published"] = today_records[-1].get("project_name", "Publicado hoy")
        print("[*] Ya se ha publicado la entrada del Diario de Desarrollo de hoy.")

    # Guardar estado de hoy
    mark_run_today(summary)

    # 4. Limpieza exquisita de residuos, temporales y liberación de memoria
    try:
        clean_stats = ResourceGovernor.run_full_cleanup(profile_dir=BROWSER_PROFILE_DIR)
        print(f"[✓] Limpieza exquisita completada: {clean_stats}")
    except Exception as e_clean:
        print(f"[!] Aviso en autorregulación de memoria: {e_clean}")

    # 5. Notificación final consolidada a Telegram
    targets_lines = ""
    for t in summary["connection_targets"]:
        icon = "✅" if t.get("status") == "success" else "⚠️"
        targets_lines += f"  {icon} {t.get('target')} [{t.get('status')}]\n"

    final_msg = (
        f"🏁 *Pase Diario Completado*\n"
        f"📅 `{today_str}` | `{datetime.now().strftime('%H:%M')}`\n\n"
        f"📊 *Resumen de actividad:*\n"
        f"• Ofertas detectadas en Sevilla: *{summary['jobs_found']}*\n"
        f"• Solicitudes a RRHH enviadas: *{summary['connections_sent']}*\n"
    )
    if targets_lines:
        final_msg += f"\n*Detalle de contactos:*\n{targets_lines}"

    if summary["post_published"]:
        final_msg += f"\n📝 *Post publicado en LinkedIn:*\n_{summary['post_published']}_\n"

    final_msg += f"\n💤 *Bot finalizado por hoy. Todos los procesos liberados.*"

    notify_telegram(final_msg)
    print("\n[✓] Pase diario completado con éxito. Reporte enviado a Telegram @JobGaBot.\n")

if __name__ == "__main__":
    force_run = "--force" in sys.argv
    run_daily_pass(force=force_run)
