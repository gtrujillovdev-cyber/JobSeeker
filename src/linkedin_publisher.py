import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Union, Dict, Any

from config import (
    BROWSER_PROFILE_DIR, STORAGE_STATE_FILE, HEADLESS, BROWSER_CHANNEL,
    CHROMIUM_EXECUTABLE_PATH, SCREENSHOTS_DIR
)
from src.anti_ban import AntiBanValidator

class LinkedInPublisher:
    """
    Publicador headless de LinkedIn mediante sesión persistente en Chromium.
    Soporta subida de múltiples imágenes (UI + funcionalidades + código), verificación de post publicado,
    captura de confirmación con URL directa y publicación automática del primer comentario.
    """

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.last_published_url: Optional[str] = None
        self.last_confirmation_screenshot: Optional[Path] = None

    def publish_post(
        self,
        text: str,
        image_path: Optional[Union[Path, List[Path]]] = None,
        project_name: str = "General",
        first_comment: Optional[str] = None
    ) -> bool:
        print(f"\n💼 [LinkedIn] Iniciando proceso de publicación para '{project_name}'...")

        # Normalizar lista de imágenes reales
        image_paths: List[Path] = []
        if isinstance(image_path, (list, tuple)):
            image_paths = [Path(p) for p in image_path if p and Path(p).exists()]
        elif image_path and Path(image_path).exists():
            image_paths = [Path(image_path)]

        # 1. Validación Anti-Ban
        if not AntiBanValidator.check_daily_limit():
            return False

        if not BROWSER_PROFILE_DIR.exists():
            print(f"[!] No se encontró el perfil de navegador en {BROWSER_PROFILE_DIR}")
            print("👉 Ejecuta primero: python scripts/setup_linkedin_session.py")
            return False

        # 2. Modo Simulación (Dry Run)
        if self.dry_run:
            print("[LinkedIn] [DRY RUN] Simulación activada. Post no publicado.")
            print("----------------- TEXTO DEL POST -----------------")
            print(text)
            print("--------------------------------------------------")
            if image_paths:
                print(f"[*] Imágenes adjuntas simuladas ({len(image_paths)}): {[str(p) for p in image_paths]}")
            if first_comment:
                print(f"[*] Primer comentario simulado: {first_comment}")
            AntiBanValidator.record_publication(project_name, text, str(image_paths[0] if image_paths else ""), status="simulated")
            return True

        # 3. Publicación real mediante Playwright
        try:
            from playwright.sync_api import sync_playwright
            from src.browser_helper import get_playwright_browser_context

            print(f"[*] Abriendo contexto de navegación de LinkedIn (headless={HEADLESS})...")
            with sync_playwright() as p:
                context, browser_instance = get_playwright_browser_context(p)
                page = context.pages[0] if context.pages else context.new_page()
                page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=45000)
                time.sleep(3)
                print(f"[*] URL actual tras navegar al Feed: {page.url} (Título: {page.title()})")

                # Verificar si pide login
                if "login" in page.url.lower() or "authwall" in page.url.lower():
                    print(f"[!] La sesión de LinkedIn ha expirado o requiere autenticación (URL: {page.url}).")
                    print("👉 Ejecuta: python scripts/setup_linkedin_session.py para renovarla.")
                    context.close()
                    if browser_instance:
                        browser_instance.close()
                    return False

                print("[*] Localizando el disparador de publicación...")
                # Selectores habituales del feed de LinkedIn para abrir el modal (incluye nuevo DOM <div role="button">)
                trigger_selectors = [
                    "div[role='button']:has-text('Crear publicación')",
                    "div[role='button']:has-text('Start a post')",
                    "button.share-box-feed-entry__trigger",
                    "button:has-text('Crear publicación')",
                    "button:has-text('Start a post')",
                    "[data-view-name='feed-share-box-trigger']"
                ]

                opened = False
                for sel in trigger_selectors:
                    trigger = page.locator(sel).first
                    if trigger.count() > 0 and trigger.is_visible():
                        try:
                            trigger.evaluate("el => el.click()")
                        except Exception:
                            trigger.click(force=True)
                        opened = True
                        break

                if not opened:
                    print("[!] No se encontró el botón para crear publicación en el feed.")
                    context.close()
                    return False

                time.sleep(2.5)

                # 4. Adjuntar imágenes (soporta galería multi-imagen: UI en vivo + funcionalidades + código real)
                if image_paths:
                    files_str_list = [str(p) for p in image_paths]
                    print(f"[*] Adjuntando {len(files_str_list)} captura(s): {files_str_list}...")
                    media_btn_selectors = [
                        "button[aria-label='Contenido multimedia']",
                        "button[aria-label*='multimedia']",
                        "button[aria-label*='Añadir contenido multimedia']",
                        "button[aria-label*='Add media']",
                        "button[aria-label*='media']",
                        ".share-promoted-v2__content button",
                        "button.share-box-footer__action--media"
                    ]
                    uploaded = False
                    for m_sel in media_btn_selectors:
                        btn = page.locator(m_sel).first
                        if btn.count() > 0 and btn.is_visible():
                            try:
                                with page.expect_file_chooser(timeout=6000) as fc_info:
                                    try:
                                        btn.evaluate("el => el.click()")
                                    except Exception:
                                        btn.click(force=True)
                                file_chooser = fc_info.value
                                file_chooser.set_files(files_str_list)
                                uploaded = True
                                break
                            except Exception:
                                file_input = page.locator("input[type='file']").first
                                if file_input.count() > 0:
                                    file_input.set_input_files(files_str_list)
                                    uploaded = True
                                    break

                    if uploaded:
                        time.sleep(3)
                        next_btn = page.locator("button:has-text('Siguiente'), button:has-text('Next'), button[aria-label='Siguiente']").first
                        if next_btn.count() > 0 and next_btn.is_visible():
                            try:
                                next_btn.evaluate("el => el.click()")
                            except Exception:
                                next_btn.click(force=True)
                            time.sleep(2)
                        print(f"[✓] {len(files_str_list)} imagen(es) adjuntada(s) con éxito.")
                    else:
                        print("[⚠️] No se pudo adjuntar la galería de imágenes, continuando con publicación de texto.")

                # 5. Escribir el texto en el editor (TipTap / ProseMirror / Quill)
                print("[*] Escribiendo texto en el editor de LinkedIn...")
                editor_selectors = [
                    "div.tiptap.ProseMirror[contenteditable='true']",
                    "div[role='textbox'][contenteditable='true']",
                    "div.ql-editor",
                    "div.editor-content",
                    "div.share-creation-state__text-editor div[contenteditable]"
                ]

                editor_el = None
                for e_sel in editor_selectors:
                    el = page.locator(e_sel).first
                    if el.count() > 0 and el.is_visible():
                        editor_el = el
                        break

                if not editor_el:
                    print("[!] No se encontró el editor de texto de la publicación.")
                    context.close()
                    return False

                try:
                    editor_el.click(force=True)
                except Exception:
                    editor_el.evaluate("el => el.focus()")
                time.sleep(0.5)

                # Limpiar contenido previo del editor TipTap/ProseMirror
                page.keyboard.press("Meta+a")
                page.keyboard.press("Backspace")
                time.sleep(0.2)

                # Escribir línea por línea usando eventos reales de teclado ('Enter') para que TipTap cree nodos <p> reales
                lines = text.split("\n")
                for idx, line in enumerate(lines):
                    if line:
                        page.keyboard.insert_text(line)
                    if idx < len(lines) - 1:
                        page.keyboard.press("Enter")
                time.sleep(2)

                # 6. Pulsar Publicar
                print("[*] Enviando publicación...")
                publish_btn = page.locator("button.share-actions__primary-action, button:has-text('Publicar'), button:has-text('Post')").first
                if publish_btn.count() > 0 and publish_btn.is_enabled():
                    try:
                        publish_btn.evaluate("el => el.click()")
                    except Exception:
                        publish_btn.click(force=True)
                    time.sleep(6)  # Esperar a que la petición de red termine
                    print("[✓] ¡Publicación lanzada exitosamente a tu feed de LinkedIn!")
                    AntiBanValidator.record_publication(project_name, text, str(image_paths[0] if image_paths else ""), status="success")

                    # Intentar capturar URN desde el toast inmediato si aparece ("Ver publicación")
                    toast_urn = ""
                    try:
                        import re
                        toast_links = page. evaluate("""() => {
                            return Array.from(document.querySelectorAll('a[href*="urn:li:activity:"], a[href*="/feed/update/"]')).map(a => a.href);
                        }""")
                        for tl in toast_links:
                            m_urn = re.search(r"(urn:li:(?:activity|ugcPost|share):\d+)", tl)
                            if m_urn:
                                toast_urn = m_urn.group(1)
                                break
                    except Exception:
                        pass

                    # 7. Verificar en recent-activity, extraer URL directa, publicar primer comentario y sacar captura de confirmación
                    expected_snippet = text.strip().splitlines()[0][:40] if text.strip() else ""
                    info = self._verify_and_comment_latest_post(
                        page=page,
                        expected_snippet=expected_snippet,
                        comment_text=first_comment,
                        hint_urn=toast_urn
                    )
                    self.last_published_url = info.get("post_url")
                    self.last_confirmation_screenshot = info.get("screenshot_path")

                    context.close()
                    return True
                else:
                    print("[!] El botón de 'Publicar' no está habilitado o no se encontró.")
                    context.close()
                    return False

        except Exception as e:
            print(f"[!] Error durante la publicación en LinkedIn: {e}")
            return False

    @staticmethod
    def _verify_and_comment_latest_post(
        page,
        expected_snippet: str = "",
        comment_text: Optional[str] = None,
        hint_urn: str = ""
    ) -> Dict[str, Any]:
        """
        1. Navega a la actividad reciente y extrae el URN real del post recién publicado
           (soportando tanto el nuevo DOM SDUI con enlaces de analytics/update como data-urn clásico).
        2. Construye la URL directa `https://www.linkedin.com/feed/update/{urn}/` y navega a ella.
        3. Si hay comment_text, lo publica en la caja de comentarios del post verificado.
        4. Toma una captura de confirmación visual para enviar a Telegram junto con el enlace.
        """
        import re
        result: Dict[str, Any] = {
            "verified": False,
            "comment_posted": False,
            "post_url": f"https://www.linkedin.com/feed/update/{hint_urn}/" if hint_urn else None,
            "screenshot_path": None
        }
        try:
            detected_urn = hint_urn
            for attempt in range(3):
                page.goto("https://www.linkedin.com/in/me/recent-activity/all/", wait_until="domcontentloaded", timeout=30000)
                time.sleep(4)

                body_text = ""
                try:
                    body_text = page.locator("body").inner_text()
                except Exception:
                    pass

                # Extraer URN desde enlaces (analytics/post-summary/urn:li:activity:..., feed/update/...) o HTML
                urns = page.evaluate("""() => {
                    const out = [];
                    for (const el of document.querySelectorAll('[data-urn*="urn:li:activity:"]')) {
                        const u = el.getAttribute('data-urn');
                        if (u && !out.includes(u)) out.push(u);
                    }
                    for (const a of document.querySelectorAll('a[href*="urn:li:activity:"], a[href*="urn:li:ugcPost:"], a[href*="urn:li:share:"]')) {
                        const m = a.href.match(/(urn:li:(?:activity|ugcPost|share):\\d+)/);
                        if (m && !out.includes(m[1])) out.push(m[1]);
                    }
                    const htmlMatches = document.body.innerHTML.match(/urn:li:(?:activity|ugcPost|share):\\d+/g) || [];
                    for (const hm of htmlMatches) {
                        if (!out.includes(hm)) out.push(hm);
                    }
                    return out;
                }""")

                if urns:
                    detected_urn = urns[0]
                    result["post_url"] = f"https://www.linkedin.com/feed/update/{detected_urn}/"
                    if not expected_snippet or expected_snippet.lower() in body_text.lower():
                        result["verified"] = True
                        break

                # Fallback clásico si existen tarjetas .feed-shared-update-v2
                post_cards = page.locator("div.feed-shared-update-v2, [data-urn*='urn:li:activity:']")
                if post_cards.count() > 0:
                    candidate = post_cards.first
                    card_text = candidate.inner_text()
                    if not expected_snippet or expected_snippet.lower() in card_text.lower():
                        result["verified"] = True
                        urn = candidate.get_attribute("data-urn") or detected_urn
                        if urn and "urn:li:" in urn:
                            result["post_url"] = f"https://www.linkedin.com/feed/update/{urn}/"
                        break

                print(f"[LinkedIn] Esperando indexación del nuevo post en actividad reciente (intento {attempt + 1}/3)...")
                time.sleep(3)

            # Si tenemos URL directa de la publicación, abrirla directamente para verificar, comentar y capturar
            if result["post_url"]:
                page.goto(result["post_url"], wait_until="domcontentloaded", timeout=30000)
                time.sleep(3.5)
                try:
                    post_page_text = page.locator("body").inner_text()
                    if not expected_snippet or expected_snippet.lower() in post_page_text.lower():
                        result["verified"] = True
                except Exception:
                    result["verified"] = True

            if comment_text and (result["verified"] or result["post_url"]):
                print(f"[*] Publicando primer comentario automático en el post verificado: {comment_text[:70]}...")
                comment_box_selectors = (
                    "div[aria-label*='Editor de texto para crear comentarios'], "
                    "div[aria-label*='Text editor for creating comment'], "
                    "div.comments-comment-box__form div[role='textbox'][contenteditable='true'], "
                    "div.tiptap.ProseMirror[role='textbox'], "
                    "div.ql-editor[contenteditable='true'], "
                    "div[role='textbox'][contenteditable='true']"
                )
                comment_box = page.locator(comment_box_selectors).first

                if comment_box.count() == 0 or not comment_box.is_visible():
                    comment_btn = page.locator(
                        "button[aria-label='Comentar'], button[aria-label*='Comentar'], button[aria-label*='Comment'], button:has-text('Comentar')"
                    ).first
                    if comment_btn.count() > 0 and comment_btn.is_visible():
                        try:
                            comment_btn.click()
                        except Exception:
                            comment_btn.evaluate("el => el.click()")
                        time.sleep(1.5)
                    comment_box = page.locator(comment_box_selectors).first

                if comment_box.count() > 0:
                    try:
                        comment_box.click(force=True)
                    except Exception:
                        comment_box.evaluate("el => el.focus()")
                    time.sleep(0.5)
                    lines = comment_text.split("\n")
                    for idx, line in enumerate(lines):
                        if line:
                            page.keyboard.insert_text(line)
                        if idx < len(lines) - 1:
                            page.keyboard.press("Enter")
                    time.sleep(1.5)

                    # Buscar botón de enviar comentario (evitando el botón de abrir comentarios que tiene texto vacío o número)
                    submitted = page.evaluate("""() => {
                        const buttons = Array.from(document.querySelectorAll('button'));
                        for (const b of buttons) {
                            const txt = (b.innerText || '').trim().toLowerCase();
                            const aria = (b.getAttribute('aria-label') || '').toLowerCase();
                            const cls = b.className || '';
                            if (b.disabled) continue;
                            if (
                                cls.includes('comments-comment-box__submit-button') ||
                                aria.includes('publicar comentario') ||
                                aria.includes('post comment') ||
                                txt === 'comentar' ||
                                txt === 'publicar' ||
                                txt === 'post'
                            ) {
                                b.click();
                                return true;
                            }
                        }
                        return false;
                    }""")
                    if submitted:
                        time.sleep(3)
                        result["comment_posted"] = True
                        print("[✓] Primer comentario publicado en tu post.")

            # Captura de confirmación del post publicado (+ primer comentario)
            confirm_path = SCREENSHOTS_DIR / f"published_confirm_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            page.screenshot(path=str(confirm_path), full_page=False)
            result["screenshot_path"] = confirm_path
        except Exception as e:
            print(f"[LinkedIn] Aviso en verificación/primer comentario: {e}")
        return result

    @classmethod
    def check_session_health(cls) -> Dict[str, Any]:
        """
        Comprueba de forma silenciosa si la sesión persistente de LinkedIn sigue activa.
        Ideal para healthcheck diario en el MBP1 o servidor headless.
        """
        if not BROWSER_PROFILE_DIR.exists():
            return {"ok": False, "reason": "No existe el directorio de perfil de navegador."}
        try:
            from playwright.sync_api import sync_playwright
            from src.browser_helper import get_playwright_browser_context
            with sync_playwright() as p:
                context, browser_instance = get_playwright_browser_context(p)
                page = context.pages[0] if context.pages else context.new_page()
                page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
                time.sleep(2)
                url = page.url.lower()
                context.close()
                if browser_instance:
                    browser_instance.close()
                if "login" in url or "authwall" in url or "checkpoint" in url:
                    return {"ok": False, "reason": f"Sesión expirada o requiere login ({url})."}
                return {"ok": True, "reason": "Sesión de LinkedIn activa y saludable."}
        except Exception as e:
            return {"ok": False, "reason": f"No se pudo verificar (posible navegador en uso): {e}"}
