#!/usr/bin/env python3
"""
Asistente interactivo de inicio de sesión en LinkedIn.
Abre una ventana visible de Google Chrome con perfil persistente local.
Detecta automáticamente cuando el usuario completa el login y entra en su Feed.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import BROWSER_PROFILE_DIR, STORAGE_STATE_FILE, BROWSER_CHANNEL, CHROMIUM_EXECUTABLE_PATH
from playwright.sync_api import sync_playwright

def setup_linkedin_session():
    BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 65)
    print(" 💼 ASISTENTE DE SESIÓN PERSISTENTE DE LINKEDIN")
    print("=" * 65)
    print(f"[*] Perfil persistente en: {BROWSER_PROFILE_DIR}")
    print("[*] Abriendo navegador visible...")

    try:
        with sync_playwright() as p:
            launch_kwargs = {
                "user_data_dir": str(BROWSER_PROFILE_DIR),
                "headless": False,
                "viewport": {"width": 1280, "height": 850},
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox"
                ]
            }
            if CHROMIUM_EXECUTABLE_PATH:
                launch_kwargs["executable_path"] = CHROMIUM_EXECUTABLE_PATH
            elif BROWSER_CHANNEL:
                launch_kwargs["channel"] = BROWSER_CHANNEL

            context = p.chromium.launch_persistent_context(**launch_kwargs)

            page = context.pages[0] if context.pages else context.new_page()
            print("[*] Navegando a LinkedIn Feed...")
            page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")

            print("\n" + "-" * 65)
            print("👉 Si ves la pantalla '¡Hola de nuevo!' o el formulario de login:")
            print("   1. Introduce tu contraseña en la ventana de Chrome.")
            print("   2. Haz clic en 'Iniciar sesión' (y pasa el 2FA si te lo pide).")
            print("👉 En cuanto entres en tu Feed (o cuando pulses [ENTER] aquí), se guardará automáticamente.")
            print("-" * 65)

            import select
            logged_in = False
            for i in range(120): # hasta 4 minutos de espera activa
                time.sleep(1.5)
                try:
                    # Si el usuario pulsa ENTER en cualquier momento, guardar de inmediato
                    if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
                        sys.stdin.readline()
                        logged_in = True
                        break
                except Exception:
                    pass
                try:
                    current_url = page.url
                    cookies_now = context.cookies("https://www.linkedin.com")
                    has_cookie = any(c.get("name") == "li_at" and len(c.get("value", "")) > 10 for c in cookies_now)
                    if has_cookie and "/feed" in current_url and "login" not in current_url and "checkpoint" not in current_url:
                        logged_in = True
                        print("\n[✓] ¡SESIÓN Y COOKIE 'li_at' DETECTADAS! Guardando estado...")
                        break
                    elif i % 5 == 0:
                        print(f"[*] Esperando inicio de sesión... (URL: {current_url[:50]} | cookie li_at: {has_cookie})")
                except Exception:
                    pass

            if not logged_in:
                print("\n[?] ¿Ya has iniciado sesión y ves tu feed de publicaciones?")
                input("Pulsa [ENTER] aquí en la terminal para confirmar y guardar: ")

            time.sleep(2)

            # Guardar storage_state y storage_clean.json (con expires y origins intactos)
            from src.browser_helper import persist_browser_session
            persist_browser_session(context, storage_state_file=STORAGE_STATE_FILE)

            cookies = context.cookies()
            has_li_at = any(c["name"] == "li_at" for c in cookies)

            context.close()

            print("\n" + "=" * 65)
            if has_li_at:
                print("[✓] ¡Sesión de LinkedIn sellada y guardada con éxito en Google Chrome!")
                print(f"[✓] Storage state exportado en: {STORAGE_STATE_FILE}")
                sync_to_mbp1()
            else:
                print("[⚠️] Advertencia: No se detectó la cookie 'li_at'. Asegúrate de haber iniciado sesión.")
            print("=" * 65 + "\n")

    except Exception as e:
        print(f"[!] Error iniciando el asistente: {e}")

def sync_to_mbp1():
    import subprocess
    print("[*] Sincronizando sesión a mbp1...")
    try:
        cmd = [
            "scp", "-o", "ConnectTimeout=5",
            str(STORAGE_STATE_FILE),
            str(STORAGE_STATE_FILE.parent / "storage_clean.json"),
            "mbp1:/Users/GabrielTrujilloVallejo/Developer/Projects/JobSeekerGA/assets/.browser_profiles/"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if res.returncode == 0:
            print("[✓] Sesión sincronizada con éxito en mbp1.")
        else:
            print(f"[!] Aviso sincronizando a mbp1: {res.stderr}")
    except Exception as e:
        print(f"[!] No se pudo sincronizar automáticamente a mbp1: {e}")

def save_cookie_direct(li_at_val: str):
    import json
    val = li_at_val.strip().strip('"').strip("'")
    if not val:
        print("[!] Valor de cookie 'li_at' vacío.")
        return False

    STORAGE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    cookie_obj = {
        "name": "li_at",
        "value": val,
        "domain": ".linkedin.com",
        "path": "/",
        "httpOnly": True,
        "secure": True,
        "sameSite": "None"
    }

    state_data = {
        "cookies": [cookie_obj],
        "origins": []
    }
    STORAGE_STATE_FILE.write_text(json.dumps(state_data, indent=2), encoding="utf-8")

    clean_path = STORAGE_STATE_FILE.parent / "storage_clean.json"
    clean_cookie = {
        "name": "li_at",
        "value": val,
        "domain": ".www.linkedin.com",
        "path": "/",
        "httpOnly": True,
        "secure": True,
        "sameSite": "Lax"
    }
    clean_path.write_text(json.dumps({"cookies": [clean_cookie], "origins": []}, indent=2), encoding="utf-8")

    print("\n" + "=" * 65)
    print(f"[✓] Cookie 'li_at' inyectada directamente en {STORAGE_STATE_FILE.name}")
    print("=" * 65)
    sync_to_mbp1()

    # Comprobación inmediata de salud
    try:
        from src.linkedin_publisher import LinkedInPublisher
        health = LinkedInPublisher.check_session_health()
        print(f"[*] Comprobación local: {health}")
    except Exception as e:
        print(f"[*] Aviso verificando local: {e}")
    return True

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("--cookie", "-c") and len(sys.argv) > 2:
        save_cookie_direct(sys.argv[2])
    elif len(sys.argv) > 1 and sys.argv[1] in ("--sync", "-s"):
        sync_to_mbp1()
    else:
        setup_linkedin_session()
