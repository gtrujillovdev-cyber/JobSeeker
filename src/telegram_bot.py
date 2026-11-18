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

import os
import time
import json
import threading
import traceback
from datetime import datetime, date, timedelta
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
from src.telegram_reviewer import TelegramReviewer, _get_drafts, _save_drafts, expire_stale_drafts
from src.dev_diary import DevDiaryGenerator
from src.easy_apply import EasyApplyEngine
from src.resource_governor import ResourceGovernor
from config import BROWSER_PROFILE_DIR

# Almacen temporal y persistente de acciones de engagement y candidaturas Easy Apply pendientes de aprobacion
PENDING_ENGAGEMENT_FILE = DATA_DIR / "pending_engagement.json"
DAILY_SCHEDULER_STATE_FILE = DATA_DIR / "daily_scheduler_state.json"
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
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "📓 Nuevo borrador", "callback_data": "menu:publish"},
                    {"text": "📋 Ver borradores", "callback_data": "menu:drafts"}
                ],
                [
                    {"text": "🤝 5 Contactos Sevilla", "callback_data": "menu:engage"},
                    {"text": "🚀 Vacantes Easy Apply", "callback_data": "menu:apply"}
                ],
                [
                    {"text": "📊 Estado hoy", "callback_data": "menu:status"},
                    {"text": "🔐 Salud LinkedIn", "callback_data": "menu:health"}
                ],
                [
                    {"text": "📖 Guía rápida", "callback_data": "menu:guia"},
                    {"text": "🧹 Limpiar borradores", "callback_data": "drafts:cleanup"}
                ]
            ]
        }
        cls._send(
            "*JobSeekerGA Bot — Panel de Control*\n\n"
            "Elige una acción directa con los botones o escribe /guia para ver el flujo completo.",
            reply_markup=keyboard
        )

    @classmethod
    def cmd_guia(cls):
        cls._send(
            "*📖 GUÍA RÁPIDA DE USO*\n\n"
            "*1. Publicar un post del Diario:*\n"
            "• Cada día a las 09:30 llega un borrador nuevo.\n"
            "• Si quieres pedir uno ahora, usa /publish (o `/publish LawLab`).\n"
            "• En el borrador pulsa *✅ Publicar ahora* para subirlo al momento, o *🕙 Programar 10:00 AM* para dejarlo en cola.\n"
            "• Para editar el texto antes de publicar, haz *Responder (Reply)* al mensaje del borrador con el nuevo texto.\n\n"
            "*2. Borrar o publicar borradores antiguos:*\n"
            "• Usa /drafts: verás botones directos para *Publicar*, *Programar* o *Descartar* cada borrador activo.\n"
            "• Usa /clear (o el botón *🧹 Limpiar borradores*) para eliminar de golpe descartados, fallidos, regenerados y mensajes viejos.\n\n"
            "*3. Contactos RRHH (Sevilla 2º grado) y Vacantes:*\n"
            "• /engage propone 5 contactos de 2º grado en Sevilla con botones `#1..#5` para desmarcar.\n"
            "• /apply busca 5 vacantes de Solicitud Sencilla con tu CV adaptado.\n"
            "• /health verifica en 5s si la sesión de LinkedIn está activa.",
            reply_markup={
                "inline_keyboard": [
                    [
                        {"text": "📋 Abrir /drafts", "callback_data": "menu:drafts"},
                        {"text": "📓 Generar /publish", "callback_data": "menu:publish"}
                    ]
                ]
            }
        )

    @classmethod
    def cmd_help(cls):
        cls._send(
            "*Comandos disponibles:*\n\n"
            "/start o /menu - Panel principal con botones\n"
            "/guia - Guía paso a paso (publicar, editar, limpiar)\n"
            "/publish `Proyecto` - Generar borrador nuevo\n"
            "/drafts - Gestionar y publicar borradores\n"
            "/clear - Limpiar borradores antiguos/descartados\n"
            "/engage - Proponer 5 contactos en Sevilla (2º grado)\n"
            "/apply - Buscar vacantes Solicitud Sencilla + CV\n"
            "/scan `keywords` - Escanear ofertas en LinkedIn Jobs\n"
            "/summary - Resumen de ofertas + ranking skills\n"
            "/status - Dashboard de actividad del dia\n"
            "/history - Historial completo (posts, RRHH, vacantes)\n"
            "/limits - Ver limites anti-ban restantes\n"
            "/health - Verificar sesion de LinkedIn\n"
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
        drafts = expire_stale_drafts(max_age_hours=24.0)
        for d_id, d in drafts.items():
            st = d.get("status", "")
            if st in ("scheduled", "publishing"):
                sched_when = d.get("scheduled_for", "10:00")[:16].replace("T", " ")
                cls._send(
                    f"🕙 *Ya hay una publicación programada:* `{d_id}` ({d.get('project_name', '')})\n"
                    f"⏰ Programada para: *{sched_when}*\n\n"
                    f"No se volverá a generar otra hasta que se publique o la canceles.",
                    reply_markup={
                        "inline_keyboard": [[
                            {"text": "📋 Ver /drafts", "callback_data": "menu:drafts"},
                            {"text": "❌ Cancelar programada", "callback_data": f"reject:{d_id}"}
                        ]]
                    }
                )
                return
            if st == "pending":
                cls._send(
                    f"⏳ *Ya existe un borrador pendiente:* `{d_id}` ({d.get('project_name', '')})\n\n"
                    f"Para evitar duplicados o acumular borradores, decide qué hacer con este primero:",
                    reply_markup={
                        "inline_keyboard": [
                            [
                                {"text": "✅ Publicar ahora", "callback_data": f"approve:{d_id}"},
                                {"text": "🕙 Programar 10:00", "callback_data": f"schedule10:{d_id}"}
                            ],
                            [
                                {"text": "🔄 Cambiar enfoque", "callback_data": f"regen:{d_id}"},
                                {"text": "❌ Descartar", "callback_data": f"reject:{d_id}"}
                            ]
                        ]
                    }
                )
                return

        cls._send(f"📓 Generando borrador del Diario de Desarrollo {f'({project_name})' if project_name else ''} con captura de código real...")

        def _run():
            try:
                res = DevDiaryGenerator.prepare_daily_diary_draft(
                    wait_approval=False,
                    project_filter=project_name if project_name else None
                )
                if not res:
                    cls._send("⛔ No se generó borrador nuevo (ya hay uno activo/programado o se agotaron píldoras inéditas en este alcance).")
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
                try:
                    PENDING_ENGAGEMENT_FILE.write_text(
                        json.dumps(_pending_engagement_actions, indent=2, ensure_ascii=False),
                        encoding="utf-8"
                    )
                except Exception:
                    pass

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
    def _delete_telegram_message(cls, chat_id: Any, message_id: Any) -> bool:
        if not chat_id or not message_id:
            return False
        try:
            r = http.post(
                f"{cls.BASE_URL}/deleteMessage",
                json={"chat_id": chat_id, "message_id": message_id},
                timeout=8
            )
            return r.status_code == 200 and r.json().get("ok", False)
        except Exception:
            return False

    @classmethod
    def cmd_drafts(cls):
        drafts = _get_drafts()
        if not drafts:
            cls._send("No hay borradores guardados.")
            return

        active_statuses = {"pending", "scheduled", "failed", "publishing"}
        active_items = [
            (d_id, d) for d_id, d in drafts.items()
            if d.get("status") in active_statuses
        ]
        archived_items = [
            (d_id, d) for d_id, d in drafts.items()
            if d.get("status") not in active_statuses
        ]

        lines = ["*GESTOR DE BORRADORES*\n"]
        keyboard_rows = []

        if active_items:
            lines.append(f"*Activos / listos ({len(active_items)}):*")
            for d_id, d in active_items[-5:]:
                st = d.get("status", "pending")
                emoji = {"pending": "⏳", "scheduled": "🕙", "failed": "❌", "publishing": "🔄"}.get(st, "⏳")
                sched_info = f" -> {d.get('scheduled_for', '')[:16]}" if st == "scheduled" else ""
                proj = d.get("project_name", "?")
                lines.append(f"{emoji} `{d_id}` · *{proj}* ({st}{sched_info})")
                lines.append(f"   _{d.get('created_at', '')[:16]}_")
                keyboard_rows.append([
                    {"text": f"✅ Publicar {d_id}", "callback_data": f"approve:{d_id}"},
                    {"text": f"🕙 10:00", "callback_data": f"schedule10:{d_id}"},
                    {"text": f"🗑 Borrar", "callback_data": f"reject:{d_id}"}
                ])
        else:
            lines.append("_No hay borradores pendientes ahora mismo. Usa /publish para crear uno._")

        if archived_items:
            pub_cnt = sum(1 for _, d in archived_items if d.get("status") == "published")
            stale_cnt = len(archived_items) - pub_cnt
            lines.append(f"\n📦 *Histórico:* {pub_cnt} publicados · {stale_cnt} descartados/antiguos")

        keyboard_rows.append([
            {"text": "🧹 Limpiar borradores antiguos", "callback_data": "drafts:cleanup"},
            {"text": "📓 Nuevo borrador", "callback_data": "menu:publish"}
        ])

        cls._send("\n".join(lines), reply_markup={"inline_keyboard": keyboard_rows})

    @classmethod
    def cmd_clear_drafts(cls, silent_if_empty: bool = False):
        """Elimina borradores descartados, regenerados, fallidos y pendientes duplicados antiguos, preservando los publicados."""
        drafts = _get_drafts()
        if not drafts:
            if not silent_if_empty:
                cls._send("No hay borradores antiguos para limpiar.")
            return

        # Identificar el borrador pending/scheduled más reciente para no perder el actual si existe
        active_candidates = [
            (d_id, d) for d_id, d in drafts.items()
            if d.get("status") in ("pending", "scheduled")
        ]
        latest_active_id = active_candidates[-1][0] if active_candidates else None

        kept: Dict[str, Any] = {}
        removed_ids = []
        deleted_tg_msgs = 0

        for d_id, d in drafts.items():
            st = d.get("status", "")
            if st == "published" or d_id == latest_active_id:
                kept[d_id] = d
            else:
                removed_ids.append(d_id)
                if d.get("telegram_message_id") and TELEGRAM_CHAT_ID:
                    if cls._delete_telegram_message(TELEGRAM_CHAT_ID, d.get("telegram_message_id")):
                        deleted_tg_msgs += 1

        _save_drafts(kept)

        # Preservar historial publicado y memoria de píldoras ya vistas/descartadas (rejected/regenerated/expired)
        history_file = DATA_DIR / "dev_diary_history.json"
        if history_file.exists():
            try:
                hist = json.loads(history_file.read_text(encoding="utf-8"))
                preserve_statuses = {"published", "rejected", "regenerated", "expired"}
                cleaned_hist = [
                    h for h in hist
                    if h.get("status") in preserve_statuses or h.get("draft_id") == latest_active_id
                ]
                history_file.write_text(json.dumps(cleaned_hist, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass

        kept_active_msg = f"\n✅ Activo conservado: `{latest_active_id}`" if latest_active_id else ""
        tg_msg_note = f"\n🗑 Mensajes eliminados del chat: {deleted_tg_msgs}" if deleted_tg_msgs else ""
        cls._send(
            f"🧹 *Limpieza completada:* {len(removed_ids)} borrador(es) antiguo(s) eliminado(s).{tg_msg_note}{kept_active_msg}",
            reply_markup={
                "inline_keyboard": [[{"text": "📋 Ver /drafts", "callback_data": "menu:drafts"}]]
            }
        )

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
            from src.browser_helper import get_li_at_expiry_days
            status = LinkedInPublisher.check_session_health()
            icon = "✅" if status.get("ok") else "⚠️"
            days_left = get_li_at_expiry_days()
            ttl_line = f"\n🕒 Validez cookie `li_at`: *{days_left:.0f} días restantes*" if days_left is not None else ""
            cls._send(f"{icon} *Estado de Sesión LinkedIn:*\n{status.get('reason', '')}{ttl_line}")

        threading.Thread(target=_run, daemon=True).start()

    # --- Callback handlers ---

    @classmethod
    def handle_callback(cls, callback_query: dict):
        cb_id = callback_query["id"]
        data = callback_query.get("data", "")
        message = callback_query.get("message", {})
        message_id = message.get("message_id")
        chat_id = message.get("chat", {}).get("id") or callback_query.get("from", {}).get("id")

        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] [Callback] data='{data}' chat_id={chat_id} msg_id={message_id}")

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
            cls._send(f"🔄 Regenerando borrador `{target}` con otro enfoque o proyecto...")
            def _run_regen():
                try:
                    new_id = DevDiaryGenerator.regenerate_draft_by_id(target)
                    if not new_id:
                        cls._send("⚠️ No se pudo generar un enfoque nuevo (revisa /drafts o si hay una publicación programada).")
                except Exception as e_reg:
                    cls._send(f"Error regenerando enfoque:\n`{str(e_reg)[:400]}`")
            threading.Thread(target=_run_regen, daemon=True).start()
        elif action == "reject":
            cls._handle_reject_draft(cb_id, target, chat_id, message_id)
        elif action == "engage":
            cls._handle_engage_decision(cb_id, target, chat_id, message_id)
        elif action == "apply":
            cls._handle_apply_decision(cb_id, target, chat_id, message_id)
        elif action == "drafts" and target == "cleanup":
            cls._answer_callback(cb_id, "Limpiando borradores antiguos...")
            cls.cmd_clear_drafts()
        elif action == "menu":
            cls._answer_callback(cb_id, "Ejecutando...")
            if target == "publish":
                cls.cmd_publish()
            elif target == "drafts":
                cls.cmd_drafts()
            elif target == "engage":
                cls.cmd_engage()
            elif target == "apply":
                cls.cmd_apply()
            elif target == "status":
                cls.cmd_status()
            elif target == "health":
                cls.cmd_health()
            elif target == "guia":
                cls.cmd_guia()
            else:
                cls.cmd_start()
        else:
            cls._answer_callback(cb_id, "Accion desconocida.")

    @classmethod
    def _handle_approve_draft(cls, cb_id: str, draft_id: str, chat_id: int, message_id: int):
        drafts = _get_drafts()
        if draft_id not in drafts:
            cls._answer_callback(cb_id, "Borrador no encontrado.")
            cls._send(f"⚠️ El borrador `{draft_id}` no se encuentra en la cola de borradores activos (usa /drafts para ver los disponibles).")
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
        old = drafts.pop(draft_id, None)
        _save_drafts(drafts)

        history_file = DATA_DIR / "dev_diary_history.json"
        if history_file.exists():
            try:
                hist = json.loads(history_file.read_text(encoding="utf-8"))
                found = False
                for h in hist:
                    if h.get("draft_id") == draft_id and h.get("status") != "published":
                        h["status"] = "rejected"
                        found = True
                if not found and old and old.get("pill_id"):
                    hist.append({
                        "draft_id": draft_id,
                        "date": datetime.now().isoformat(),
                        "dir_name": old.get("project_name", "").split("·")[-1].strip(),
                        "pill_id": old.get("pill_id"),
                        "status": "rejected",
                    })
                history_file.write_text(json.dumps(hist, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass

        cls._answer_callback(cb_id, "Borrador descartado y eliminado.")
        cls._remove_buttons(chat_id, message_id)
        cls._send(f"🗑 Borrador `{draft_id}` descartado y eliminado definitivamente.")

    @classmethod
    def _handle_engage_decision(cls, cb_id: str, decision: str, chat_id: int, message_id: int):
        global _pending_engagement_actions
        if not _pending_engagement_actions and PENDING_ENGAGEMENT_FILE.exists():
            try:
                _pending_engagement_actions = json.loads(PENDING_ENGAGEMENT_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass

        if decision.startswith("toggle_"):
            try:
                idx = int(decision.split("_")[1])
                if 0 <= idx < len(_pending_engagement_actions):
                    _pending_engagement_actions[idx]["enabled"] = not _pending_engagement_actions[idx].get("enabled", True)
                    try:
                        PENDING_ENGAGEMENT_FILE.write_text(
                            json.dumps(_pending_engagement_actions, indent=2, ensure_ascii=False),
                            encoding="utf-8"
                        )
                    except Exception:
                        pass
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

    @staticmethod
    def _update_heartbeat():
        """Actualiza el timestamp de heartbeat en data/heartbeat.txt (patrón armonizado con GTAVIHub en mbp1)."""
        try:
            hb_file = DATA_DIR / "heartbeat.txt"
            hb_file.write_text(str(int(time.time())), encoding="utf-8")
        except Exception:
            pass

    @staticmethod
    def _business_days_since(last_date: date, current_date: date) -> int:
        """Cuenta cuántos días laborales (lunes a viernes) han pasado después de last_date hasta current_date."""
        if current_date <= last_date:
            return 0
        count = 0
        cursor = last_date + timedelta(days=1)
        while cursor <= current_date:
            if cursor.weekday() < 5:
                count += 1
            cursor += timedelta(days=1)
        return count

    @classmethod
    def _should_generate_diary_today(
        cls,
        drafts: Dict[str, Any],
        today: Optional[date] = None,
        interval_business_days: Optional[int] = None
    ) -> bool:
        """
        Determina si hoy toca generar un nuevo borrador automático del Diario de Desarrollo:
        - Solo en días laborales (lunes a viernes).
        - Solo si no hay ya un borrador activo/creado hoy (pending, scheduled, publishing).
        - Respetando la cadencia de cada N días laborales (por defecto 3 días laborales) desde la última publicación.
        """
        today = today or date.today()
        if today.weekday() >= 5:
            return False

        if interval_business_days is None:
            try:
                interval_business_days = int(os.getenv("DEV_DIARY_INTERVAL_BUSINESS_DAYS", "3"))
            except Exception:
                interval_business_days = 3

        today_iso = today.isoformat()
        has_active_or_today = any(
            d_obj.get("created_at", "").startswith(today_iso)
            or d_obj.get("published_at", "").startswith(today_iso)
            or d_obj.get("status") in ("pending", "scheduled", "publishing")
            for d_obj in drafts.values()
        )
        if has_active_or_today:
            return False

        # Buscar la fecha de la última publicación real en borradores o historial
        last_pub_dates = []
        for d_obj in drafts.values():
            if d_obj.get("status") == "published":
                dt_str = (d_obj.get("published_at") or d_obj.get("created_at") or "")[:10]
                if len(dt_str) == 10:
                    try:
                        last_pub_dates.append(date.fromisoformat(dt_str))
                    except Exception:
                        pass

        for rec in AntiBanValidator.get_records():
            if rec.get("status") == "success":
                dt_str = (rec.get("date") or "")[:10]
                if len(dt_str) == 10:
                    try:
                        last_pub_dates.append(date.fromisoformat(dt_str))
                    except Exception:
                        pass

        if not last_pub_dates:
            return True

        latest_pub = max(last_pub_dates)
        return cls._business_days_since(latest_pub, today) >= interval_business_days

    @classmethod
    def _scheduler_worker(cls):
        """
        Hilo daemon de automatización diaria (Lunes a Viernes):
        - 09:30 AM (cada 3 días laborales): genera el borrador del Diario de Desarrollo para aprobar/programar.
        - 09:35 AM (diario laboral): escanea Sevilla y propone 5 contactos de 2º grado en Telegram.
        - 09:40 AM (diario laboral): busca 5 vacantes Easy Apply + CV adaptado y las propone en Telegram.
        - 10:00 AM (o cuando toque scheduled_for): publica automáticamente el borrador programado.
        """
        loops_counter = 0
        while True:
            try:
                cls._update_heartbeat()
                loops_counter += 1
                # Cada ~15 minutos (20 ciclos de 45s) forzar barrido de memoria y purga de temporales
                if loops_counter % 20 == 0:
                    ResourceGovernor.run_full_cleanup(profile_dir=BROWSER_PROFILE_DIR)

                drafts = expire_stale_drafts(max_age_hours=24.0)
                now = datetime.now()
                today_obj = now.date()
                today_iso = today_obj.isoformat()
                is_workday = today_obj.weekday() < 5

                # Cargar estado compartido del scheduler (latidos, propuestas RRHH, Easy Apply)
                sched_state = {}
                if DAILY_SCHEDULER_STATE_FILE.exists():
                    try:
                        sched_state = json.loads(DAILY_SCHEDULER_STATE_FILE.read_text(encoding="utf-8"))
                    except Exception:
                        sched_state = {}

                # 0. Latido preventivo de sesión LinkedIn cada 8 horas (7 días/semana)
                now_ts = time.time()
                last_hb_ts = float(sched_state.get("last_session_heartbeat_ts", 0) or 0)
                if (now_ts - last_hb_ts) >= 28800:
                    sched_state["last_session_heartbeat_ts"] = now_ts
                    DAILY_SCHEDULER_STATE_FILE.write_text(json.dumps(sched_state, indent=2), encoding="utf-8")
                    try:
                        from scripts.session_keeper import run_session_heartbeat
                        run_session_heartbeat(notify_on_ok=False)
                    except Exception as e_hb:
                        print(f"[Scheduler] Aviso en heartbeat de sesión: {e_hb}")
                    finally:
                        ResourceGovernor.run_full_cleanup(profile_dir=BROWSER_PROFILE_DIR)

                # 1. Diario de Desarrollo cada 3 días laborales a partir de las 09:30 AM
                if is_workday and (now.hour > 9 or (now.hour == 9 and now.minute >= 30)):
                    if cls._should_generate_diary_today(drafts, today=today_obj) and AntiBanValidator.check_daily_limit():
                        print(f"[Scheduler] Toca entrada del Diario de Desarrollo (cadencia cada 3 días laborales, {today_iso})...")
                        DevDiaryGenerator.prepare_daily_diary_draft(wait_approval=False)
                        drafts = _get_drafts()

                # 2. Propuesta diaria automática de 5 Contactos RRHH en Sevilla (L-V a partir de las 09:35 AM)
                if is_workday and (now.hour > 9 or (now.hour == 9 and now.minute >= 35)):
                    if sched_state.get("hr_proposed_date") != today_iso:
                        sched_state["hr_proposed_date"] = today_iso
                        DAILY_SCHEDULER_STATE_FILE.write_text(json.dumps(sched_state, indent=2), encoding="utf-8")
                        eng_today = AntiBanValidator.get_today_engagement_summary()
                        if eng_today.get("connection", 0) < MAX_DAILY_CONNECTIONS:
                            print(f"[Scheduler] Escaneando ofertas y preparando propuesta diaria de 5 contactos RRHH ({today_iso})...")
                            try:
                                if not JobScanner.get_today_results():
                                    JobScanner.scan()
                                actions = EngagementEngine.propose_actions()
                                if actions:
                                    global _pending_engagement_actions
                                    _pending_engagement_actions = actions
                                    PENDING_ENGAGEMENT_FILE.write_text(
                                        json.dumps(_pending_engagement_actions, indent=2, ensure_ascii=False),
                                        encoding="utf-8"
                                    )
                                    text_msg, kb_msg = EngagementEngine._build_engagement_message_and_keyboard(actions)
                                    cls._send(text_msg, reply_markup=kb_msg)
                            except Exception as e_hr:
                                print(f"[Scheduler] Aviso preparando propuesta RRHH: {e_hr}")
                            finally:
                                ResourceGovernor.run_full_cleanup(profile_dir=BROWSER_PROFILE_DIR)

                # 3. Búsqueda y propuesta diaria automática de Vacantes Solicitud Sencilla + CV adaptado (L-V a partir de las 09:40 AM)
                if is_workday and (now.hour > 9 or (now.hour == 9 and now.minute >= 40)):
                    if sched_state.get("apply_proposed_date") != today_iso:
                        sched_state["apply_proposed_date"] = today_iso
                        DAILY_SCHEDULER_STATE_FILE.write_text(json.dumps(sched_state, indent=2), encoding="utf-8")
                        print(f"[Scheduler] Buscando vacantes de Solicitud Sencilla con CV adaptado ({today_iso})...")
                        try:
                            jobs = EasyApplyEngine.scan_easy_apply_jobs(max_results=5)
                            if jobs:
                                global _pending_easy_apply_jobs
                                _pending_easy_apply_jobs = jobs
                                text_apply, kb_apply = EasyApplyEngine._build_telegram_message_and_keyboard(jobs)
                                cls._send(text_apply, reply_markup=kb_apply)
                        except Exception as e_app:
                            print(f"[Scheduler] Aviso buscando vacantes Easy Apply: {e_app}")
                        finally:
                            ResourceGovernor.run_full_cleanup(profile_dir=BROWSER_PROFILE_DIR)

                # 4. Publicación automática de borradores programados para las 10:00 AM (confirmados previamente)
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
                            TelegramReviewer.publish_approved_draft(d_id, from_scheduler=True)
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
                cls._update_heartbeat()
                r = http.get(
                    f"{cls.BASE_URL}/getUpdates",
                    params={"offset": last_update_id + 1, "timeout": 10},
                    timeout=15
                )
                if r.status_code != 200:
                    time.sleep(4)
                    continue

                for update in r.json().get("result", []):
                    last_update_id = update["update_id"]

                    # Seguridad: solo responder a nuestro chat
                    update_chat = str(
                        update.get("message", {}).get("chat", {}).get("id", "") or
                        update.get("callback_query", {}).get("message", {}).get("chat", {}).get("id", "") or
                        update.get("callback_query", {}).get("from", {}).get("id", "")
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

                    if cmd in ("/start", "/menu"):
                        cls.cmd_start()
                    elif cmd == "/guia":
                        cls.cmd_guia()
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
                    elif cmd in ("/clear", "/cleardrafts"):
                        cls.cmd_clear_drafts()
                    elif cmd == "/history":
                        cls.cmd_history()
                    elif cmd == "/health":
                        cls.cmd_health()
                    else:
                        cls._send(f"Comando no reconocido: `{cmd}`\nUsa /help o /menu para ver los botones.")

            except KeyboardInterrupt:
                print("\n[Bot] Detenido por el usuario.")
                break
            except Exception as e:
                err_str = str(e)
                if "Read timed out" not in err_str and "Connection reset by peer" not in err_str:
                    print(f"[Bot] Error en loop principal: {e}")
                time.sleep(3)

    @classmethod
    def _register_commands(cls):
        """Registra los comandos en el menu de Telegram (el boton / del chat)."""
        commands = [
            {"command": "menu", "description": "Panel principal con botones rapidos"},
            {"command": "guia", "description": "Guia paso a paso (publicar y limpiar)"},
            {"command": "publish", "description": "Generar nuevo borrador para LinkedIn"},
            {"command": "drafts", "description": "Gestionar, publicar o borrar borradores"},
            {"command": "clear", "description": "Limpiar borradores antiguos o descartados"},
            {"command": "engage", "description": "Proponer 5 contactos Sevilla (2o grado)"},
            {"command": "apply", "description": "Vacantes Solicitud Sencilla + CV adaptado"},
            {"command": "status", "description": "Dashboard de actividad del dia"},
            {"command": "health", "description": "Verificar sesion de LinkedIn"},
            {"command": "history", "description": "Historial de posts, contactos y vacantes"},
            {"command": "limits", "description": "Ver limites anti-ban restantes"},
            {"command": "help", "description": "Lista de comandos"},
        ]
        try:
            http.post(f"{cls.BASE_URL}/setMyCommands",
                      json={"commands": commands}, timeout=10)
        except Exception:
            pass
