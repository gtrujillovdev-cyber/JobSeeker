"""
Helper universal para inicialización de navegadores Playwright.
Soporta tanto contextos persistentes tradicionales como contextos limpios con storage_state
para máxima compatibilidad entre máquinas (macOS 11, servidores headless Linux y nubes gratuitas).
"""

import os
from typing import Tuple, Any
from pathlib import Path
from config import (
    BROWSER_PROFILE_DIR, STORAGE_STATE_FILE, HEADLESS,
    BROWSER_CHANNEL, CHROMIUM_EXECUTABLE_PATH
)

def get_playwright_browser_context(p: Any) -> Tuple[Any, Any]:
    """
    Inicializa y retorna (context, browser_or_none):
    1. Si existe storage_state.json (o storage_clean.json), lanza un browser headless estándar
       inyectando las cookies, evitando fallos de descifrado del keychain de Chromium.
    2. Fallback a launch_persistent_context con el directorio de usuario.
    """
    clean_storage = STORAGE_STATE_FILE.parent / "storage_clean.json"
    active_storage = clean_storage if clean_storage.exists() else STORAGE_STATE_FILE

    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox"
    ]
    if CHROMIUM_EXECUTABLE_PATH:
        launch_args.extend(["--headless=old", "--disable-gpu"])

    launch_kwargs: dict = {
        "headless": HEADLESS,
        "args": launch_args
    }
    if CHROMIUM_EXECUTABLE_PATH:
        launch_kwargs["executable_path"] = CHROMIUM_EXECUTABLE_PATH
    elif BROWSER_CHANNEL:
        launch_kwargs["channel"] = BROWSER_CHANNEL

    # Estrategia 1: Storage State (Inyección universal de sesión sin depender del keychain local)
    if active_storage.exists():
        try:
            browser = p.chromium.launch(**launch_kwargs)
            ctx = browser.new_context(
                storage_state=str(active_storage),
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 900}
            )
            return ctx, browser
        except Exception as e:
            print(f"[BrowserHelper] Aviso usando storage_state ({e}). Probando contexto persistente...")

    # Estrategia 2: Contexto persistente estándar
    persistent_kwargs = dict(launch_kwargs)
    persistent_kwargs.update({
        "user_data_dir": str(BROWSER_PROFILE_DIR),
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "viewport": {"width": 1280, "height": 900}
    })
    ctx = p.chromium.launch_persistent_context(**persistent_kwargs)
    return ctx, None
