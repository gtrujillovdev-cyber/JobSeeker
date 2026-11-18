"""
Helper universal para inicialización de navegadores Playwright.
Soporta tanto contextos persistentes tradicionales como contextos limpios con storage_state
para máxima compatibilidad entre máquinas (macOS 11, servidores headless Linux y nubes gratuitas).
"""

import json
import threading
import time
from typing import Tuple, Any, List, Dict, Optional
from pathlib import Path
from config import (
    BROWSER_PROFILE_DIR, STORAGE_STATE_FILE, HEADLESS,
    BROWSER_CHANNEL, CHROMIUM_EXECUTABLE_PATH
)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

_COOKIE_ALLOWED_KEYS = {
    "name", "value", "domain", "path", "httpOnly", "secure", "sameSite", "expires"
}
_TRANSIENT_COOKIE_NAMES = {"__cf_bm", "AnalyticsSyncHistory", "UserMatchHistory"}
_STORAGE_LOCK = threading.Lock()


def has_linkedin_session() -> bool:
    """Indica si existe alguna sesión guardada (storage_clean, storage_state o perfil persistente)."""
    clean_storage = STORAGE_STATE_FILE.parent / "storage_clean.json"
    return clean_storage.exists() or STORAGE_STATE_FILE.exists() or BROWSER_PROFILE_DIR.exists()


def sanitize_cookies(cookies: List[Dict[str, Any]], drop_transient: bool = False) -> List[Dict[str, Any]]:
    """Normaliza cookies para Playwright conservando expires y filtrando entradas conflictivas."""
    sanitized: List[Dict[str, Any]] = []
    for c in cookies or []:
        if not isinstance(c, dict):
            continue
        if c.get("partitionKey") or c.get("_crHasCrossSiteAncestor"):
            continue
        if drop_transient and c.get("name") in _TRANSIENT_COOKIE_NAMES:
            continue
        c_clean = {k: v for k, v in c.items() if k in _COOKIE_ALLOWED_KEYS}
        if c_clean.get("sameSite") not in ("Strict", "Lax", "None"):
            c_clean["sameSite"] = "Lax"
        sanitized.append(c_clean)
    return sanitized


def _atomic_write_json(target_path: Path, payload: Dict[str, Any]) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_suffix(target_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(target_path)


def persist_browser_session(context: Any, storage_state_file: Optional[Path] = None) -> bool:
    """
    Persiste de forma atómica y thread-safe las cookies/origins actuales en
    storage_state.json y storage_clean.json, solo si li_at sigue presente y válida.
    """
    state_file = storage_state_file or STORAGE_STATE_FILE
    clean_file = state_file.parent / "storage_clean.json"

    try:
        cookies = context.cookies("https://www.linkedin.com")
        li_at = next(
            (c for c in cookies if c.get("name") == "li_at" and len(c.get("value", "")) > 10),
            None
        )
        if not li_at:
            return False

        with _STORAGE_LOCK:
            prev_expirations = {}
            if state_file.exists():
                try:
                    prev_raw = json.loads(state_file.read_text(encoding="utf-8"))
                    for pc in prev_raw.get("cookies", []):
                        exp_val = pc.get("expires")
                        if isinstance(exp_val, (int, float)) and exp_val > 0:
                            prev_expirations[(pc.get("name"), pc.get("domain"), pc.get("value"))] = exp_val
                except Exception:
                    prev_expirations = {}

            tmp_state = state_file.with_suffix(".json.tmp")
            state_file.parent.mkdir(parents=True, exist_ok=True)
            context.storage_state(path=str(tmp_state))
            raw_state = json.loads(tmp_state.read_text(encoding="utf-8"))
            for rc in raw_state.get("cookies", []):
                if not (isinstance(rc.get("expires"), (int, float)) and rc["expires"] > 0):
                    prev_exp = prev_expirations.get((rc.get("name"), rc.get("domain"), rc.get("value")))
                    if prev_exp:
                        rc["expires"] = prev_exp

            _atomic_write_json(state_file, raw_state)
            tmp_state.unlink(missing_ok=True)

            clean_cookies = sanitize_cookies(raw_state.get("cookies", cookies), drop_transient=True)
            origins = raw_state.get("origins", [])
            _atomic_write_json(clean_file, {"cookies": clean_cookies, "origins": origins})
        return True
    except Exception as e:
        print(f"[BrowserHelper] Aviso persistiendo sesión: {e}")
        return False


def get_li_at_expiry_days(storage_state_file: Optional[Path] = None) -> Optional[float]:
    """Devuelve los días restantes hasta la expiración de la cookie li_at, o None si no consta."""
    state_file = storage_state_file or STORAGE_STATE_FILE
    clean_file = state_file.parent / "storage_clean.json"
    for candidate in (clean_file, state_file):
        if not candidate.exists():
            continue
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
            li_at = next((c for c in data.get("cookies", []) if c.get("name") == "li_at"), None)
            if li_at and isinstance(li_at.get("expires"), (int, float)) and li_at["expires"] > 0:
                return (li_at["expires"] - time.time()) / 86400.0
        except Exception:
            continue
    return None


def close_playwright_context(
    context: Any,
    browser_instance: Any = None,
    persist: bool = False,
    storage_state_file: Optional[Path] = None
) -> None:
    """Persiste opcionalmente cookies válidas y cierra contexto y navegador sin dejar huérfanos."""
    if persist and context is not None:
        persist_browser_session(context, storage_state_file=storage_state_file)
    try:
        if context is not None:
            context.close()
    except Exception:
        pass
    try:
        if browser_instance is not None:
            browser_instance.close()
    except Exception:
        pass


def get_playwright_browser_context(p: Any) -> Tuple[Any, Any]:
    """
    Inicializa y retorna (context, browser_or_none):
    1. Si existe storage_state.json (o storage_clean.json), lanza un browser headless estándar
       inyectando cookies y origins, evitando fallos de descifrado del keychain de Chromium.
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
            raw_state = json.loads(active_storage.read_text(encoding="utf-8"))
            sanitized_cookies = sanitize_cookies(raw_state.get("cookies", []))
            origins = raw_state.get("origins", [])
            if not origins and STORAGE_STATE_FILE.exists():
                try:
                    origins = json.loads(STORAGE_STATE_FILE.read_text(encoding="utf-8")).get("origins", [])
                except Exception:
                    origins = []
            browser = p.chromium.launch(**launch_kwargs)
            ctx = browser.new_context(
                storage_state={"cookies": sanitized_cookies, "origins": origins},
                user_agent=USER_AGENT,
                viewport={"width": 1280, "height": 900}
            )
            return ctx, browser
        except Exception as e:
            print(f"[BrowserHelper] Aviso usando storage_state ({e}). Probando contexto persistente...")

    # Estrategia 2: Contexto persistente estándar
    persistent_kwargs = dict(launch_kwargs)
    persistent_kwargs.update({
        "user_data_dir": str(BROWSER_PROFILE_DIR),
        "user_agent": USER_AGENT,
        "viewport": {"width": 1280, "height": 900}
    })
    ctx = p.chromium.launch_persistent_context(**persistent_kwargs)
    return ctx, None
