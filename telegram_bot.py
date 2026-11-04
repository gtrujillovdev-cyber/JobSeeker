"""
Bot de Telegram centralizado para JobSeekerGA.
Daemon de long-polling que controla todo el pipeline desde el movil:
  /status   - Dashboard de actividad del dia
  /scan     - Escanear ofertas de empleo en LinkedIn Jobs
  /summary  - Resumen de ofertas + skills demandadas + empresas target
  /publish  - Generar borrador de post para LinkedIn (con aprobacion)
  /engage   - Proponer plan de networking activo (con aprobacion)
  /limits   - Ver limites anti-ban restantes
  /help     - Lista de comandos
"""

import time
import json
import threading
import traceback
from datetime import datetime, date
from pathlib import Path
from typing import Optional, Dict, Any

import requests as http

from config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, DATA_DIR,
    MAX_DAILY_POSTS, MAX_DAILY_CONNECTIONS, MAX_DAILY_COMMENTS, MAX_DAILY_REACTIONS,
    JOB_SEARCH_KEYWORDS, JOB_SEARCH_LOCATION
)
from src.anti_ban import AntiBanValidator
from src.job_scanner import JobScanner
from src.copy_generator import CopyGenerator
from src.project_capturer import ProjectCapturer
from src.linkedin_publisher import LinkedInPublisher
from src.engagement_engine import EngagementEngine
from src.telegram_reviewer import TelegramReviewer, _get_drafts, _save_drafts
from src.dev_diary import DevDiaryGenerator
from src.easy_apply import EasyApplyEngine
from src.resource_governor import ResourceGovernor
from config import BROWSER_PROFILE_DIR

# Almacen temporal de acciones de engagement y candidaturas Easy Apply pendientes de aprobacion
_pending_engagement_actions = []
_pending_easy_apply_jobs = []


