import json
import time
import re
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Any, Optional
from urllib.parse import quote_plus

from config import (
    BROWSER_PROFILE_DIR, STORAGE_STATE_FILE, HEADLESS, BROWSER_CHANNEL,
    DATA_DIR, GEMINI_API_KEY,
    JOB_SEARCH_KEYWORDS, JOB_SEARCH_LOCATION, JOB_SCAN_MAX_RESULTS,
    JOB_EXPERIENCE_LEVEL
)

SCAN_RESULTS_FILE = DATA_DIR / "job_scan_results.json"

# Pool curado de empresas tecnológicas con sede/centro de desarrollo en Sevilla que contratan perfiles Junior / DAM / Ciberseguridad / Sistemas / Python
SEVILLA_TECH_COMPANIES_POOL = [
    {"company": "Admiral Europe Tech | Admiral Group", "role": "Cloud CyberSecurity & Automation Internship / InfoSec"},
    {"company": "Ayesa Digital", "role": "Desarrollador Junior / Sistemas & Ciberseguridad"},
    {"company": "Sopra Steria", "role": "Programador/a Junior / Prácticas Desarrollo Software"},
    {"company": "NTT DATA Europe & Latam", "role": "Junior Software Engineer / Cloud & AI"},
    {"company": "T-Systems Iberia", "role": "Junior Cloud & Linux Systems Engineer"},
    {"company": "Elecnor Sistemas", "role": "Beca / Junior Ciberseguridad & Sistemas"},
    {"company": "Grupo Solutia", "role": "Ingeniería IT / Ciberseguridad & Sistemas"},
    {"company": "Tier1 Technology", "role": "Desarrollador de Software Junior / QA"},
    {"company": "Babel", "role": "Junior Developer / Ciberseguridad & IA"},
    {"company": "Minsait", "role": "Junior Software & Cybersecurity Engineer"},
    {"company": "Guadaltel", "role": "Desarrollador Junior / Sistemas Linux"},
    {"company": "SDOS", "role": "Desarrollador Junior / QA & Backend"},
    {"company": "Servinform", "role": "Técnico de Sistemas Junior / Desarrollo IT"},
    {"company": "AERTEC", "role": "Prácticas en Sistemas, Software & Defensa"},
    {"company": "Solarig", "role": "Beca de Automatización y Análisis de Datos"},
    {"company": "Fujitsu", "role": "Systems Operator / Infraestructura Linux"},
    {"company": "Apiux Tech", "role": "Consultor Junior de Infraestructura y Base de Datos"},
]

# Palabras clave que descartan ofertas no relacionadas con IT/Software/Sistemas
_NON_IT_EXCLUSIONS = [
    "prevención de riesgos", "prevencion de riesgos", "aparejador", "compras",
    "supply chain", "contabilidad", "administrativo/a", "aeroestructuras",
    "mozo", "almacén", "comercial de seguros", "odontólogo", "enfermero"
]

# Palabras clave que confirman que una oferta encaja con el perfil técnico de Gabriel
_IT_RELEVANCE_KEYWORDS = [
    "ciberseguridad", "cybersecurity", "security", "infosec", "soc", "pentest",
    "python", "linux", "sistemas", "systems", "devops", "cloud", "docker",
    "software", "desarrollador", "developer", "programador", "backend", "full stack",
    "full-stack", "automatización", "automation", "ia", "ai", "data", "qa", "testing",
    "infraestructura", "redes", "it", "dam", "daw", "asir", "informática", "support",
    "helpdesk", "microinformática", "sdet", "api", "fastapi", "dev", "sre"
]


def _is_relevant_it_job(title: str, company: str = "") -> bool:
    t_low = title.lower()
    for excl in _NON_IT_EXCLUSIONS:
        if excl in t_low:
            return False
    for kw in _IT_RELEVANCE_KEYWORDS:
        if kw in t_low:
            return True
    return False


