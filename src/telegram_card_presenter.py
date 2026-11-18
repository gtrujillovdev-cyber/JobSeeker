"""
Presentador y formateador de tarjetas visuales para Telegram en JobSeekerGA.
Elimina la información críptica, tecnicismos confusos y volcados JSON,
reemplazándolos por tarjetas ejecutivas con barras de progreso y jerarquía clara.
"""

from typing import Dict, Any, List, Optional


def render_progress_bar(percentage: int, total_blocks: int = 10) -> str:
    """Genera una barra de progreso visual tipo [████████░░] 80%."""
    pct = max(0, min(100, int(percentage)))
    filled_blocks = int(round((pct / 100.0) * total_blocks))
    empty_blocks = total_blocks - filled_blocks
    bar = "█" * filled_blocks + "░" * empty_blocks
    return f"[{bar}] {pct}%"


def format_status_card(
    date_str: str,
    anti_ban_status: str,
    cooldown_min: int,
    stats: Dict[str, Any],
    pending_jobs_count: int = 0,
    pending_actions_count: int = 0,
    pending_invites_count: int = 0
) -> str:
    """Genera un panel de estado diario conciso, visual y sin ruido técnico."""
    status_icon = "🟢 Saludable" if anti_ban_status == "OK" else "🟡 En Pausa / Cooldown"
    cooldown_line = f"⏳ Cooldown activo: {cooldown_min} min restantes\n" if cooldown_min > 0 else ""

    lines = [
        "📊 *PANEL DE CONTROL / DASHBOARD · JOBSEEKER*",
        f"📅 Fecha: `{date_str}`",
        f"🛡️ Estado del Bot: *{status_icon}*",
        cooldown_line,
        "━━━━━━━━━━━━━━━━━━━━━━",
        "📈 *Actividad de Hoy*",
        f" • 🎯 Candidaturas enviadas: *{stats.get('applications', 0)}*",
        f" • 🤝 Conexiones enviadas: *{stats.get('connections', 0)}*",
        f" • 📥 Invitaciones aceptadas: *{stats.get('invitations_accepted', 0)}*",
        f" • 💬 Interacciones / Posts publicados: *{stats.get('interactions', 0)}*",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "📬 *Pendientes de tu Aprobación*",
        f" • 💼 Candidaturas Easy Apply: *{pending_jobs_count}*",
        f" • 🤝 Acciones de Networking: *{pending_actions_count}*",
        f" • 📩 Invitaciones Recibidas: *{pending_invites_count}*",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "💡 _Escribe /help para ver las acciones rápidas disponibles._"
    ]
    return "\n".join(line for line in lines if line)


def format_job_card(job: Dict[str, Any], index: int = 1, total: int = 1) -> str:
    """Genera una tarjeta limpia y enfocada para una oferta Easy Apply."""
    title = job.get("title", "Puesto sin título")
    company = job.get("company", "Empresa desconocida")
    location = job.get("location", "Ubicación no especificada")
    score = job.get("ats_score", job.get("score", 0))
    cv_used = job.get("cv_route", job.get("cv_name", "CV Principal"))
    matched_skills = job.get("matched_skills", [])
    gaps = job.get("missing_skills", [])

    progress = render_progress_bar(score)

    skills_str = ", ".join(matched_skills[:4]) if matched_skills else "Perfil compatible"
    gaps_str = ", ".join(gaps[:3]) if gaps else "Ninguno crítico"

    lines = [
        f"💼 *OPORTUNIDAD DETECTADA* ({index}/{total})",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"🏢 *{company}*",
        f"📌 *Puesto:* {title}",
        f"📍 *Ubicación:* {location}",
        "",
        f"🎯 *Compatibilidad ATS:*",
        f"`{progress}`",
        f"📄 *Currículum asignado:* `{cv_used}`",
        "",
        f"✅ *Puntos fuertes:* {skills_str}",
        f"⚠️ *Gaps identificados:* {gaps_str}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "¿Deseas que el bot presente tu candidatura?"
    ]
    return "\n".join(lines)


def format_invitation_card(invite: Dict[str, Any], index: int = 1, total: int = 1) -> str:
    """Genera una tarjeta elegante y comprensible para una invitación recibida en LinkedIn."""
    name = invite.get("name", "Usuario de LinkedIn")
    title = invite.get("title", "Sin cargo especificado")
    company = invite.get("company", "")
    category = invite.get("category", "General")
    note = invite.get("note", "").strip()

    # Identificación amigable de categoría
    badge_map = {
        "recruiter": "🎯 Reclutador / Headhunter",
        "engineering": "💻 Perfil Técnico / Colega IT",
        "founder": "🚀 Fundador / Directivo",
        "sales": "📢 Ventas / Comercial",
        "general": "🌐 Contacto General"
    }
    category_label = badge_map.get(category.lower(), "🌐 Contacto Profesional")

    lines = [
        f"📩 *SOLICITUD DE CONEXIÓN* ({index}/{total})",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"👤 *{name}*",
        f"💼 *Cargo:* {title}" + (f" en *{company}*" if company else ""),
        f"🏷️ *Categoría detectada:* {category_label}",
    ]

    if note:
        lines.extend([
            "",
            "📝 *Mensaje adjunto:*",
            f"> _{note}_"
        ])

    lines.extend([
        "━━━━━━━━━━━━━━━━━━━━━━",
        "¿Qué acción deseas tomar?"
    ])
    return "\n".join(lines)


def format_simple_notification(title: str, message: str, level: str = "info") -> str:
    """
    Notificación concisa para avisos de sistema, evitando volcados técnicos.
    Niveles: 'success', 'warning', 'error', 'info'
    """
    icons = {
        "success": "✅",
        "warning": "⚠️",
        "error": "🚨",
        "info": "ℹ️"
    }
    icon = icons.get(level, "ℹ️")
    return f"{icon} *{title}*\n\n{message}"
