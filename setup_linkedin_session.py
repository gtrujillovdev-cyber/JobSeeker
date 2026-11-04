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
            print("👉 El asistente detectará AUTOMÁTICAMENTE cuando entres en tu Feed.")
            print("-" * 65)

            logged_in = False
            for i in range(120): # hasta 4 minutos de espera activa
                time.sleep(2)
                try:
                    current_url = page.url
                    if "/feed" in current_url and "login" not in current_url and "checkpoint" not in current_url:
                        # Verificar que el feed o la barra de navegación existe
                        nav_found = page.locator("#global-nav, .global-nav, .feed-identity-module, div.feed-shared-update-v2").count() > 0
                        if nav_found:
                            logged_in = True
                            print("\n[✓] ¡SESIÓN DETECTADA CON ÉXITO! Estás dentro de LinkedIn.")
                            break
                    elif i % 5 == 0:
                        print(f"[*] Esperando inicio de sesión... (URL actual: {current_url[:50]}...)")
                except Exception:
                    pass

            if not logged_in:
                print("\n[?] ¿Ya has iniciado sesión y ves tu feed de publicaciones?")
                input("Pulsa [ENTER] aquí en la terminal para confirmar y guardar: ")

            time.sleep(2)

            # Guardar storage_state
            context.storage_state(path=str(STORAGE_STATE_FILE))
            
            cookies = context.cookies()
            has_li_at = any(c["name"] == "li_at" for c in cookies)

            context.close()

            print("\n" + "=" * 65)
            if has_li_at:
                print("[✓] ¡Sesión de LinkedIn sellada y guardada con éxito en Google Chrome!")
                print(f"[✓] Storage state exportado en: {STORAGE_STATE_FILE}")
            else:
                print("[⚠️] Advertencia: No se detectó la cookie 'li_at'. Asegúrate de haber iniciado sesión.")
            print("=" * 65 + "\n")

    except Exception as e:
        print(f"[!] Error iniciando el asistente: {e}")

if __name__ == "__main__":
    setup_linkedin_session()