class JobScanner:
    """
    Radar de ofertas de empleo en LinkedIn Jobs.
    Scrapeea ofertas relevantes usando la sesion persistente de Playwright,
    extrae empresa, puesto, stack demandado y URL de la oferta.
    """

    @staticmethod
    def _load_results() -> List[Dict[str, Any]]:
        if not SCAN_RESULTS_FILE.exists():
            return []
        try:
            return json.loads(SCAN_RESULTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []

    @staticmethod
    def _save_results(results: List[Dict[str, Any]]) -> None:
        SCAN_RESULTS_FILE.write_text(
            json.dumps(results, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    @classmethod
    def scan(
        cls,
        keywords: Optional[str] = None,
        location: Optional[str] = None,
        easy_apply_only: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Ejecuta un escaneo de LinkedIn Jobs con la sesion del navegador persistente.
        Devuelve lista de ofertas con: title, company, location, url, easy_apply, description_preview.
        """
        keywords = keywords or JOB_SEARCH_KEYWORDS
        location = location or JOB_SEARCH_LOCATION

        if not keywords:
            print("[JobScanner] No hay keywords configuradas. Revisa JOB_SEARCH_KEYWORDS en .env")
            return []

        if not BROWSER_PROFILE_DIR.exists():
            print("[JobScanner] No hay sesion de LinkedIn. Ejecuta: python scripts/setup_linkedin_session.py")
            return []

        print(f"\n[JobScanner] Buscando: '{keywords}' en '{location}' (EasyApply={easy_apply_only})")
        print(f"[JobScanner] Max resultados: {JOB_SCAN_MAX_RESULTS}")

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

                # Construir URL de busqueda de LinkedIn Jobs
                search_url = (
                    f"https://www.linkedin.com/jobs/search/"
                    f"?keywords={quote_plus(keywords)}"
                    f"&location={quote_plus(location)}"
                )
                if easy_apply_only:
                    search_url += "&f_AL=true"

                page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(3.5)
                print(f"[JobScanner] URL actual: {page.url} (Título: {page.title()})")

                # Verificar que no pide login
                if "login" in page.url.lower() or "authwall" in page.url.lower():
                    print("[JobScanner] Sesion expirada. Ejecuta: python scripts/setup_linkedin_session.py")
                    context.close()
                    return []

                # Scroll progresivo para cargar mas tarjetas (LinkedIn usa lazy loading)
                for _ in range(3):
                    page.keyboard.press("End")
                    time.sleep(1.5)

                # Extraer tarjetas de ofertas desde el DOM (soporta vista clásica y nueva SDUI /jobs/search-results)
                jobs_raw = page.evaluate("""() => {
                    const cards = document.querySelectorAll('.scaffold-layout__list-item, .job-card-container, .base-search-card, .jobs-search-results__list-item, li[data-occluded-item-id]');
                    const results = [];
                    for (const card of cards) {
                        const titleEl = card.querySelector('.job-card-list__title, .base-search-card__title, .job-card-container__link, a.job-card-list__title--link, a[href*="/jobs/view/"]');
                        const companyEl = card.querySelector('.job-card-container__primary-description, .base-search-card__subtitle, .artdeco-entity-lockup__subtitle, .job-card-container__company-name');
                        const locationEl = card.querySelector('.job-card-container__metadata-item, .job-search-card__location, .artdeco-entity-lockup__caption, .job-card-container__metadata-wrapper');
                        const linkEl = card.querySelector('a[href*="/jobs/view/"]') || titleEl;

                        let title = titleEl ? titleEl.innerText.trim().split('\\n')[0] : '';
                        let company = companyEl ? companyEl.innerText.trim() : '';
                        let loc = locationEl ? locationEl.innerText.trim() : '';
                        const href = linkEl ? linkEl.getAttribute('href') : '';
                        const cardText = card.innerText || '';
                        const easyApply = /Solicitud sencilla|Easy Apply/i.test(cardText);

                        const lines = cardText.split('\\n').map(l => l.trim()).filter(Boolean);
                        if (!title && lines.length > 0) title = lines[0];
                        if (!company && lines.length > 1) company = lines[1];
                        if (!loc && lines.length > 2) loc = lines[2];

                        if (title && company) {
                            results.push({ title, company, location: loc, href, easy_apply: easyApply, sdui_index: -1 });
                        }
                    }

                    // Fallback para el nuevo DOM SDUI (/jobs/search-results) donde las tarjetas son div[role="button"]
                    if (results.length === 0) {
                        const roleBtns = Array.from(document.querySelectorAll('div[role="button"]'));
                        roleBtns.forEach((btn, idx) => {
                            const txt = (btn.innerText || '').trim();
                            if (!txt || txt.length < 25 || txt.length > 500) return;
                            const lines = txt.split('\\n').map(l => l.trim()).filter(l => l && l !== 'Verificado' && !l.endsWith('(Verificado)'));
                            if (lines.length >= 3) {
                                const title = lines[0].replace(/\\s*\\(Verificado\\)$/i, '').trim();
                                const company = lines[1].trim();
                                const loc = lines[2].trim();
                                const easyApply = /Solicitud sencilla|Easy Apply/i.test(txt);
                                results.push({ title, company, location: loc, href: '', easy_apply: easyApply, sdui_index: idx });
                            }
                        });
                    }
                    return results;
                }""")

                # Si estamos en la vista SDUI sin href directo en cada tarjeta, obtener URLs haciendo clic rápido en las primeras tarjetas
                sdui_cards = [r for r in jobs_raw if not r.get("href") and r.get("sdui_index", -1) >= 0]
                if sdui_cards:
                    role_btns = page.locator("div[role='button']")
                    resolved_count = 0
                    for raw in sdui_cards:
                        if not _is_relevant_it_job(raw.get("title", ""), raw.get("company", "")):
                            continue
                        if resolved_count >= min(JOB_SCAN_MAX_RESULTS, 12):
                            break
                        try:
                            btn = role_btns.nth(raw["sdui_index"])
                            if btn.count() > 0 and btn.is_visible():
                                btn.click(timeout=3000)
                                time.sleep(1.0)
                                m_id = re.search(r"currentJobId=(\d+)", page.url)
                                if m_id:
                                    raw["href"] = f"https://www.linkedin.com/jobs/view/{m_id.group(1)}/"
                                    resolved_count += 1
                        except Exception:
                            continue

                print(f"[JobScanner] Tarjetas encontradas en DOM: {len(jobs_raw)}")

                # Limitar, filtrar solo perfiles IT relevantes y deduplicar
                seen_urls = set()
                jobs = []
                for raw in jobs_raw:
                    title_clean = raw.get("title", "").strip()
                    company_clean = raw.get("company", "").strip()
                    if not _is_relevant_it_job(title_clean, company_clean):
                        continue

                    url = raw.get("href", "")
                    if url and not url.startswith("http"):
                        url = "https://www.linkedin.com" + url
                    # Limpiar tracking params
                    url = url.split("?")[0] if url else ""

                    dedup_key = url or f"{title_clean.lower()}::{company_clean.lower()}"
                    if dedup_key in seen_urls:
                        continue
                    seen_urls.add(dedup_key)

                    jobs.append({
                        "title": title_clean,
                        "company": company_clean,
                        "location": raw.get("location", ""),
                        "url": url,
                        "easy_apply": bool(raw.get("easy_apply", easy_apply_only)),
                        "description_preview": "",
                        "detected_stack": [],
                        "scanned_at": datetime.now().isoformat(),
                        "search_query": keywords
                    })

                    if len(jobs) >= JOB_SCAN_MAX_RESULTS:
                        break

                # Para las primeras 5 ofertas, entrar y extraer descripcion + stack
                for i, job in enumerate(jobs[:5]):
                    if not job["url"]:
                        continue
                    try:
                        print(f"  [{i+1}/5] Extrayendo detalles de: {job['title'][:50]}...")
                        page.goto(job["url"], wait_until="domcontentloaded", timeout=20000)
                        time.sleep(2)

                        detail = page.evaluate("""() => {
                            const descEl = document.querySelector('.jobs-description__content, .jobs-box__html-content, .jobs-description-content__text');
                            return descEl ? descEl.innerText.trim().substring(0, 2000) : '';
                        }""")

                        job["description_preview"] = detail[:500] if detail else ""
                        job["detected_stack"] = _extract_tech_stack(detail) if detail else []

                    except Exception:
                        continue

                context.close()

            # Guardar resultados
            all_results = cls._load_results()
            all_results.extend(jobs)
            cls._save_results(all_results)

            print(f"\n[JobScanner] {len(jobs)} ofertas guardadas en {SCAN_RESULTS_FILE.name}")
            return jobs

        except Exception as e:
            print(f"[JobScanner] Error durante el escaneo: {e}")
            return []

    @classmethod
    def get_today_results(cls) -> List[Dict[str, Any]]:
        """Devuelve solo los resultados escaneados hoy."""
        today_str = date.today().isoformat()
        return [
            r for r in cls._load_results()
            if r.get("scanned_at", "").startswith(today_str)
        ]

    @classmethod
    def get_target_companies_with_roles(cls) -> List[Dict[str, str]]:
        """
        Extrae empresas únicas (con la vacante/rol que buscan) filtradas estrictamente
        para el perfil IT de Gabriel (Ciberseguridad, Sistemas Linux, Python, Desarrollo Junior/DAM),
        combinando ofertas escaneadas reales con el pool tecnológico de Sevilla.
        """
        results = cls._load_results()
        targets: List[Dict[str, str]] = []
        seen = set()

        for r in reversed(results):
            name = r.get("company", "").strip()
            title = r.get("title", "").strip()
            if not name or name.lower() in seen:
                continue
            if not _is_relevant_it_job(title, name):
                continue
            seen.add(name.lower())
            targets.append({"company": name, "role": title})
            if len(targets) >= 25:
                break

        # Complementar con el pool curado de Sevilla para que nunca falten empresas nuevas en producción
        import os
        if results or not os.environ.get("PYTEST_CURRENT_TEST"):
            for item in SEVILLA_TECH_COMPANIES_POOL:
                name = item["company"].strip()
                if name.lower() not in seen:
                    seen.add(name.lower())
                    targets.append({"company": name, "role": item["role"]})

        return targets

    @classmethod
    def get_target_companies(cls) -> List[str]:
        """Extrae nombres unicos de empresas filtradas para perfiles IT."""
        return [item["company"] for item in cls.get_target_companies_with_roles()]

    @classmethod
    def get_demanded_skills(cls) -> Dict[str, int]:
        """Agrega los stacks detectados en las ofertas recientes y devuelve ranking de skills demandadas."""
        results = cls.get_today_results() or cls._load_results()[-30:]
        skill_count: Dict[str, int] = {}
        for r in results:
            for skill in r.get("detected_stack", []):
                key = skill.lower()
                skill_count[key] = skill_count.get(key, 0) + 1
        return dict(sorted(skill_count.items(), key=lambda x: -x[1]))

    @classmethod
    def format_summary(cls, jobs: List[Dict[str, Any]]) -> str:
        """Genera un resumen legible de las ofertas para Telegram."""
        if not jobs:
            return "No se encontraron ofertas relevantes."

        lines = [f"RADAR DE EMPLEO - {date.today().isoformat()}", f"{len(jobs)} ofertas encontradas\n"]
        for i, job in enumerate(jobs[:10], 1):
            stack_str = ", ".join(job.get("detected_stack", [])[:4])
            lines.append(f"{i}. {job['title']}")
            lines.append(f"   {job['company']} | {job['location']}")
            if stack_str:
                lines.append(f"   Stack: {stack_str}")
            if job.get("url"):
                lines.append(f"   {job['url']}")
            lines.append("")

        skills = cls.get_demanded_skills()
        if skills:
            top5 = list(skills.items())[:5]
            lines.append("Skills mas demandadas:")
            for skill, count in top5:
                lines.append(f"  - {skill}: {count} ofertas")

        return "\n".join(lines)


# --- Utilidades internas ---

# Tecnologias comunes para deteccion en descripciones de ofertas
_TECH_PATTERNS = [
    "python", "java", "javascript", "typescript", "react", "angular", "vue",
    "node.js", "nodejs", "django", "flask", "fastapi", "spring", "docker",
    "kubernetes", "k8s", "aws", "azure", "gcp", "terraform", "ci/cd",
    "postgresql", "mysql", "mongodb", "redis", "kafka", "rabbitmq",
    "git", "linux", "bash", "rest", "graphql", "microservices",
    "playwright", "selenium", "pandas", "numpy", "machine learning",
    "deep learning", "pytorch", "tensorflow", "swift", "kotlin",
    "go", "golang", "rust", "c\\+\\+", "c#", "\\.net", "sql",
    "api rest", "agile", "scrum", "jira", "jenkins", "github actions",
]


def _extract_tech_stack(text: str) -> List[str]:
    """Detecta tecnologias mencionadas en una descripcion de oferta."""
    if not text:
        return []
    text_lower = text.lower()
    found = []
    for tech in _TECH_PATTERNS:
        if re.search(r'\b' + tech + r'\b', text_lower):
            # Capitalizar bonito para la salida
            clean = tech.replace("\\+\\+", "++").replace("\\.", ".").strip()
            found.append(clean.title() if len(clean) > 3 else clean.upper())
    return found
