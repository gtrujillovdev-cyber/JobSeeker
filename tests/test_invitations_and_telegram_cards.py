"""
Tests para el formateador de tarjetas de Telegram y el clasificador de invitaciones.
"""

import pytest
from src.telegram_card_presenter import (
    render_progress_bar,
    format_status_card,
    format_job_card,
    format_invitation_card,
    format_simple_notification
)
from src.invitation_manager import InvitationManager


def test_render_progress_bar():
    bar_0 = render_progress_bar(0, total_blocks=10)
    assert "[░░░░░░░░░░] 0%" in bar_0

    bar_50 = render_progress_bar(50, total_blocks=10)
    assert "[█████░░░░░] 50%" in bar_50

    bar_100 = render_progress_bar(100, total_blocks=10)
    assert "[██████████] 100%" in bar_100


def test_format_status_card():
    card = format_status_card(
        date_str="2026-11-18",
        anti_ban_status="OK",
        cooldown_min=0,
        stats={
            "applications": 3,
            "connections": 2,
            "invitations_accepted": 1,
            "interactions": 4
        },
        pending_jobs_count=2,
        pending_actions_count=1,
        pending_invites_count=3
    )
    assert "PANEL DE CONTROL" in card
    assert "2026-11-18" in card
    assert "🟢 Saludable" in card
    assert "Candidaturas enviadas: *3*" in card
    assert "Invitaciones Recibidas: *3*" in card


def test_format_job_card():
    job = {
        "title": "Senior DevOps Engineer",
        "company": "CloudTech Solutions",
        "location": "Sevilla / Remoto",
        "ats_score": 85,
        "cv_route": "GTVCV_2027.pdf",
        "matched_skills": ["Linux", "Kubernetes", "AWS", "Terraform"],
        "missing_skills": ["Ansible"]
    }
    card = format_job_card(job, index=1, total=5)
    assert "*OPORTUNIDAD DETECTADA* (1/5)" in card
    assert "CloudTech Solutions" in card
    assert "Senior DevOps Engineer" in card
    assert "GTVCV_2027.pdf" in card
    assert "Linux, Kubernetes, AWS, Terraform" in card


def test_format_invitation_card():
    invite = {
        "name": "Laura Gómez",
        "title": "Senior IT Recruiter en TechHunters",
        "category": "recruiter",
        "note": "Hola Gabriel, he visto tu perfil y encajas con una vacante Cloud."
    }
    card = format_invitation_card(invite, index=1, total=1)
    assert "SOLICITUD DE CONEXIÓN" in card
    assert "Laura Gómez" in card
    assert "Senior IT Recruiter" in card
    assert "🎯 Reclutador / Headhunter" in card
    assert "Hola Gabriel, he visto tu perfil" in card


def test_format_simple_notification():
    msg = format_simple_notification("Alerta del Sistema", "Acción completada con éxito.", level="success")
    assert "✅ *Alerta del Sistema*" in msg
    assert "Acción completada con éxito." in msg


def test_invitation_manager_classification():
    # Recruiter
    cat1 = InvitationManager.classify_profile("Talent Acquisition Specialist", "Buscamos desarrolladores")
    assert cat1 == "recruiter"

    # Founder / Directivo
    cat2 = InvitationManager.classify_profile("CTO & Co-Founder en Startup", "")
    assert cat2 == "founder"

    # Engineering / IT Peer
    cat3 = InvitationManager.classify_profile("Senior Backend Software Engineer", "")
    assert cat3 == "engineering"

    # Sales
    cat4 = InvitationManager.classify_profile("Account Executive / Sales B2B", "")
    assert cat4 == "sales"

    # General
    cat5 = InvitationManager.classify_profile("Consultor Estratégico", "")
    assert cat5 == "general"
