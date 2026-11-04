import json
import time
import random
from typing import List, Dict, Any, Optional
from pathlib import Path

from config import (
    BROWSER_PROFILE_DIR, STORAGE_STATE_FILE, HEADLESS, BROWSER_CHANNEL,
    GEMINI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
)
from src.anti_ban import AntiBanValidator
from src.job_scanner import JobScanner


class EngagementEngine:
    """
    Motor de networking activo en LinkedIn.
    Genera comentarios, conexiones y reacciones dirigidas a empresas target,
    siempre con aprobacion previa por Telegram (Human-in-the-Loop).
    """

    @classmethod
    def propose_actions(cls, max_actions: int = 5, discover_profiles: bool = True) -> List[Dict[str, Any]]:
        """
        Analiza los datos del JobScanner y propone acciones de engagement:
        - Filtra empresas ya contactadas recientemente para descubrir siempre nuevos recruiters
        - Si discover_profiles=True, pre-busca en LinkedIn el nombre, cargo y URL real de la persona de RRHH
          y redacta la nota personalizada ANTES de enviarte la propuesta a Telegram.
        """
        targets = JobScanner.get_target_companies_with_roles()
        skills = JobScanner.get_demanded_skills()

        if not targets:
            print("[Engagement] No hay empresas target. Ejecuta primero: python main.py --scan-jobs")
            return []

        # Filtrar empresas ya contactadas con éxito en los últimos 30 registros
        history = AntiBanValidator._get_engagement_records()
        already_contacted = {
            r.get("target", "").strip().lower()
            for r in history[-30:]
            if r.get("action") == "connection" and r.get("status") == "success"
        }

        actions = []

        # Proponer conexiones prioritarias con RRHH, Selección y Talent Acquisition de empresas no contactadas
        for item in targets:
            company = item["company"]
            role = item.get("role", "Desarrollo de Software / Ciberseguridad / Sistemas")
            if company.lower() in already_contacted:
                continue
            if not AntiBanValidator.check_engagement_limit("connection"):
                break
            if len(actions) >= max_actions:
                break
            actions.append({
                "type": "connection",
                "target_company": company,
                "target_role": role,
                "target_name": "Responsable de Selección",
                "target_headline": "RRHH / Talent Acquisition",
                "target_url": "",
                "search_query": f"{company} (RRHH OR \"Recursos Humanos\" OR recruiter OR \"talent acquisition\" OR seleccion)",
                "status": "proposed",
                "enabled": True,
                "note_text": None
            })

        # Si todas las empresas del radar ya fueron contactadas, permitir segundos contactos en el top
        if not actions:
            for item in targets[:max_actions]:
                company = item["company"]
                role = item.get("role", "Desarrollo de Software / Ciberseguridad / Sistemas")
                if not AntiBanValidator.check_engagement_limit("connection"):
                    break
                actions.append({
                    "type": "connection",
                    "target_company": company,
                    "target_role": role,
                    "target_name": "Responsable de Selección",
                    "target_headline": "RRHH / Talent Acquisition",
                    "target_url": "",
                    "search_query": f"{company} (RRHH OR \"Recursos Humanos\" OR recruiter OR \"talent acquisition\" OR seleccion)",
                    "status": "proposed",
                    "enabled": True,
                    "note_text": None
                })

        import os
        if discover_profiles and actions and not os.environ.get("PYTEST_CURRENT_TEST"):
            cls._discover_recruiter_previews(actions)

        for act in actions:
            if not act.get("note_text"):
                act["note_text"] = cls._generate_connection_note(
                    act["target_company"],
                    act.get("target_name", "Responsable de Selección"),
                    act.get("target_role", "Sistemas / Ciberseguridad / Desarrollo")
                )

        return actions

    @classmethod
    def _discover_recruiter_previews(cls, actions: List[Dict[str, Any]]) -> None:
        """
        Pre-busca en LinkedIn el primer perfil conectable de RRHH/Selección de cada empresa
        para mostrar a Gabriel en Telegram el nombre real, cargo, enlace y nota exacta antes de aprobar.
        """
        if not BROWSER_PROFILE_DIR.exists():
            return
        try:
            from urllib.parse import quote_plus
            from playwright.sync_api import sync_playwright
            import re

            print("[Engagement] Pre-buscando perfiles reales de RRHH para mostrar en Telegram...")
            with sync_playwright() as p:
                launch_kwargs = {
                    "user_data_dir": str(BROWSER_PROFILE_DIR),
                    "headless": HEADLESS,
                    "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                    "viewport": {"width": 1280, "height": 900},
                    "args": ["--disable-blink-features=AutomationControlled", "--no-sandbox"]
                }
                if BROWSER_CHANNEL:
                    launch_kwargs["channel"] = BROWSER_CHANNEL

                context = p.chromium.launch_persistent_context(**launch_kwargs)
                page = context.pages[0] if context.pages else context.new_page()

                for act in actions:
                    company = act["target_company"]
                    query = f'{company} ("Recursos Humanos" OR RRHH OR recruiter OR "talent acquisition" OR seleccion)'
                    # Priorizar contactos de 2º grado (contactos de mis contactos: network=["S"]) para máxima confianza
                    search_url = (
                        f"https://www.linkedin.com/search/results/people/"
                        f"?keywords={quote_plus(query)}"
                        f"&network=%5B%22S%22%5D"
                        f"&origin=GLOBAL_SEARCH_HEADER"
                    )
                    try:
                        page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
                        time.sleep(2.5)
                        connect_btn = page.locator(
                            "a[href*='search-custom-invite'], a[aria-label*='conectar' i], button[aria-label*='conectar' i], "
                            "a[aria-label*='to connect' i], button[aria-label*='to connect' i]"
                        ).first
                        if connect_btn.count() == 0 or not connect_btn.is_visible():
                            # Fallback sin filtro estricto de red si no hay en 2º grado
                            search_url_broad = f"https://www.linkedin.com/search/results/people/?keywords={quote_plus(query)}&origin=GLOBAL_SEARCH_HEADER"
                            page.goto(search_url_broad, wait_until="domcontentloaded", timeout=20000)
                            time.sleep(2.0)
                            connect_btn = page.locator(
                                "a[href*='search-custom-invite'], a[aria-label*='conectar' i], button[aria-label*='conectar' i], "
                                "a[aria-label*='to connect' i], button[aria-label*='to connect' i]"
                            ).first
                        if connect_btn.count() == 0 or not connect_btn.is_visible():
                            continue

                        aria = connect_btn.get_attribute("aria-label") or ""
                        href_attr = connect_btn.get_attribute("href") or ""
                        m = re.search(r"[iI]nvita a\s+(.+?)\s+a conectar", aria) or re.search(r"[iI]nvite\s+(.+?)\s+to connect", aria)
                        if m:
                            act["target_name"] = m.group(1).strip()
                        if "vanityName=" in href_attr:
                            vn = href_attr.split("vanityName=")[-1].split("&")[0]
                            if vn:
                                act["target_url"] = f"https://www.linkedin.com/in/{vn}/"

                        info = connect_btn.evaluate("""(el) => {
                            let card = el.closest('li, .reusable-search__result-container, [data-view-name="search-entity-result-universal-template"]') || el.parentElement?.parentElement?.parentElement;
                            if (!card) return {name: '', headline: '', url: ''};
                            const link = card.querySelector('a[href*="/in/"]');
                            const url = link ? link.href.split('?')[0] : '';
                            const nameSpan = card.querySelector('a[href*="/in/"] span[aria-hidden="true"]');
                            const name = nameSpan ? nameSpan.innerText.trim().split('\\n')[0].trim() : '';
                            const sub = card.querySelector('.entity-result__primary-subtitle, .t-14.t-black.t-normal');
                            const headline = sub ? sub.innerText.trim().split('\\n')[0].trim() : '';
                            return {name, headline, url};
                        }""")
                        if info.get("name") and act["target_name"] == "Responsable de Selección":
                            act["target_name"] = info["name"].split("•")[0].strip()
                        if info.get("headline"):
                            act["target_headline"] = info["headline"]
                        if info.get("url") and not act.get("target_url"):
                            act["target_url"] = info["url"]
                    except Exception:
                        continue

                context.close()
        except Exception as e:
            print(f"[Engagement] Aviso en pre-búsqueda de perfiles: {e}")

    @classmethod
    def _build_engagement_message_and_keyboard(cls, actions: List[Dict[str, Any]]) -> tuple[str, dict]:
        lines = ["🎯 *PLAN DE NETWORKING RRHH (CON VISTA PREVIA)*\n"]
        summary = AntiBanValidator.get_today_engagement_summary()
        if summary:
            lines.append("Actividad registrada hoy:")
            for action_k, count in summary.items():
                lines.append(f"  • {action_k}: {count}")
            lines.append("")

        toggle_row = []
        for i, action in enumerate(actions, 1):
            enabled = action.get("enabled", True)
            state_icon = "✅" if enabled else "⏭️ (Omitido)"
            person = action.get("target_name", "Responsable de Selección")
            headline = action.get("target_headline", "RRHH / Selección")
            url = action.get("target_url", "")
            note = action.get("note_text", "")
            lines.append(f"*{i}. {state_icon} {action['target_company']}* ({action.get('target_role', '')[:45]})")
            lines.append(f"   👤 *{person}* — {headline[:60]}")
            if url:
                lines.append(f"   🔗 {url}")
            if note:
                lines.append(f"   ✉️ _{note}_")
            lines.append("")
            toggle_row.append({
                "text": f"{'✅' if enabled else '❌'} #{i}",
                "callback_data": f"engage:toggle_{i - 1}"
            })

        lines.append("Pulsa sobre `#1..#5` si quieres desmarcar alguno antes de enviar:")
        keyboard_rows = []
        if toggle_row:
            keyboard_rows.append(toggle_row)
        keyboard_rows.append([
            {"text": "🚀 Enviar seleccionadas", "callback_data": "engage:approve"},
            {"text": "❌ Cancelar", "callback_data": "engage:reject"}
        ])
        return "\n".join(lines), {"inline_keyboard": keyboard_rows}

    @classmethod
    def send_proposals_to_telegram(cls, actions: List[Dict[str, Any]]) -> Optional[str]:
        """Envia las acciones propuestas a Telegram con nombre real, perfil, nota y botones individuales."""
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            print("[Engagement] Telegram no configurado.")
            return None

        if not actions:
            return None

        import requests

        text, keyboard = cls._build_engagement_message_and_keyboard(actions)

        try:
            res = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": text[:4000],
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                    "reply_markup": keyboard
                },
                timeout=15
            )
            if res.status_code == 200:
                print("[Engagement] Plan enviado a Telegram para aprobacion.")
                return "engage"
            else:
                print(f"[Engagement] Error enviando a Telegram: {res.status_code}")
                return None
        except Exception as e:
            print(f"[Engagement] Error: {e}")
            return None

    @classmethod
    def listen_and_execute(cls, actions: List[Dict[str, Any]], timeout: int = 900) -> bool:
        """
        Escucha la decision del usuario en Telegram.
        Si aprueba, ejecuta las acciones de engagement con Playwright.
        """
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            return False

        import requests

        print("\n" + "=" * 55)
        print(" ESPERANDO APROBACION DEL PLAN DE ENGAGEMENT...")
        print("=" * 55)

        last_update_id = 0
        start_time = time.time()

        while (time.time() - start_time) < timeout:
            try:
                res = requests.get(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
                    params={"offset": last_update_id + 1, "timeout": 10},
                    timeout=15
                )
                if res.status_code != 200:
                    time.sleep(2)
                    continue

                for update in res.json().get("result", []):
                    last_update_id = update["update_id"]

                    if "callback_query" not in update:
                        continue

                    cb = update["callback_query"]
                    data = cb.get("data", "")
                    cb_id = cb["id"]
                    chat_id = cb.get("message", {}).get("chat", {}).get("id")
                    message_id = cb.get("message", {}).get("message_id")

                    if not data.startswith("engage:"):
                        continue

                    decision = data.split(":")[1]

                    if decision.startswith("toggle_"):
                        try:
                            idx = int(decision.split("_")[1])
                            if 0 <= idx < len(actions):
                                actions[idx]["enabled"] = not actions[idx].get("enabled", True)
                                new_text, new_kb = cls._build_engagement_message_and_keyboard(actions)
                                requests.post(
                                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageText",
                                    json={
                                        "chat_id": chat_id,
                                        "message_id": message_id,
                                        "text": new_text[:4000],
                                        "parse_mode": "Markdown",
                                        "disable_web_page_preview": True,
                                        "reply_markup": new_kb
                                    }
                                )
                                requests.post(
                                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery",
                                    json={"callback_query_id": cb_id, "text": f"Contacto #{idx + 1} actualizado"}
                                )
                        except Exception:
                            pass
                        continue

                    # Limpiar botones
                    requests.post(
                        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageReplyMarkup",
                        json={"chat_id": chat_id, "message_id": message_id, "reply_markup": {"inline_keyboard": []}}
                    )

                    if decision == "approve":
                        selected = [a for a in actions if a.get("enabled", True)]
                        requests.post(
                            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery",
                            json={"callback_query_id": cb_id, "text": f"Ejecutando {len(selected)} acciones..."}
                        )
                        print(f"[Engagement] Aprobado ({len(selected)} seleccionadas). Ejecutando acciones...")
                        results = cls._execute_actions(selected)
                        cls._report_results(results, chat_id)
                        return True

                    elif decision == "reject":
                        requests.post(
                            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery",
                            json={"callback_query_id": cb_id, "text": "Plan cancelado."}
                        )
                        requests.post(
                            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                            json={"chat_id": chat_id, "text": "Plan de engagement cancelado."}
                        )
                        print("[Engagement] Plan cancelado por el usuario.")
                        return False

            except Exception as e:
                print(f"[Engagement] Error en polling: {e}")
                time.sleep(3)

        print("[Engagement] Timeout esperando decision.")
        return False

    @classmethod
    def _execute_actions(cls, actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Ejecuta cada accion aprobada con Playwright sobre LinkedIn."""
        results = []

        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                launch_kwargs = {
                    "user_data_dir": str(BROWSER_PROFILE_DIR),
                    "headless": HEADLESS,
                    "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                    "viewport": {"width": 1280, "height": 900},
                    "args": ["--disable-blink-features=AutomationControlled", "--no-sandbox"]
                }
                if BROWSER_CHANNEL:
                    launch_kwargs["channel"] = BROWSER_CHANNEL

                context = p.chromium.launch_persistent_context(**launch_kwargs)
                page = context.pages[0] if context.pages else context.new_page()
                print(f"[Engagement] Estableciendo sesión en Feed de LinkedIn...")
                page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
                time.sleep(2)
                print(f"[Engagement] URL Feed: {page.url} (Título: {page.title()})")

                for action in actions:
                    if not AntiBanValidator.check_engagement_limit(action["type"]):
                        results.append({**action, "status": "skipped", "reason": "daily_limit"})
                        continue

                    # Pausa humana entre acciones (anti-deteccion)
                    time.sleep(random.uniform(3, 7))

                    if action["type"] == "comment":
                        result = cls._execute_comment(page, action)
                    elif action["type"] == "connection":
                        result = cls._execute_connection(page, action)
                    elif action["type"] == "reaction":
                        result = cls._execute_reaction(page, action)
                    else:
                        result = {**action, "status": "skipped", "reason": "unknown_type"}

                    results.append(result)

                context.close()

        except Exception as e:
            print(f"[Engagement] Error en Playwright: {e}")

        return results

    @classmethod
    def _execute_comment(cls, page, action: Dict[str, Any]) -> Dict[str, Any]:
        """Busca un post reciente de la empresa target y deja un comentario tecnico."""
        company = action["target_company"]
        print(f"  [Comment] Buscando posts de '{company}'...")

        try:
            from urllib.parse import quote_plus
            search_url = f"https://www.linkedin.com/search/results/content/?keywords={quote_plus(company)}&sortBy=%22date_posted%22"
            page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
            time.sleep(3)
            print(f"  [Connect] URL búsqueda personas: {page.url} (Título: {page.title()})")

            # Buscar el primer post con boton de comentar
            post_text = page.evaluate("""() => {
                const post = document.querySelector('.feed-shared-update-v2__description, .update-components-text');
                return post ? post.innerText.trim().substring(0, 500) : '';
            }""")

            if not post_text:
                return {**action, "status": "skipped", "reason": "no_posts_found"}

            # Generar comentario tecnico con Gemini
            comment = cls._generate_comment(company, post_text)
            if not comment:
                return {**action, "status": "skipped", "reason": "comment_generation_failed"}

            # Localizar y clickar boton de comentar
            comment_btn = page.locator("button[aria-label*='omment'], button[aria-label*='omentar']").first
            if comment_btn.count() == 0 or not comment_btn.is_visible():
                return {**action, "status": "skipped", "reason": "comment_button_not_found"}

            comment_btn.click()
            time.sleep(1.5)

            # Escribir en el campo de comentario
            comment_box = page.locator("div.ql-editor[contenteditable='true'], div[role='textbox'][contenteditable='true']").first
            if comment_box.count() == 0:
                return {**action, "status": "skipped", "reason": "comment_box_not_found"}

            comment_box.click()
            time.sleep(0.5)

            page.evaluate("""(text) => {
                const el = document.querySelector('.comments-comment-box__form div.ql-editor, div[role="textbox"][contenteditable="true"]');
                if (!el) return false;
                el.focus();
                document.execCommand('insertText', false, text);
                el.dispatchEvent(new Event('input', { bubbles: true }));
                return true;
            }""", comment)

            time.sleep(1)

            # Pulsar enviar comentario
            submit_btn = page.locator("button.comments-comment-box__submit-button, button[aria-label*='ubmit'], button[aria-label*='nviar']").first
            if submit_btn.count() > 0 and submit_btn.is_enabled():
                submit_btn.click()
                time.sleep(2)
                AntiBanValidator.record_engagement("comment", company, comment)
                print(f"  [Comment] Comentario publicado en post de {company}")
                return {**action, "status": "success", "comment_text": comment}

            return {**action, "status": "skipped", "reason": "submit_not_found"}

        except Exception as e:
            print(f"  [Comment] Error: {e}")
            return {**action, "status": "error", "reason": str(e)}

    @classmethod
    def _execute_connection(cls, page, action: Dict[str, Any]) -> Dict[str, Any]:
        """Busca perfiles de RRHH / Talento de la empresa y envia solicitud real verificando el diálogo de invitación."""
        company = action["target_company"]
        target_role = action.get("target_role", "Desarrollo de Software / Ciberseguridad / Sistemas")
        print(f"  [Connect] Buscando responsables de RRHH/Selección de '{company}' (Rol: {target_role})...")

        try:
            import re
            from urllib.parse import quote_plus
            # Priorizar contactos de 2º grado (contactos de mis contactos: network=["S"]) para red de confianza
            query = f'{company} ("Recursos Humanos" OR RRHH OR recruiter OR "talent acquisition" OR seleccion)'
            search_url = (
                f"https://www.linkedin.com/search/results/people/"
                f"?keywords={quote_plus(query)}"
                f"&network=%5B%22S%22%5D"
                f"&origin=GLOBAL_SEARCH_HEADER"
            )
            page.goto(search_url, wait_until="domcontentloaded", timeout=25000)
            time.sleep(3.0)
            print(f"  [Connect] URL búsqueda personas (2º grado): {page.url}")

            # Buscar botones o enlaces reales de "Conectar" en los resultados
            strict_selector = (
                "a[href*='search-custom-invite'], a[aria-label*='conectar' i], button[aria-label*='conectar' i], "
                "a[aria-label*='to connect' i], button[aria-label*='to connect' i]"
            )
            connect_locator = page.locator(strict_selector)
            total_candidates = connect_locator.count()

            # Si no hay candidatos de 2º grado, ampliar a toda la red para esa empresa
            if total_candidates == 0:
                broad_query_url = (
                    f"https://www.linkedin.com/search/results/people/"
                    f"?keywords={quote_plus(query)}"
                    f"&origin=GLOBAL_SEARCH_HEADER"
                )
                page.goto(broad_query_url, wait_until="domcontentloaded", timeout=25000)
                time.sleep(3.0)
                connect_locator = page.locator(strict_selector)
                total_candidates = connect_locator.count()

            if total_candidates == 0:
                # Fallback 2: búsqueda más amplia en la misma empresa
                broad_query = f"{company} (RRHH OR Talent OR People OR Tech OR Engineering)"
                broad_url = f"https://www.linkedin.com/search/results/people/?keywords={quote_plus(broad_query)}&origin=GLOBAL_SEARCH_HEADER"
                page.goto(broad_url, wait_until="domcontentloaded", timeout=25000)
                time.sleep(3.0)
                connect_locator = page.locator(strict_selector)
                total_candidates = connect_locator.count()

            if total_candidates == 0:
                return {**action, "status": "skipped", "reason": "no_connect_button"}

            connect_btn = connect_locator.first
            if not connect_btn.is_visible():
                return {**action, "status": "skipped", "reason": "connect_button_not_visible"}

            # Extraer nombre, cargo y URL del perfil desde aria-label / href / DOM
            profile_name = action.get("target_name") or "Responsable de Selección"
            profile_url = action.get("target_url") or ""
            aria = connect_btn.get_attribute("aria-label") or ""
            invite_href = connect_btn.get_attribute("href") or ""

            m = re.search(r"[iI]nvita a\s+(.+?)\s+a conectar", aria) or re.search(r"[iI]nvite\s+(.+?)\s+to connect", aria)
            if m:
                profile_name = m.group(1).strip()

            if "vanityName=" in invite_href and not profile_url:
                vanity = invite_href.split("vanityName=")[-1].split("&")[0]
                if vanity:
                    profile_url = f"https://www.linkedin.com/in/{vanity}/"

            if profile_name == "Responsable de Selección" or not profile_url:
                try:
                    dom_info = connect_btn.evaluate("""(el) => {
                        let card = el.closest('li, .reusable-search__result-container, [data-view-name="search-entity-result-universal-template"]') || el.parentElement?.parentElement?.parentElement;
                        if (!card) return {name: '', url: ''};
                        const link = card.querySelector('a[href*="/in/"]');
                        const url = link ? link.href.split('?')[0] : '';
                        const nameEl = card.querySelector('a[href*="/in/"] span[aria-hidden="true"], .entity-result__title-text a span[aria-hidden="true"], a[href*="/in/"]');
                        const name = nameEl && nameEl.innerText ? nameEl.innerText.trim().split('\\n')[0].trim() : '';
                        return {name, url};
                    }""")
                    if dom_info.get("name") and len(dom_info["name"]) > 2 and "conectar" not in dom_info["name"].lower():
                        profile_name = dom_info["name"].split("•")[0].strip()
                    if dom_info.get("url") and not profile_url:
                        profile_url = dom_info["url"]
                except Exception:
                    pass

            print(f"  [Connect] Contacto seleccionado: {profile_name} ({profile_url or invite_href})")

            # Abrir modal de invitación (navegando a /preload/search-custom-invite/ si es un enlace, o clickando)
            if invite_href and "/preload/" in invite_href:
                full_invite_url = invite_href if invite_href.startswith("http") else f"https://www.linkedin.com{invite_href}"
                page.goto(full_invite_url, wait_until="domcontentloaded", timeout=25000)
                time.sleep(3.5)
            else:
                try:
                    connect_btn.click(timeout=5000)
                except Exception:
                    connect_btn.evaluate("el => el.click()")
                time.sleep(2.5)

            # Localizar el botón de envío dentro del diálogo de invitación ("Enviar sin nota" garantiza envío 100% en cuentas Free)
            send_no_note_btn = page.locator(
                "div[role='dialog'] button[aria-label='Enviar sin nota'], "
                "div[role='dialog'] button:has-text('Enviar sin nota'), "
                "div[role='dialog'] button[aria-label='Send without a note'], "
                "div[role='dialog'] button:has-text('Send without a note'), "
                "button[aria-label='Enviar sin nota'], "
                "button:has-text('Enviar sin nota')"
            ).first

            sent_ok = False
            note_used = ""

            if send_no_note_btn.count() > 0 and send_no_note_btn.is_visible() and send_no_note_btn.is_enabled():
                try:
                    send_no_note_btn.click(timeout=5000)
                except Exception:
                    send_no_note_btn.evaluate("el => el.click()")
                time.sleep(2.5)
                sent_ok = True
            else:
                # Fallback: si el diálogo muestra directamente "Enviar invitación"
                direct_send = page.locator(
                    "div[role='dialog'] button[aria-label='Enviar invitación'], "
                    "div[role='dialog'] button[aria-label='Send invitation']"
                ).first
                if direct_send.count() > 0 and direct_send.is_visible() and direct_send.is_enabled():
                    try:
                        direct_send.click(timeout=5000)
                    except Exception:
                        direct_send.evaluate("el => el.click()")
                    time.sleep(2.5)
                    sent_ok = True

            if sent_ok:
                AntiBanValidator.record_engagement("connection", company, f"-> {profile_name} ({target_role[:40]})")
                print(f"  [Connect] [✓] Solicitud enviada realmente a {profile_name} ({company})")
                return {
                    **action,
                    "status": "success",
                    "target_name": profile_name,
                    "target_url": profile_url,
                    "note_sent": note_used
                }

            # Si quedó algún modal abierto, cerrarlo
            dismiss = page.locator("div[role='dialog'] button[aria-label='Descartar'], div[role='dialog'] button[aria-label='Dismiss']").first
            if dismiss.count() > 0 and dismiss.is_visible():
                dismiss.click()

            return {**action, "status": "skipped", "reason": "send_button_not_enabled_in_dialog"}

        except Exception as e:
            print(f"  [Connect] Error: {e}")
            return {**action, "status": "error", "reason": str(e)}

    @classmethod
    def _execute_reaction(cls, page, action: Dict[str, Any]) -> Dict[str, Any]:
        """Reacciona (like) al primer post visible de la empresa target."""
        company = action.get("target_company", "")
        print(f"  [Reaction] Reaccionando a post de '{company}'...")

        try:
            from urllib.parse import quote_plus
            search_url = f"https://www.linkedin.com/search/results/content/?keywords={quote_plus(company)}"
            page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
            time.sleep(3)
            print(f"  [Connect] URL búsqueda personas: {page.url} (Título: {page.title()})")

            like_btn = page.locator("button[aria-label*='ecomendar'], button[aria-label*='ike']").first
            if like_btn.count() > 0 and like_btn.is_visible():
                like_btn.click()
                time.sleep(1)
                AntiBanValidator.record_engagement("reaction", company)
                print(f"  [Reaction] Like en post de {company}")
                return {**action, "status": "success"}

            return {**action, "status": "skipped", "reason": "like_button_not_found"}

        except Exception as e:
            return {**action, "status": "error", "reason": str(e)}

    @staticmethod
    def _generate_comment(company: str, post_context: str) -> Optional[str]:
        """Genera un comentario tecnico breve con Gemini."""
        if not GEMINI_API_KEY:
            return f"Interesante enfoque. Trabajando en sistemas similares con Python, la gestion de estos retos en produccion es clave. Gracias por compartir."

        try:
            from google import genai
            client = genai.Client(api_key=GEMINI_API_KEY)

            prompt = f"""Genera un comentario breve (2-3 frases, maximo 200 caracteres) para un post de LinkedIn de la empresa {company}.

            Contexto del post: {post_context[:300]}

            REGLAS:
            - Tono profesional y tecnico, como un ingeniero de software comentando a un colega.
            - Aporta valor: una observacion tecnica, pregunta inteligente o experiencia relacionada.
            - PROHIBIDO: 'gran post', 'totalmente de acuerdo', 'inspirador', emojis excesivos.
            - PROHIBIDO: autopromocion directa o mencionar tus proyectos.
            - Escribe en espanol.
            - Genera SOLO el texto del comentario, sin comillas ni explicaciones.
            """

            for model_name in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]:
                try:
                    response = client.models.generate_content(model=model_name, contents=prompt)
                    if response.text and len(response.text.strip()) > 20:
                        return response.text.strip()[:300]
                except Exception:
                    continue
        except Exception:
            pass

        return "Interesante planteamiento. En mi experiencia con sistemas similares, este tipo de decisiones de arquitectura marcan la diferencia en produccion."

    @staticmethod
    def _generate_connection_note(company: str, name: str, target_role: str = "Sistemas / Ciberseguridad / Desarrollo") -> str:
        """Genera una nota personalizada para solicitud de conexion (<= 195 chars para respetar limite de 200 chars de LinkedIn Free)."""
        full_greeting = f"Hola {name}," if name and name != "Responsable de Selección" else "Hola,"
        first_name = name.split()[0] if name and name != "Responsable de Selección" else ""
        greeting = f"Hola {first_name}," if first_name else "Hola,"

        if not GEMINI_API_KEY:
            return (
                f"{full_greeting} soy Gabriel Trujillo (DAM en Sevilla: Linux, Ciberseguridad y Python). "
                f"Sigo a {company} ({target_role[:22]}) y me encantaría conectar."
            )[:195]

        try:
            from google import genai
            from config import CANDIDATE_PROFILE
            client = genai.Client(api_key=GEMINI_API_KEY)

            prompt = f"""Genera una nota breve para una solicitud de conexión en LinkedIn.
            Destinatario: {name} (RRHH / Selección en {company}).
            Área o vacante detectada en {company}: {target_role}.
            Remitente: {CANDIDATE_PROFILE['name']}.
            Perfil: Desarrollador Junior / Graduado DAM en Sevilla (Linux, Ciberseguridad, Python/IA).

            REGLAS ESTRICTAS:
            - Máximo 185 caracteres (el límite de LinkedIn Free es 200 caracteres).
            - Tono cercano, profesional y directo.
            - Menciona Sevilla y tu interés en {company}.
            - Devuelve SOLO el texto de la nota en español, sin comillas.
            """

            for model_name in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]:
                try:
                    response = client.models.generate_content(model=model_name, contents=prompt)
                    if response.text and len(response.text.strip()) > 20:
                        return response.text.strip()[:195]
                except Exception:
                    continue
        except Exception:
            pass

        return (
            f"{greeting} soy Gabriel Trujillo (DAM en Sevilla: Linux, Ciberseguridad y Python). "
            f"Sigo a {company} ({target_role[:25]}) y me gustaría conectar."
        )[:195]

    @classmethod
    def _report_results(cls, results: List[Dict[str, Any]], chat_id: int) -> None:
        """Envia un resumen de resultados de ejecucion a Telegram."""
        import requests

        success = [r for r in results if r.get("status") == "success"]
        skipped = [r for r in results if r.get("status") == "skipped"]
        errors = [r for r in results if r.get("status") == "error"]

        lines = [f"*RESULTADO DEL ENGAGEMENT*\n"]
        lines.append(f"Exitosos: {len(success)}")
        lines.append(f"Omitidos: {len(skipped)}")
        lines.append(f"Errores: {len(errors)}\n")

        for r in success:
            emoji = {"comment": "💬", "connection": "🤝", "reaction": "👍"}.get(r["type"], "✅")
            person = r.get("target_name", "")
            url = r.get("target_url", "")
            person_str = f" ({person})" if person and person != "Responsable de Selección" else ""
            lines.append(f"{emoji} {r['type']} -> {r['target_company']}{person_str}")
            if url:
                lines.append(f"   🔗 {url}")

        if skipped:
            lines.append("\nOmitidos:")
            for r in skipped[:3]:
                lines.append(f"  - {r['target_company']}: {r.get('reason', '?')}")

        text = "\n".join(lines)

        try:
            res = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": text[:4000], "parse_mode": "Markdown", "disable_web_page_preview": True},
                timeout=10
            )
            if res.status_code != 200:
                requests.post(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                    json={"chat_id": chat_id, "text": text[:4000], "disable_web_page_preview": True},
                    timeout=10
                )
        except Exception:
            pass