class TelegramBot:
    """Bot de Telegram con long-polling para controlar JobSeekerGA."""

    BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

    # --- API helpers ---

    @classmethod
    def _send(cls, text: str, parse_mode: str = "Markdown",
              reply_markup: Optional[dict] = None) -> Optional[dict]:
        payload: Dict[str, Any] = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text[:4096],
            "parse_mode": parse_mode
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            r = http.post(f"{cls.BASE_URL}/sendMessage", json=payload, timeout=15)
            return r.json() if r.status_code == 200 else None
        except Exception:
            return None

    @classmethod
    def _send_photo(cls, photo_path: Path, caption: str = "",
                    reply_markup: Optional[dict] = None) -> Optional[dict]:
        data: Dict[str, Any] = {
            "chat_id": TELEGRAM_CHAT_ID,
            "caption": caption[:1024],
            "parse_mode": "Markdown"
        }
        if reply_markup:
            data["reply_markup"] = json.dumps(reply_markup)
        try:
            with open(photo_path, "rb") as f:
                r = http.post(f"{cls.BASE_URL}/sendPhoto", data=data,
                              files={"photo": f}, timeout=20)
            return r.json() if r.status_code == 200 else None
        except Exception:
            return None

    @classmethod
    def _answer_callback(cls, callback_id: str, text: str = "") -> None:
        try:
            http.post(f"{cls.BASE_URL}/answerCallbackQuery",
                      json={"callback_query_id": callback_id, "text": text}, timeout=10)
        except Exception:
            pass

    @classmethod
    def _remove_buttons(cls, chat_id: int, message_id: int) -> None:
        try:
            http.post(f"{cls.BASE_URL}/editMessageReplyMarkup",
                      json={"chat_id": chat_id, "message_id": message_id,
                            "reply_markup": {"inline_keyboard": []}}, timeout=10)
        except Exception:
            pass

    # --- Comando handlers ---

    @classmethod
    def cmd_start(cls):
        cls._send(
            "*JobSeekerGA Bot*\n\n"
            "Control centralizado de tu pipeline de marca personal en LinkedIn.\n\n"
            "Usa /help para ver los comandos disponibles."
        )

    @classmethod
    def cmd_help(cls):
        cls._send(
            "*Comandos disponibles:*\n\n"
            "/status - Dashboard de actividad del dia\n"
            "/scan - Escanear ofertas en LinkedIn Jobs\n"
            "/scan `keywords` - Escanear con keywords custom\n"
            "/summary - Resumen de ofertas + ranking skills\n"
            "/publish `NombreProyecto` - Generar borrador de post\n"
            "/engage - Proponer plan de engagement (5 conexiones RRHH)\n"
            "/apply - Buscar vacantes Solicitud Sencilla + CV adaptado\n"
            "/history - Historial completo: posts, contactos y candidaturas\n"
            "/limits - Ver limites anti-ban restantes\n"
            "/drafts - Ver borradores pendientes\n"
            "/help - Esta ayuda"
        )

    @classmethod
    def cmd_status(cls):
        today = date.today().isoformat()

        # Posts publicados hoy
        pub_records = AntiBanValidator.get_records()
        today_posts = [r for r in pub_records
                       if r.get("date", "").startswith(today) and r.get("status") == "success"]

        # Engagement de hoy
        eng_summary = AntiBanValidator.get_today_engagement_summary()

        # Ofertas escaneadas hoy
        today_jobs = JobScanner.get_today_results()

        # Borradores pendientes
        drafts = _get_drafts()
        pending = [d for d in drafts.values() if d.get("status") == "pending"]

        lines = [
            f"*DASHBOARD - {today}*\n",
            f"Posts publicados: {len(today_posts)}/{MAX_DAILY_POSTS}",
            f"Ofertas escaneadas: {len(today_jobs)}",
            f"Borradores pendientes: {len(pending)}",
            ""
        ]

        if eng_summary:
            lines.append("*Engagement:*")
            for action, count in eng_summary.items():
                limit = {"comment": MAX_DAILY_COMMENTS,
                         "connection": MAX_DAILY_CONNECTIONS,
                         "reaction": MAX_DAILY_REACTIONS}.get(action, "?")
                lines.append(f"  {action}: {count}/{limit}")
        else:
            lines.append("Engagement: sin actividad hoy")

        if today_jobs:
            top_companies = list({j["company"] for j in today_jobs})[:5]
            lines.append(f"\n*Empresas detectadas:* {', '.join(top_companies)}")

        cls._send("\n".join(lines))

    @classmethod
    def cmd_scan(cls, custom_keywords: Optional[str] = None):
        keywords = custom_keywords or JOB_SEARCH_KEYWORDS
        cls._send(f"Escaneando ofertas: `{keywords}` en `{JOB_SEARCH_LOCATION}`\nEsto puede tardar ~30 seg...")

        def _run():
            try:
                jobs = JobScanner.scan(keywords=keywords)
                if jobs:
                    summary = JobScanner.format_summary(jobs)
                    cls._send(f"*SCAN COMPLETADO*\n\n{summary}")
                else:
                    cls._send("No se encontraron ofertas. Comprueba la sesion de LinkedIn (/status).")
            except Exception as e:
                cls._send(f"Error durante el scan:\n`{str(e)[:500]}`")

        threading.Thread(target=_run, daemon=True).start()

    @classmethod
    def cmd_summary(cls):
        today_jobs = JobScanner.get_today_results()
        all_results = JobScanner._load_results()

        if not today_jobs and not all_results:
            cls._send("No hay resultados de escaneo. Ejecuta /scan primero.")
            return

        jobs = today_jobs if today_jobs else all_results[-15:]
        label = "hoy" if today_jobs else f"ultimos {len(jobs)}"

        lines = [f"*RESUMEN DE OFERTAS ({label}):*\n"]

        for i, job in enumerate(jobs[:10], 1):
            stack = ", ".join(job.get("detected_stack", [])[:3])
            lines.append(f"{i}. *{job['title']}*")
            lines.append(f"   {job['company']} | {job.get('location', '')}")
            if stack:
                lines.append(f"   `{stack}`")
            lines.append("")

        # Skills ranking
        skills = JobScanner.get_demanded_skills()
        if skills:
            lines.append("*Skills mas demandadas:*")
            for skill, count in list(skills.items())[:8]:
                bar = "█" * min(count, 10)
                lines.append(f"  `{skill:<16}` {bar} ({count})")

        # Empresas target
        companies = JobScanner.get_target_companies()
        if companies:
            lines.append(f"\n*Empresas target ({len(companies)}):*")
            lines.append(", ".join(companies[:10]))

        cls._send("\n".join(lines))

    @classmethod
    def cmd_publish(cls, project_name: str = ""):
        cls._send(f"📓 Generando borrador del Diario de Desarrollo {f'({project_name})' if project_name else ''} con captura de código real...")

        def _run():
            try:
                DevDiaryGenerator.prepare_daily_diary_draft(
                    wait_approval=False,
                    project_filter=project_name if project_name else None
                )
            except Exception as e:
                cls._send(f"Error generando borrador:\n`{traceback.format_exc()[-500:]}`")

        threading.Thread(target=_run, daemon=True).start()

    @classmethod
    def cmd_engage(cls):
        cls._send("🤝 Pre-buscando perfiles de RRHH/Selección y preparando las 5 solicitudes de conexión...")

        def _run():
            try:
                actions = EngagementEngine.propose_actions()
                if not actions:
                    cls._send("No hay acciones de engagement disponibles.\nEjecuta /scan primero para detectar empresas target.")
                    return

                global _pending_engagement_actions
                _pending_engagement_actions = actions

                text, keyboard = EngagementEngine._build_engagement_message_and_keyboard(actions)
                cls._send(text, reply_markup=keyboard)
            except Exception as e:
                cls._send(f"Error preparando plan de engagement:\n`{str(e)[:500]}`")

        threading.Thread(target=_run, daemon=True).start()

    @classmethod
    def cmd_apply(cls, custom_keywords: Optional[str] = None):
        cls._send(
            "🔎 Buscando vacantes de *Solicitud Sencilla (Easy Apply)* en LinkedIn y "
            "generando tu *CV adaptado* a cada puesto (~30s)..."
        )

        def _run():
            try:
                jobs = EasyApplyEngine.scan_easy_apply_jobs(keywords=custom_keywords, max_results=5)
                if not jobs:
                    cls._send("No se encontraron nuevas vacantes de Solicitud Sencilla disponibles ahora mismo.")
                    return

                global _pending_easy_apply_jobs
                _pending_easy_apply_jobs = jobs

                text, keyboard = EasyApplyEngine._build_telegram_message_and_keyboard(jobs)
                cls._send(text, reply_markup=keyboard)
            except Exception as e:
                cls._send(f"Error buscando ofertas Easy Apply:\n`{str(e)[:500]}`")

        threading.Thread(target=_run, daemon=True).start()

    @classmethod
    def cmd_limits(cls):
        today = date.today().isoformat()
        pub_records = AntiBanValidator.get_records()
        today_posts = len([r for r in pub_records
                          if r.get("date", "").startswith(today) and r.get("status") == "success"])

        eng = AntiBanValidator.get_today_engagement_summary()

        lines = [
            "*LIMITES ANTI-BAN*\n",
            f"Posts:       {today_posts}/{MAX_DAILY_POSTS}",
            f"Comentarios: {eng.get('comment', 0)}/{MAX_DAILY_COMMENTS}",
            f"Conexiones:  {eng.get('connection', 0)}/{MAX_DAILY_CONNECTIONS}",
            f"Reacciones:  {eng.get('reaction', 0)}/{MAX_DAILY_REACTIONS}",
        ]

        # Indicadores visuales
        for label, used, total in [
            ("Posts", today_posts, MAX_DAILY_POSTS),
            ("Comments", eng.get("comment", 0), MAX_DAILY_COMMENTS),
            ("Connects", eng.get("connection", 0), MAX_DAILY_CONNECTIONS),
            ("Reactions", eng.get("reaction", 0), MAX_DAILY_REACTIONS),
        ]:
            filled = int((used / max(total, 1)) * 10)
            bar = "█" * filled + "░" * (10 - filled)
            lines.append(f"`{label:<10}` {bar}")

        cls._send("\n".join(lines))

    @classmethod
    def cmd_drafts(cls):
        drafts = _get_drafts()
        if not drafts:
            cls._send("No hay borradores guardados.")
            return

        lines = ["*BORRADORES*\n"]
        for d_id, d in list(drafts.items())[-10:]:
            status_emoji = {
                "pending": "⏳",
                "scheduled": "🕙",
                "published": "✅",
                "rejected": "🗑",
                "failed": "❌"
            }.get(d.get("status", ""), "❓")
            sched_info = f" -> {d.get('scheduled_for', '')[:16]}" if d.get("status") == "scheduled" else ""
            lines.append(f"{status_emoji} `{d_id}` - {d.get('project_name', '?')} ({d.get('status', '?')}{sched_info})")
            lines.append(f"   {d.get('created_at', '')[:16]}")

        cls._send("\n".join(lines))

    @classmethod
    def cmd_history(cls):
        """Muestra el historial consolidado de publicaciones, solicitudes de contacto y vacantes aplicadas."""
        lines = ["📜 *HISTORIAL GENERAL JOBSEEKERGA*\n"]

        # 1. Publicaciones
        pub_records = [r for r in AntiBanValidator.get_records() if r.get("status") == "success"]
        lines.append(f"📝 *PUBLICACIONES REALIZADAS ({len(pub_records)}):*")
        if pub_records:
            for p in reversed(pub_records[-5:]):
                p_date = p.get("date", "")[:10]
                p_name = p.get("project_name", "Post técnico")
                p_url = p.get("published_url", "")
                url_str = f" [🔗 Ver]({p_url})" if p_url else ""
                lines.append(f"• `{p_date}`: {p_name}{url_str}")
        else:
            lines.append("• Sin publicaciones registradas todavía.")
        lines.append("")

        # 2. Solicitudes de contacto / Engagement
        eng_records = [r for r in AntiBanValidator._get_engagement_records() if r.get("status") == "success"]
        conn_records = [r for r in eng_records if r.get("action") == "connection"]
        lines.append(f"🤝 *CONTACTOS RRHH ENVIADOS ({len(conn_records)}):*")
        if conn_records:
            for c in reversed(conn_records[-6:]):
                c_date = c.get("date", "")[:10]
                c_target = c.get("target", "Recruiter")
                c_detail = c.get("detail", "")
                lines.append(f"• `{c_date}`: *{c_target}* {c_detail}")
        else:
            lines.append("• Sin solicitudes registradas.")
        lines.append("")

        # 3. Vacantes aplicadas (Easy Apply)
        apply_records = [r for r in EasyApplyEngine._load_history() if r.get("status") == "success"]
        lines.append(f"🚀 *VACANTES SOLICITUD SENCILLA APLICADAS ({len(apply_records)}):*")
        if apply_records:
            for a in reversed(apply_records[-6:]):
                a_date = a.get("date", "")[:10]
                a_title = a.get("title", "Puesto IT")
                a_comp = a.get("company", "Empresa")
                a_cv = a.get("cv_label", "CV Oficial")
                a_url = a.get("url", "")
                url_link = f" [🔗 Ver]({a_url})" if a_url else ""
                lines.append(f"• `{a_date}`: *{a_title}* — {a_comp} (`{a_cv}`){url_link}")
        else:
            lines.append("• Sin candidaturas registradas.")

        cls._send("\n".join(lines))

    @classmethod
    def cmd_health(cls):
        cls._send("🔍 Verificando salud de la sesión persistente de LinkedIn...")

        def _run():
            status = LinkedInPublisher.check_session_health()
            icon = "✅" if status.get("ok") else "⚠️"
            cls._send(f"{icon} *Estado de Sesión LinkedIn:*\n{status.get('reason', '')}")

        threading.Thread(target=_run, daemon=True).start()

    # --- Callback handlers ---

    @classmethod
    def handle_callback(cls, callback_query: dict):
        cb_id = callback_query["id"]
        data = callback_query.get("data", "")
        message = callback_query.get("message", {})
        message_id = message.get("message_id")
        chat_id = message.get("chat", {}).get("id")

        if ":" not in data:
            cls._answer_callback(cb_id, "Accion no reconocida.")
            return

        action, target = data.split(":", 1)

        if action == "approve":
            cls._handle_approve_draft(cb_id, target, chat_id, message_id)
        elif action == "schedule10":
            when_str = TelegramReviewer.schedule_draft_for_10am(target)
            cls._answer_callback(cb_id, f"Programado para {when_str}")
            cls._remove_buttons(chat_id, message_id)
            cls._send(f"🕙 Borrador `{target}` programado automáticamente para *{when_str}*.")
        elif action == "regen":
            cls._answer_callback(cb_id, "Regenerando enfoque y capturas...")
            cls._remove_buttons(chat_id, message_id)
            cls._send(f"🔄 Regenerando borrador `{target}` con otro módulo/función del proyecto...")
            threading.Thread(target=DevDiaryGenerator.regenerate_draft_by_id, args=(target,), daemon=True).start()
        elif action == "reject":
            cls._handle_reject_draft(cb_id, target, chat_id, message_id)
        elif action == "engage":
            cls._handle_engage_decision(cb_id, target, chat_id, message_id)
        elif action == "apply":
            cls._handle_apply_decision(cb_id, target, chat_id, message_id)
        else:
            cls._answer_callback(cb_id, "Accion desconocida.")

    @classmethod
    def _handle_approve_draft(cls, cb_id: str, draft_id: str, chat_id: int, message_id: int):
        drafts = _get_drafts()
        if draft_id not in drafts:
            cls._answer_callback(cb_id, "Borrador no encontrado o expirado.")
            return

        draft = drafts[draft_id]
        cls._answer_callback(cb_id, "Publicando en LinkedIn...")
        cls._remove_buttons(chat_id, message_id)
        cls._send(f"⏳ Publicando *{draft['project_name']}* en LinkedIn...")

        def _run():
            try:
                TelegramReviewer.publish_approved_draft(draft_id)
            except Exception as e:
                cls._send(f"Error durante publicacion:\n`{str(e)[:500]}`")

        threading.Thread(target=_run, daemon=True).start()

    @classmethod
    def _handle_reject_draft(cls, cb_id: str, draft_id: str, chat_id: int, message_id: int):
        drafts = _get_drafts()
        if draft_id in drafts:
            drafts[draft_id]["status"] = "rejected"
            _save_drafts(drafts)

        cls._answer_callback(cb_id, "Borrador descartado.")
        cls._remove_buttons(chat_id, message_id)
        cls._send(f"Borrador `{draft_id}` descartado.")

    @classmethod
    def _handle_engage_decision(cls, cb_id: str, decision: str, chat_id: int, message_id: int):
        global _pending_engagement_actions

        if decision.startswith("toggle_"):
            try:
                idx = int(decision.split("_")[1])
                if 0 <= idx < len(_pending_engagement_actions):
                    _pending_engagement_actions[idx]["enabled"] = not _pending_engagement_actions[idx].get("enabled", True)
                    new_text, new_kb = EngagementEngine._build_engagement_message_and_keyboard(_pending_engagement_actions)
                    http.post(
                        f"{cls.BASE_URL}/editMessageText",
                        json={
                            "chat_id": chat_id,
                            "message_id": message_id,
                            "text": new_text[:4000],
                            "parse_mode": "Markdown",
                            "disable_web_page_preview": True,
                            "reply_markup": new_kb
                        },
                        timeout=10
                    )
                    cls._answer_callback(cb_id, f"Contacto #{idx + 1} actualizado")
            except Exception:
                pass
            return

        cls._remove_buttons(chat_id, message_id)

        if decision == "approve":
            cls._answer_callback(cb_id, "Ejecutando plan de engagement...")
            actions = [a for a in _pending_engagement_actions if a.get("enabled", True)]
            _pending_engagement_actions = []

            if not actions:
                cls._send("No hay acciones seleccionadas. Usa /engage para generar un nuevo plan.")
                return

            cls._send(f"⏳ Ejecutando {len(actions)} acciones de engagement...")

            def _run():
                try:
                    results = EngagementEngine._execute_actions(actions)
                    EngagementEngine._report_results(results, chat_id)
                except Exception as e:
                    cls._send(f"Error durante engagement:\n`{str(e)[:500]}`")

            threading.Thread(target=_run, daemon=True).start()

        elif decision == "reject":
            _pending_engagement_actions = []
            cls._answer_callback(cb_id, "Plan cancelado.")
            cls._send("Plan de engagement cancelado.")

    @classmethod
    def _handle_apply_decision(cls, cb_id: str, decision: str, chat_id: int, message_id: int):
        global _pending_easy_apply_jobs
        from src.easy_apply import PENDING_EASY_APPLY_FILE
        if not _pending_easy_apply_jobs and PENDING_EASY_APPLY_FILE.exists():
            try:
                _pending_easy_apply_jobs = json.loads(PENDING_EASY_APPLY_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass

        if decision.startswith("toggle_"):
            try:
                idx = int(decision.split("_")[1])
                if 0 <= idx < len(_pending_easy_apply_jobs):
                    _pending_easy_apply_jobs[idx]["enabled"] = not _pending_easy_apply_jobs[idx].get("enabled", True)
                    try:
                        PENDING_EASY_APPLY_FILE.write_text(
                            json.dumps(_pending_easy_apply_jobs, indent=2, ensure_ascii=False),
                            encoding="utf-8"
                        )
                    except Exception:
                        pass
                    new_text, new_kb = EasyApplyEngine._build_telegram_message_and_keyboard(_pending_easy_apply_jobs)
                    http.post(
                        f"{cls.BASE_URL}/editMessageText",
                        json={
                            "chat_id": chat_id,
                            "message_id": message_id,
                            "text": new_text[:4000],
                            "parse_mode": "Markdown",
                            "disable_web_page_preview": True,
                            "reply_markup": new_kb
                        },
                        timeout=10
                    )
                    cls._answer_callback(cb_id, f"Vacante #{idx + 1} actualizada")
            except Exception:
                pass
            return

        cls._remove_buttons(chat_id, message_id)

        if decision == "approve":
            cls._answer_callback(cb_id, "Enviando candidaturas Easy Apply...")
            selected = [j for j in _pending_easy_apply_jobs if j.get("enabled", True)]
            _pending_easy_apply_jobs = []

            if not selected:
                cls._send("No hay vacantes seleccionadas. Usa /apply para buscar de nuevo.")
                return

            cls._send(f"⏳ Aplicando a {len(selected)} vacantes con tu CV adaptado...")

            def _run():
                try:
                    results = EasyApplyEngine.execute_applications(selected)
                    EasyApplyEngine.report_results_to_telegram(results, chat_id)
                except Exception as e:
                    cls._send(f"Error durante Easy Apply:\n`{str(e)[:500]}`")

            threading.Thread(target=_run, daemon=True).start()

        elif decision == "reject":
            _pending_easy_apply_jobs = []
            cls._answer_callback(cb_id, "Candidaturas canceladas.")
            cls._send("❌ Envío de candidaturas de Solicitud Sencilla cancelado.")

    @classmethod
    def _scheduler_worker(cls):
        """
        Hilo daemon que comprueba cada 45 segundos si hay algún borrador en pending_drafts.json
        con status='scheduled' cuya hora programada (scheduled_for) ya haya llegado,
        publicándolo automáticamente y ejecutando las 5 solicitudes de conexión diarias.
        Además, ejecuta la autorregulación periódica de memoria y purga de temporales.
        """
        loops_counter = 0
        while True:
            try:
                loops_counter += 1
                # Cada ~15 minutos (20 ciclos de 45s) forzar barrido de memoria y purga de temporales
                if loops_counter % 20 == 0:
                    ResourceGovernor.run_full_cleanup(profile_dir=BROWSER_PROFILE_DIR)

                drafts = _get_drafts()
                now = datetime.now()
                for d_id, d_obj in list(drafts.items()):
                    if d_obj.get("status") == "scheduled" and d_obj.get("scheduled_for"):
                        sched_str = d_obj["scheduled_for"]
                        try:
                            sched_dt = datetime.fromisoformat(sched_str).replace(tzinfo=None)
                        except Exception:
                            continue
                        if now >= sched_dt:
                            print(f"[Scheduler] Hora alcanzada para borrador programado {d_id}. Publicando...")
                            d_obj["status"] = "publishing"
                            _save_drafts(drafts)
                            TelegramReviewer.publish_approved_draft(d_id)

                            # Ejecutar también las 5 conexiones diarias con RRHH si aún no se han enviado hoy
                            eng_today = AntiBanValidator.get_today_engagement_summary()
                            if eng_today.get("connection", 0) == 0:
                                print("[Scheduler] Ejecutando las 5 solicitudes de conexión diarias tras la publicación...")
                                actions = EngagementEngine.propose_actions(max_actions=MAX_DAILY_CONNECTIONS, discover_profiles=False)
                                if actions:
                                    results = EngagementEngine._execute_actions(actions)
                                    EngagementEngine._report_results(results, int(TELEGRAM_CHAT_ID))
                            
                            # Liberar inmediatamente recursos tras publicar
                            ResourceGovernor.run_full_cleanup(profile_dir=BROWSER_PROFILE_DIR)
            except Exception as e:
                print(f"[Scheduler] Aviso en bucle de cola: {e}")
            time.sleep(45)

    # --- Main loop ---

    @classmethod
    def run(cls):
        """Inicia el bot en modo long-polling junto con el scheduler integrado."""
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            print("[Bot] Error: TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID deben estar configurados en .env")
            return

        print("=" * 55)
        print(" JOBSEEKERGA TELEGRAM BOT + SCHEDULER")
        print("=" * 55)
        print(f"[Bot] Token: ...{TELEGRAM_BOT_TOKEN[-8:]}")
        print(f"[Bot] Chat ID: {TELEGRAM_CHAT_ID}")
        print(f"[Bot] Escuchando comandos y cola programada. Ctrl+C para detener.\n")

        # Iniciar hilo del scheduler de publicaciones programadas
        threading.Thread(target=cls._scheduler_worker, daemon=True).start()

        # Registrar comandos en el menu de Telegram
        cls._register_commands()

        last_update_id = 0
        allowed_chat = str(TELEGRAM_CHAT_ID)

        while True:
            try:
                r = http.get(
                    f"{cls.BASE_URL}/getUpdates",
                    params={"offset": last_update_id + 1, "timeout": 30},
                    timeout=35
                )
                if r.status_code != 200:
                    time.sleep(2)
                    continue

                for update in r.json().get("result", []):
                    last_update_id = update["update_id"]

                    # Seguridad: solo responder a nuestro chat
                    update_chat = str(
                        update.get("message", {}).get("chat", {}).get("id", "") or
                        update.get("callback_query", {}).get("message", {}).get("chat", {}).get("id", "")
                    )
                    if update_chat != allowed_chat:
                        continue

                    # Callback de botones inline
                    if "callback_query" in update:
                        cls.handle_callback(update["callback_query"])
                        continue

                    msg = update.get("message", {})
                    text = msg.get("text", "").strip()

                    # Edición de borrador respondiendo (Reply) al mensaje en Telegram
                    if "reply_to_message" in msg and text and not text.startswith("/"):
                        replied_id = msg["reply_to_message"].get("message_id")
                        drafts = _get_drafts()
                        for d_id, d_obj in drafts.items():
                            if d_obj.get("telegram_message_id") == replied_id:
                                cleaned = DevDiaryGenerator._format_clean_post(text)
                                d_obj["text"] = cleaned
                                _save_drafts(drafts)
                                cls._send(
                                    f"✏️ *Texto del borrador `{d_id}` actualizado y maquetado:*\n\n{cleaned}",
                                    reply_markup={
                                        "inline_keyboard": [
                                            [
                                                {"text": "✅ Publicar ahora", "callback_data": f"approve:{d_id}"},
                                                {"text": "🕙 Programar 10:00 AM", "callback_data": f"schedule10:{d_id}"}
                                            ],
                                            [
                                                {"text": "❌ Descartar", "callback_data": f"reject:{d_id}"}
                                            ]
                                        ]
                                    }
                                )
                                break
                        continue

                    if not text.startswith("/"):
                        continue

                    parts = text.split(maxsplit=1)
                    cmd = parts[0].lower().split("@")[0]  # Quitar @botname
                    arg = parts[1].strip() if len(parts) > 1 else ""

                    ts = datetime.now().strftime("%H:%M:%S")
                    print(f"[{ts}] Comando: {cmd} {arg}")

                    if cmd == "/start":
                        cls.cmd_start()
                    elif cmd == "/help":
                        cls.cmd_help()
                    elif cmd == "/status":
                        cls.cmd_status()
                    elif cmd == "/scan":
                        cls.cmd_scan(custom_keywords=arg if arg else None)
                    elif cmd == "/summary":
                        cls.cmd_summary()
                    elif cmd == "/publish":
                        cls.cmd_publish(project_name=arg if arg else "")
                    elif cmd == "/engage":
                        cls.cmd_engage()
                    elif cmd == "/apply":
                        cls.cmd_apply(custom_keywords=arg if arg else None)
                    elif cmd == "/limits":
                        cls.cmd_limits()
                    elif cmd == "/drafts":
                        cls.cmd_drafts()
                    elif cmd == "/history":
                        cls.cmd_history()
                    elif cmd == "/health":
                        cls.cmd_health()
                    else:
                        cls._send(f"Comando no reconocido: `{cmd}`\nUsa /help para ver los disponibles.")

            except KeyboardInterrupt:
                print("\n[Bot] Detenido por el usuario.")
                break
            except Exception as e:
                print(f"[Bot] Error en loop principal: {e}")
                time.sleep(3)

    @classmethod
    def _register_commands(cls):
        """Registra los comandos en el menu de Telegram (el boton / del chat)."""
        commands = [
            {"command": "status", "description": "Dashboard de actividad del dia"},
            {"command": "scan", "description": "Escanear ofertas en LinkedIn Jobs"},
            {"command": "summary", "description": "Resumen ofertas + ranking skills"},
            {"command": "publish", "description": "Generar borrador de post para LinkedIn"},
            {"command": "engage", "description": "Proponer plan de engagement (5 conexiones)"},
            {"command": "apply", "description": "Vacantes Solicitud Sencilla con CV adaptado"},
            {"command": "history", "description": "Historial de posts, contactos y candidaturas"},
            {"command": "limits", "description": "Ver limites anti-ban restantes"},
            {"command": "drafts", "description": "Ver borradores pendientes"},
            {"command": "health", "description": "Verificar sesion de LinkedIn"},
            {"command": "help", "description": "Lista de comandos"},
        ]
        try:
            http.post(f"{cls.BASE_URL}/setMyCommands",
                      json={"commands": commands}, timeout=10)
        except Exception:
            pass
