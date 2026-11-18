#!/usr/bin/env python3
"""
Latido diario de sesión LinkedIn.
Corre a las 08:00 via LaunchAgent en mbp1.
- Abre el feed de LinkedIn en headless con el perfil persistente.
- Si la sesión sigue activa: re-exporta storage_clean.json (refresca TTL).
- Si expiró: alerta por Telegram y sale con código 1.
"""

import sys
import time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import (
    BROWSER_PROFILE_DIR, STORAGE_STATE_FILE,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
)
from src.browser_helper import (
    get_playwright_browser_context,
    persist_browser_session,
    get_li_at_expiry_days,
    close_playwright_context,
)

LOG_FILE = Path(__file__).resolve().parent.parent / "logs" / "session_keeper.log"


def _log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _notify(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        import requests
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"},
            timeout=10
        )
    except Exception as e:
        _log(f"[!] Telegram notify error: {e}")


def _probe_linkedin_session_once() -> tuple[bool, str, bool]:
    """
    Intenta una vez abrir el Feed de LinkedIn con el contexto actual y devuelve:
    (is_valid_session, final_url, exported_ok)
    """
    from playwright.sync_api import sync_playwright

    context = None
    browser_instance = None
    try:
        with sync_playwright() as p:
            context, browser_instance = get_playwright_browser_context(p)
            page = context.pages[0] if context.pages else context.new_page()

            _log("[*] Navegando a LinkedIn Feed...")
            page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=35000)
            time.sleep(3.5)

            # Actividad mínima pasiva para permitir rotación natural de cookies/CSRF
            try:
                page.mouse.wheel(0, 240)
                time.sleep(1.5)
            except Exception:
                pass

            current_url = page.url.lower()
            cookies = context.cookies("https://www.linkedin.com")
            has_li_at = any(c.get("name") == "li_at" and len(c.get("value", "")) > 10 for c in cookies)
            at_feed = "/feed" in current_url and not any(
                k in current_url for k in ("login", "authwall", "checkpoint")
            )

            # Si hubo redirección puntual pero la cookie li_at existe, reintentar navegación dentro de la misma sesión
            if has_li_at and not at_feed:
                time.sleep(2.0)
                page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
                time.sleep(3.0)
                current_url = page.url.lower()
                cookies = context.cookies("https://www.linkedin.com")
                has_li_at = any(c.get("name") == "li_at" and len(c.get("value", "")) > 10 for c in cookies)
                at_feed = "/feed" in current_url and not any(
                    k in current_url for k in ("login", "authwall", "checkpoint")
                )

            if has_li_at and at_feed:
                exported = persist_browser_session(context, storage_state_file=STORAGE_STATE_FILE)
                close_playwright_context(context, browser_instance, persist=False)
                return True, current_url, exported

            close_playwright_context(context, browser_instance, persist=False)
            return False, f"{current_url} | li_at={has_li_at}", False
    except Exception as e:
        close_playwright_context(context, browser_instance, persist=False)
        return False, f"exception: {e}", False


def run_session_heartbeat(notify_on_ok: bool = False) -> bool:
    """
    Abre LinkedIn feed headless usando storage_clean.json / storage_state.json,
    verifica la sesión con doble comprobación antes de alertar y persiste las cookies refrescadas.
    """
    _log("[*] Iniciando heartbeat de sesión LinkedIn...")

    clean_storage = STORAGE_STATE_FILE.parent / "storage_clean.json"
    if not clean_storage.exists() and not STORAGE_STATE_FILE.exists() and not BROWSER_PROFILE_DIR.exists():
        _log("[!] No existe perfil ni storage_state. Ejecuta scripts/setup_linkedin_session.py primero.")
        return False

    last_diag = ""
    for attempt in (1, 2):
        is_valid, diag, exported = _probe_linkedin_session_once()
        last_diag = diag
        if is_valid:
            if exported:
                days_left = get_li_at_expiry_days(STORAGE_STATE_FILE)
                days_txt = f"{days_left:.0f} días restantes" if days_left is not None else "TTL desconocido"
                _log(f"[OK] Sesión activa. storage_clean.json/storage_state.json refrescados ({days_txt}).")
                if days_left is not None and days_left <= 7:
                    _notify(
                        f"⚠️ *Aviso JobSeekerGA — Cookie LinkedIn próxima a expirar*\n"
                        f"Quedan *{days_left:.1f} días* de validez en `li_at`.\n"
                        f"Conviene renovar ejecutando `python scripts/setup_linkedin_session.py`."
                    )
                elif notify_on_ok:
                    _notify(
                        f"*JobSeekerGA - Sesión LinkedIn*\n"
                        f"Latido OK a las `{datetime.now().strftime('%H:%M')}` ({days_txt})."
                    )
                return True
            else:
                _log("[!] Feed cargado pero falló exportando cookies.")
                return False

        if attempt == 1:
            _log(f"[*] Primer intento de heartbeat no cargó el feed ({diag[:80]}). Reintentando en 5s para descartar fallo transitorio...")
            time.sleep(5)

    _log(f"[!] SESIÓN EXPIRADA CONFIRMADA TRAS 2 INTENTOS. Detalle: {last_diag[:100]}")
    _notify(
        f"*ALERTA JobSeekerGA - Sesión LinkedIn EXPIRADA*\n\n"
        f"El bot no puede publicar hasta que renueves la sesión.\n\n"
        f"Desde tu Mac ejecuta:\n"
        f"`python scripts/setup_linkedin_session.py`\n\n"
        f"Detalle: `{last_diag[:70]}`"
    )
    return False


if __name__ == "__main__":
    notify_flag = "--notify-ok" in sys.argv
    ok = run_session_heartbeat(notify_on_ok=notify_flag)
    sys.exit(0 if ok else 1)
