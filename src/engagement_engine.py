import json
import time
import random
from typing import List, Dict, Any, Optional
from pathlib import Path

from config import (
    BROWSER_PROFILE_DIR, STORAGE_STATE_FILE, HEADLESS, BROWSER_CHANNEL, CHROMIUM_EXECUTABLE_PATH,
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

        # Filtrar empresas ya contactadas con éxito en los últimos 60 días (ventana temporal, no por conteo)
        history = AntiBanValidator._get_engagement_records()
        from datetime import datetime as _dt, timedelta as _td
        cutoff_60d = (_dt.now() - _td(days=60)).isoformat()
        already_contacted = {
            r.get("target", "").strip().lower()
            for r in history
            if r.get("action") == "connection"
            and r.get("status") == "success"
            and r.get("timestamp", "9999") >= cutoff_60d
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

        for idx_act, act in enumerate(actions):
            if not act.get("note_text"):
                act["note_text"] = cls._generate_connection_note(
                    act["target_company"],
                    act.get("target_name", "Responsable de Selección"),
                    act.get("target_headline") or act.get("target_role", "Sistemas / Ciberseguridad / Desarrollo"),
                    variation_idx=idx_act
                )

        return actions

    @classmethod
    def _discover_recruiter_previews(cls, actions: List[Dict[str, Any]]) -> None:
        """
        Pre-busca en LinkedIn perfiles de 2º GRADO (contactos de tus contactos) en SEVILLA:
        combina IT Recruiters/RRHH (~60%) y perfiles técnicos (Tech Lead, Developers, Sistemas ~40%)
        para ampliar el círculo hacia oportunidades de programación y sistemas.
        """
        from src.browser_helper import has_linkedin_session
        if not has_linkedin_session():
            return
        try:
            from urllib.parse import quote_plus
            from playwright.sync_api import sync_playwright
            import re

            history = AntiBanValidator._get_engagement_records()
            already_contacted_people = {
                r.get("detail", "").lower()
                for r in history[-60:]
                if r.get("action") == "connection" and r.get("status") == "success"
            }
            seen_urls: set[str] = set()
            seen_names: set[str] = set()

            sevilla_circle_queries = [
                'Sevilla ("IT Recruiter" OR "Talent Acquisition" OR "Seleccion IT" OR "Tech Recruiter")',
                'Sevilla ("Tech Lead" OR "Engineering Manager" OR "CTO" OR "Backend") (Python OR Software)',
                'Sevilla ("Responsable de Seleccion" OR "RRHH" OR "People") (IT OR Software OR Tech)',
                'Sevilla ("Desarrollador" OR "Software Engineer" OR "DevOps" OR "Sistemas Linux")',
            ]

            print("[Engagement] Pre-buscando contactos de 2º grado (contactos de tus contactos) en Sevilla...")
            with sync_playwright() as p:
                from src.browser_helper import get_playwright_browser_context, close_playwright_context
                context, browser = get_playwright_browser_context(p)
                page = context.pages[0] if context.pages else context.new_page()

                for idx_act, act in enumerate(actions):
                    company = act["target_company"]
                    # SIEMPRE 2º grado (&network=%5B%22S%22%5D = contactos de mis contactos) y foco en Sevilla
                    if idx_act % 3 == 1:
                        candidate_queries = [
                            f'{company} Sevilla ("Tech Lead" OR "Software Engineer" OR Backend OR Python OR Sistemas OR DevOps)',
                            f'{company} ("Tech Lead" OR "Desarrollador" OR CTO OR "Engineering Manager" OR Sistemas) Sevilla',
                            sevilla_circle_queries[idx_act % len(sevilla_circle_queries)],
                        ]
                    else:
                        candidate_queries = [
                            f'{company} Sevilla ("Recursos Humanos" OR RRHH OR recruiter OR "talent acquisition" OR seleccion OR IT)',
                            f'{company} ("Recursos Humanos" OR RRHH OR recruiter OR "talent acquisition" OR seleccion) Sevilla',
                            sevilla_circle_queries[idx_act % len(sevilla_circle_queries)],
                        ]

                    picked_ok = False
                    for q_idx, query in enumerate(candidate_queries):
                        if picked_ok:
                            break
                        search_url = (
                            f"https://www.linkedin.com/search/results/people/"
                            f"?keywords={quote_plus(query)}"
                            f"&network=%5B%22S%22%5D"
                            f"&origin=GLOBAL_SEARCH_HEADER"
                        )
                        try:
                            page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
                            time.sleep(2.5)
                            cards = page.evaluate("""() => {
                                const items = Array.from(document.querySelectorAll('div[role="listitem"], li.reusable-search__result-container, [data-view-name="search-entity-result-universal-template"]'));
                                const results = [];
                                for (const item of items) {
                                    const link = item.querySelector('a[href*="/in/"]');
                                    if (!link) continue;
                                    const rawUrl = (link.href || '').split('?')[0];
                                    const parts = rawUrl.split('/in/');
                                    if (parts.length < 2) continue;
                                    const vanity = parts[1].split('/')[0].trim();
                                    if (!vanity || vanity === 'opportunities') continue;
                                    const fullText = (item.innerText || '').trim();
                                    const lines = fullText.split('\\n').map(l => l.trim()).filter(Boolean);
                                    if (!lines.length) continue;
                                    const name = lines[0].split('•')[0].trim();
                                    const cleanLines = lines.filter(l => !l.startsWith('•') && l !== 'Conectar' && l !== 'Seguir' && l !== 'Enviar mensaje');
                                    const headline = cleanLines.length > 1 ? cleanLines[1] : '';
                                    const location = cleanLines.length > 2 ? cleanLines[2] : 'Sevilla';
                                    const mutual = cleanLines.find(l => l.includes('en común') || l.includes('shared connection')) || 'Contacto de 2º grado en común';
                                    results.push({
                                        name,
                                        vanity,
                                        url: 'https://www.linkedin.com/in/' + vanity + '/',
                                        invite_href: '/preload/custom-invite/?vanityName=' + vanity,
                                        headline,
                                        location,
                                        mutual
                                    });
                                }
                                return results;
                            }""")

                            for card in (cards or []):
                                cand_name = (card.get("name") or "").strip()
                                cand_url = (card.get("url") or "").strip()
                                href_attr = (card.get("invite_href") or "").strip()

                                if not cand_name or "miembro de linkedin" in cand_name.lower() or "linkedin member" in cand_name.lower():
                                    continue
                                if cand_name.lower() in seen_names:
                                    continue
                                if cand_url and cand_url in seen_urls:
                                    continue
                                if any(cand_name.lower() in prev for prev in already_contacted_people):
                                    continue

                                seen_names.add(cand_name.lower())
                                if cand_url:
                                    seen_urls.add(cand_url)

                                act["target_name"] = cand_name
                                if card.get("headline"):
                                    act["target_headline"] = card["headline"]
                                if cand_url:
                                    act["target_url"] = cand_url
                                if href_attr:
                                    act["invite_href"] = href_attr
                                act["mutual_info"] = card.get("mutual") or "Contacto de 2º grado en común"
                                act["location_info"] = card.get("location") or "Sevilla"
                                if q_idx == 2:
                                    act["target_company"] = f"Círculo Sevilla ({act['target_headline'][:28]})"
                                picked_ok = True
                                break
                        except Exception:
                            continue

                close_playwright_context(context, browser, persist=True)
        except Exception as e:
            print(f"[Engagement] Aviso en pre-búsqueda de perfiles: {e}")

    @classmethod
    def _build_engagement_message_and_keyboard(cls, actions: List[Dict[str, Any]]) -> tuple[str, dict]:
        summary = AntiBanValidator.get_today_engagement_summary()
        today_conns = summary.get("connection", 0) if summary else 0
        header = f"🤝 *Contactos Sevilla (2º grado)* · {len(actions)} propuestos"
        if today_conns:
            header += f" · Hoy: {today_conns}"

        lines = [header, "━━━━━━━━━━━━━━━━━━━━━━"]

        toggle_row = []
        for i, action in enumerate(actions, 1):
            enabled = action.get("enabled", True)
            state_icon = "✅" if enabled else "⏭️"
            person = (action.get("target_name") or "Responsable de Selección").replace("[", "(").replace("]", ")")
            company = (action.get("target_company") or "").replace("[", "(").replace("]", ")")
            headline = (action.get("target_headline") or "RRHH / Selección").strip()
            if len(headline) > 55:
                headline = headline[:52] + "..."
            loc = action.get("location_info", "Sevilla")
            url = action.get("target_url", "")

            person_link = f"[{person}]({url})" if url else f"*{person}*"
            company_part = f" · *{company}*" if company else ""
            lines.append(f"*{i}.* {state_icon} {person_link}{company_part}")
            lines.append(f"   _{headline}_ · {loc}")
            lines.append("")

            toggle_row.append({
                "text": f"{'✅' if enabled else '❌'} #{i}",
                "callback_data": f"engage:toggle_{i - 1}"
            })

        lines.append("Pulsa `#1..#5` para omitir alguno y luego *Enviar*:")
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
            from src.browser_helper import get_playwright_browser_context, close_playwright_context

            with sync_playwright() as p:
                context, browser_instance = get_playwright_browser_context(p)
                page = context.pages[0] if context.pages else context.new_page()
                print(f"[Engagement] Estableciendo sesión en Feed de LinkedIn...")
                page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
                time.sleep(2)
                feed_url = page.url.lower()
                print(f"[Engagement] URL Feed: {page.url} (Título: {page.title()})")

                if "login" in feed_url or "checkpoint" in feed_url or "authwall" in feed_url:
                    print(f"[Engagement] [⛔] Sesión expirada o requiere login ({page.url}). Abortando plan.")
                    close_playwright_context(context, browser_instance, persist=False)
                    return [{**action, "status": "error", "reason": "session_expired"} for action in actions]

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

                close_playwright_context(context, browser_instance, persist=True)

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
        """Conecta exclusivamente con contactos de 2º grado (contactos de tus contactos) en Sevilla."""
        company = action["target_company"]
        target_role = action.get("target_role", "Desarrollo de Software / Ciberseguridad / Sistemas")
        profile_name = action.get("target_name") or "Responsable de Selección"
        profile_url = action.get("target_url") or ""
        invite_href = action.get("invite_href") or ""
        print(f"  [Connect] Conectando con contacto de 2º grado en Sevilla: {profile_name} ('{company}')...")

        try:
            import re
            from urllib.parse import quote_plus
            connect_btn = None

            if not (invite_href and "/preload/" in invite_href):
                # Búsqueda estricta en 2º grado (network=["S"]) + Sevilla
                query = (
                    f'{profile_name} Sevilla'
                    if profile_name != "Responsable de Selección"
                    else f'{company} Sevilla ("Recursos Humanos" OR RRHH OR recruiter OR "talent acquisition" OR seleccion)'
                )
                search_url = (
                    f"https://www.linkedin.com/search/results/people/"
                    f"?keywords={quote_plus(query)}"
                    f"&network=%5B%22S%22%5D"
                    f"&origin=GLOBAL_SEARCH_HEADER"
                )
                page.goto(search_url, wait_until="domcontentloaded", timeout=25000)
                time.sleep(3.0)
                print(f"  [Connect] URL búsqueda personas (2º grado · Sevilla): {page.url}")

                cards = page.evaluate("""() => {
                    const items = Array.from(document.querySelectorAll('div[role="listitem"], li.reusable-search__result-container, [data-view-name="search-entity-result-universal-template"]'));
                    const results = [];
                    for (const item of items) {
                        const link = item.querySelector('a[href*="/in/"]');
                        if (!link) continue;
                        const rawUrl = (link.href || '').split('?')[0];
                        const parts = rawUrl.split('/in/');
                        if (parts.length < 2) continue;
                        const vanity = parts[1].split('/')[0].trim();
                        if (!vanity || vanity === 'opportunities') continue;
                        const fullText = (item.innerText || '').trim();
                        const lines = fullText.split('\\n').map(l => l.trim()).filter(Boolean);
                        if (!lines.length) continue;
                        const name = lines[0].split('•')[0].trim();
                        if (!name || name.toLowerCase().includes('miembro de linkedin') || name.toLowerCase().includes('linkedin member')) continue;
                        results.push({
                            name,
                            vanity,
                            url: 'https://www.linkedin.com/in/' + vanity + '/',
                            invite_href: '/preload/custom-invite/?vanityName=' + vanity
                        });
                    }
                    return results;
                }""")

                if not cards:
                    fallback_2nd_sevilla = (
                        f"https://www.linkedin.com/search/results/people/"
                        f"?keywords={quote_plus('Sevilla (RRHH OR Recruiter OR Talent OR Seleccion OR IT)')}"
                        f"&network=%5B%22S%22%5D"
                        f"&origin=GLOBAL_SEARCH_HEADER"
                    )
                    page.goto(fallback_2nd_sevilla, wait_until="domcontentloaded", timeout=25000)
                    time.sleep(3.0)
                    cards = page.evaluate("""() => {
                        const items = Array.from(document.querySelectorAll('div[role="listitem"], li.reusable-search__result-container, [data-view-name="search-entity-result-universal-template"]'));
                        const results = [];
                        for (const item of items) {
                            const link = item.querySelector('a[href*="/in/"]');
                            if (!link) continue;
                            const rawUrl = (link.href || '').split('?')[0];
                            const parts = rawUrl.split('/in/');
                            if (parts.length < 2) continue;
                            const vanity = parts[1].split('/')[0].trim();
                            if (!vanity || vanity === 'opportunities') continue;
                            const fullText = (item.innerText || '').trim();
                            const lines = fullText.split('\\n').map(l => l.trim()).filter(Boolean);
                            if (!lines.length) continue;
                            const name = lines[0].split('•')[0].trim();
                            if (!name || name.toLowerCase().includes('miembro de linkedin') || name.toLowerCase().includes('linkedin member')) continue;
                            results.push({
                                name,
                                vanity,
                                url: 'https://www.linkedin.com/in/' + vanity + '/',
                                invite_href: '/preload/custom-invite/?vanityName=' + vanity
                            });
                        }
                        return results;
                    }""")

                if not cards:
                    return {**action, "status": "skipped", "reason": "no_2nd_degree_connect_button"}

                picked = cards[0]
                profile_name = picked["name"]
                profile_url = picked["url"]
                invite_href = picked["invite_href"]

                # Actualizar nota con el nombre real si antes decía "Responsable de Selección"
                action["note_text"] = cls._generate_connection_note(
                    company,
                    profile_name,
                    target_role
                )

            print(f"  [Connect] Contacto seleccionado: {profile_name} ({profile_url or invite_href})")

            # Abrir modal de invitación navegando a /preload/custom-invite/
            if invite_href and "/preload/" in invite_href:
                full_invite_url = invite_href if invite_href.startswith("http") else f"https://www.linkedin.com{invite_href}"
                page.goto(full_invite_url, wait_until="domcontentloaded", timeout=25000)
                time.sleep(3.5)
            elif connect_btn is not None:
                try:
                    connect_btn.click(timeout=5000)
                except Exception:
                    connect_btn.evaluate("el => el.click()")
                time.sleep(2.5)

            sent_ok = False
            note_used = ""

            # Intentar enviar con la nota tipo fija si LinkedIn permite "Añadir una nota"
            note_to_send = (action.get("note_text") or "").strip()[:195]
            if note_to_send:
                clicked_add_note = page.evaluate("""() => {
                    const btns = Array.from(document.querySelectorAll('div[role="dialog"] button, button'));
                    const addBtn = btns.find(b => {
                        if (b.disabled) return false;
                        const txt = (b.innerText || '').trim().toLowerCase();
                        const aria = (b.getAttribute('aria-label') || '').trim().toLowerCase();
                        return txt.includes('añadir una nota') || txt.includes('add a note') || aria.includes('añadir una nota') || aria.includes('add a note');
                    });
                    if (addBtn) { addBtn.click(); return true; }
                    return false;
                }""")
                if clicked_add_note:
                    try:
                        time.sleep(1.5)
                        upsell_blocked = page.evaluate("""() => {
                            const txt = (document.body.innerText || '').toLowerCase();
                            return (
                                txt.includes('no te quedan notas personalizadas') ||
                                txt.includes('invitaciones personalizadas sin límites') ||
                                txt.includes('no personalized') ||
                                txt.includes('out of personalized') ||
                                txt.includes('personalized invitations left')
                            );
                        }""")
                        if upsell_blocked:
                            print("  [Connect] [i] Cuota mensual de notas personalizadas agotada (LinkedIn Free); enviando sin nota...")
                        else:
                            textarea = page.locator("div[role='dialog'] textarea[name='message'], div[role='dialog'] textarea#custom-message, div[role='dialog'] textarea").first
                            if textarea.count() > 0:
                                textarea.fill(note_to_send)
                                time.sleep(0.8)
                                clicked_send_note = page.evaluate("""() => {
                                    const btns = Array.from(document.querySelectorAll('div[role="dialog"] button'));
                                    const sendBtn = btns.find(b => {
                                        if (b.disabled) return false;
                                        const txt = (b.innerText || '').trim().toLowerCase();
                                        const aria = (b.getAttribute('aria-label') || '').trim().toLowerCase();
                                        return txt === 'enviar' || txt === 'send' || aria.includes('enviar invitación') || aria.includes('send invitation');
                                    });
                                    if (sendBtn) { sendBtn.click(); return true; }
                                    return false;
                                }""")
                                if clicked_send_note:
                                    time.sleep(2.5)
                                    sent_ok = True
                                    note_used = note_to_send
                        if not sent_ok:
                            # Volver atrás o recargar /preload/custom-invite/ si el upsell de Premium reemplazó el diálogo
                            went_back = page.evaluate("""() => {
                                const btns = Array.from(document.querySelectorAll('div[role="dialog"] button'));
                                const backBtn = btns.find(b => {
                                    const txt = (b.innerText || '').trim().toLowerCase();
                                    const aria = (b.getAttribute('aria-label') || '').trim().toLowerCase();
                                    return txt.includes('cancelar') || txt.includes('atrás') || aria.includes('cancelar') || aria.includes('atrás') || aria.includes('back');
                                });
                                if (backBtn) { backBtn.click(); return true; }
                                return false;
                            }""")
                            if went_back:
                                time.sleep(1.0)
                            has_no_note = page.evaluate("""() => {
                                const btns = Array.from(document.querySelectorAll('div[role="dialog"] button, button'));
                                return btns.some(b => {
                                    if (b.disabled) return false;
                                    const txt = (b.innerText || '').trim().toLowerCase();
                                    const aria = (b.getAttribute('aria-label') || '').trim().toLowerCase();
                                    return txt.includes('enviar sin nota') || txt.includes('send without a note') || aria.includes('enviar sin nota') || aria.includes('send without a note');
                                });
                            }""")
                            if not has_no_note:
                                if invite_href and "/preload/" in invite_href:
                                    full_invite_url = invite_href if invite_href.startswith("http") else f"https://www.linkedin.com{invite_href}"
                                    page.goto(full_invite_url, wait_until="domcontentloaded", timeout=25000)
                                    time.sleep(2.5)
                                elif connect_btn is not None:
                                    page.evaluate("""() => {
                                        const dismiss = document.querySelector('div[role="dialog"] button[aria-label="Descartar"], div[role="dialog"] button[aria-label="Dismiss"]');
                                        if (dismiss) dismiss.click();
                                    }""")
                                    time.sleep(1.0)
                                    try:
                                        connect_btn.click(timeout=5000)
                                    except Exception:
                                        connect_btn.evaluate("el => el.click()")
                                    time.sleep(2.0)
                    except Exception:
                        pass

            # Fallback estándar / cuenta Free sin cuota de notas: "Enviar sin nota"
            if not sent_ok:
                clicked_no_note = page.evaluate("""() => {
                    const btns = Array.from(document.querySelectorAll('div[role="dialog"] button, button'));
                    const sendNoNote = btns.find(b => {
                        if (b.disabled) return false;
                        const txt = (b.innerText || '').trim().toLowerCase();
                        const aria = (b.getAttribute('aria-label') || '').trim().toLowerCase();
                        return txt.includes('enviar sin nota') || txt.includes('send without a note') || aria.includes('enviar sin nota') || aria.includes('send without a note') || aria === 'enviar invitación' || aria === 'send invitation';
                    });
                    if (sendNoNote) { sendNoNote.click(); return true; }
                    return false;
                }""")
                if clicked_no_note:
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
            page.evaluate("""() => {
                const dismiss = document.querySelector('div[role="dialog"] button[aria-label="Descartar"], div[role="dialog"] button[aria-label="Dismiss"]');
                if (dismiss) dismiss.click();
            }""")

            print(f"  [Connect] [!] Saltado {profile_name} ({company}): send_button_not_enabled_in_dialog")
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
        """Genera un comentario tecnico breve, natural y sin muletillas de IA."""
        if not GEMINI_API_KEY:
            return "Muy buen punto. Cuando he montado cosas parecidas en Python, esa parte suele ser justo donde más se nota la diferencia al llevarlo a uso real."

        try:
            from google import genai
            client = genai.Client(api_key=GEMINI_API_KEY)

            prompt = f"""Escribe un comentario corto (1-2 frases, máximo 190 caracteres) para un post de LinkedIn de {company}.

            Contexto del post: {post_context[:300]}

            REGLAS:
            - Escribe como un desarrollador real español hablando de tú a tú a un compañero del sector.
            - Nada de tono corporativo ni clichés de IA ('gran post', 'interesante planteamiento', 'totalmente de acuerdo', 'marca la diferencia en producción', 'sinergias', emojis).
            - Aporta una pregunta concreta o un detalle práctico breve.
            - Devuelve SOLO el texto en español, sin comillas.
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

        return "Muy buen punto. En proyectos propios con Python suele ser justo la parte que más tiempo ahorra luego al mantenerlo."

    @staticmethod
    def _generate_connection_note(
        company: str,
        name: str,
        target_role: str = "Sistemas / Ciberseguridad / Desarrollo",
        variation_idx: Optional[int] = None
    ) -> str:
        """
        Genera el mensaje tipo fijo, honesto y directo de presentación para todas las conexiones,
        personalizado siempre con el nombre propio del contacto (< 200 caracteres).
        """
        raw_name = (name or "").strip()
        if raw_name and raw_name != "Responsable de Selección" and "miembro de linkedin" not in raw_name.lower():
            first_name = raw_name.split()[0].strip(",.")
            greeting = f"Hola {first_name},"
        else:
            greeting = "Hola,"

        note = (
            f"{greeting} soy Gabriel. Acabo de terminar mis estudios de DAM y busco mi primera "
            f"oportunidad en el mundo IT con muchas ganas de aportar y aprender. ¿Conectamos?"
        )
        if len(note) > 195:
            note = (
                f"{greeting} soy Gabriel. Acabo de terminar DAM y busco mi primera oportunidad "
                f"en el mundo IT con muchas ganas. ¿Conectamos?"
            )
        return note[:195]

    @classmethod
    def _report_results(cls, results: List[Dict[str, Any]], chat_id: int) -> None:
        """Envia un resumen de resultados de ejecucion a Telegram."""
        import requests

        success = [r for r in results if r.get("status") == "success"]
        skipped = [r for r in results if r.get("status") == "skipped"]
        errors = [r for r in results if r.get("status") == "error"]

        lines = [
            "🤝 *Resultado de Contactos*",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"✅ Exitosos: {len(success)}  ·  ⏭️ Omitidos: {len(skipped)}  ·  ❌ Errores: {len(errors)}",
            ""
        ]

        for r in success:
            emoji = {"comment": "💬", "connection": "🤝", "reaction": "👍"}.get(r["type"], "✅")
            person = (r.get("target_name") or "").replace("[", "(").replace("]", ")")
            url = r.get("target_url", "")
            company = r.get("target_company", "")
            label = f"[{person}]({url})" if (person and url) else (person or company)
            tail = f" ({company})" if person and company else ""
            lines.append(f"{emoji} {label}{tail}")

        if skipped:
            lines.append("\n⏭️ *Omitidos:*")
            for r in skipped[:5]:
                who = r.get("target_name") or r.get("target_company", "Contacto")
                lines.append(f"  • {who}: `{r.get('reason', '?')}`")

        session_err = any(r.get("reason") == "session_expired" for r in results)
        if session_err:
            lines.append("\n⚠️ *Tu sesión de LinkedIn ha expirado o requiere login.*")
            lines.append("Ejecuta /health o renueva la sesión para poder enviar invitaciones.")

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
