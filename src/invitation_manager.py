"""
Gestor de invitaciones entrantes de LinkedIn para JobSeekerGA.
Inspecciona solicitudes de conexion recibidas, clasifica los perfiles (Recruiter, IT, Founder, Sales)
y permite aceptarlas automaticamente o mediante aprobacion en Telegram con proteccion anti-ban.
"""

import time
import re
from typing import List, Dict, Any, Optional
from pathlib import Path

from config import BROWSER_PROFILE_DIR
from src.anti_ban import AntiBanValidator


class InvitationManager:
    """Gestiona y califica las solicitudes de contacto recibidas en LinkedIn."""

    INVITATIONS_URL = "https://www.linkedin.com/mynetwork/invitation-manager/"

    # Clasificadores heurísticos basados en palabras clave
    KEYWORDS_RECRUITER = [
        "recruiter", "talent", "hr", "headhunter", "talent acquisition",
        "hiring", "rrhh", "recursos humanos", "people partner", "selector"
    ]
    KEYWORDS_ENGINEERING = [
        "developer", "software", "engineer", "ingeniero", "architect",
        "devops", "cloud", "sysadmin", "sre", "data", "ai", "fullstack", "backend"
    ]
    KEYWORDS_FOUNDER = [
        "founder", "co-founder", "ceo", "cto", "cio", "director", "head of", "vp"
    ]
    KEYWORDS_SALES = [
        "sales", "account executive", "bdr", "sdr", "ventas", "comercial", "broker"
    ]

    @classmethod
    def classify_profile(cls, title: str, note: str = "") -> str:
        """
        Determina la categoría del perfil entrante según su titulación y nota adjunta.
        Retorna: 'recruiter', 'engineering', 'founder', 'sales', o 'general'.
        """
        text = f"{title} {note}".lower()

        for kw in cls.KEYWORDS_RECRUITER:
            if kw in text:
                return "recruiter"
        for kw in cls.KEYWORDS_FOUNDER:
            if kw in text:
                return "founder"
        for kw in cls.KEYWORDS_ENGINEERING:
            if kw in text:
                return "engineering"
        for kw in cls.KEYWORDS_SALES:
            if kw in text:
                return "sales"

        return "general"

    @classmethod
    def scan_inbound_invitations(cls, max_scan: int = 5) -> List[Dict[str, Any]]:
        """
        Abre el navegador, navega a la sección de invitaciones recibidas y
        extrae los datos de las personas que nos han enviado solicitud.
        """
        can_proceed, reason = AntiBanValidator.check_action_limit("invitation_check")
        if not can_proceed:
            print(f"[InvitationManager] Anti-ban limit alcanzado: {reason}")
            return []

        from playwright.sync_api import sync_playwright

        results: List[Dict[str, Any]] = []

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch_persistent_context(
                    user_data_dir=str(BROWSER_PROFILE_DIR),
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled"]
                )
                page = browser.new_page()

                print(f"[InvitationManager] Navegando a {cls.INVITATIONS_URL}...")
                page.goto(cls.INVITATIONS_URL, wait_until="domcontentloaded", timeout=30000)
                time.sleep(3.0)

                # Extraer tarjetas de invitaciones mediante evaluación en el DOM
                raw_invitations = page.evaluate("""() => {
                    const cards = Array.from(document.querySelectorAll('.invitation-card, li.invitation-card, [data-view-name="invitation-card"]'));
                    return cards.slice(0, 10).map((c, index) => {
                        const nameEl = c.querySelector('.invitation-card__title, .app-aware-link span[aria-hidden="true"]');
                        const titleEl = c.querySelector('.invitation-card__subtitle, .invitation-card__occupation');
                        const noteEl = c.querySelector('.invitation-card__custom-message, .invitation-card__message');
                        const btnAccept = c.querySelector('button[aria-label*="Aceptar"], button[aria-label*="Accept"], button.artdeco-button--secondary');

                        return {
                            id: `inv_${index}_${Date.now()}`,
                            name: nameEl ? nameEl.innerText.trim() : 'Contacto LinkedIn',
                            title: titleEl ? titleEl.innerText.trim() : '',
                            note: noteEl ? noteEl.innerText.trim() : '',
                            has_accept_button: !!btnAccept
                        };
                    });
                }""")

                browser.close()

                for raw in raw_invitations[:max_scan]:
                    category = cls.classify_profile(raw.get("title", ""), raw.get("note", ""))
                    results.append({
                        "id": raw["id"],
                        "name": raw["name"],
                        "title": raw["title"],
                        "note": raw["note"],
                        "category": category,
                        "raw_data": raw
                    })

                AntiBanValidator.record_engagement("invitation_check", "LinkedIn", f"Escaneadas {len(results)} invitaciones")

        except Exception as e:
            print(f"[InvitationManager] Error escaneando invitaciones: {e}")

        return results

    @classmethod
    def accept_invitation(cls, invitation_id: str, sender_name: str) -> bool:
        """
        Ejecuta el clic para aceptar la invitación en LinkedIn de manera segura con Playwright.
        """
        can_proceed, reason = AntiBanValidator.check_action_limit("connection")
        if not can_proceed:
            print(f"[InvitationManager] Bloqueo anti-ban al aceptar: {reason}")
            return False

        from playwright.sync_api import sync_playwright

        accepted = False
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch_persistent_context(
                    user_data_dir=str(BROWSER_PROFILE_DIR),
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled"]
                )
                page = browser.new_page()
                page.goto(cls.INVITATIONS_URL, wait_until="domcontentloaded", timeout=30000)
                time.sleep(2.5)

                # Intentar pulsar el botón de aceptar correspondiente al remitente o primer elemento
                clicked = page.evaluate("""(targetName) => {
                    const cards = Array.from(document.querySelectorAll('.invitation-card, li.invitation-card, [data-view-name="invitation-card"]'));
                    for (let c of cards) {
                        const nameEl = c.querySelector('.invitation-card__title, .app-aware-link');
                        const cardName = nameEl ? nameEl.innerText.trim() : '';
                        
                        // Si coincide el nombre o si no hay especificado, pulsamos el botón
                        if (!targetName || cardName.toLowerCase().includes(targetName.toLowerCase())) {
                            const btnAccept = c.querySelector('button[aria-label*="Aceptar"], button[aria-label*="Accept"], button.artdeco-button--secondary');
                            if (btnAccept && !btnAccept.disabled) {
                                btnAccept.click();
                                return true;
                            }
                        }
                    }
                    return false;
                }""", sender_name)

                if clicked:
                    time.sleep(2.0)
                    accepted = True
                    AntiBanValidator.record_engagement("connection", "Inbound Network", f"Aceptada invitación de {sender_name}")
                    print(f"[InvitationManager] [✓] Invitación de {sender_name} aceptada exitosamente.")

                browser.close()

        except Exception as e:
            print(f"[InvitationManager] Error aceptando invitación: {e}")

        return accepted
