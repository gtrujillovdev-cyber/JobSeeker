import json
import re
import time
import random
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import quote_plus

from config import (
    BASE_DIR, BROWSER_PROFILE_DIR, HEADLESS, BROWSER_CHANNEL, CHROMIUM_EXECUTABLE_PATH,
    DATA_DIR, OUTPUT_DIR, SCREENSHOTS_DIR,
    GEMINI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    JOB_SEARCH_LOCATION, CANDIDATE_PROFILE
)
from src.job_scanner import _is_relevant_it_job, _extract_tech_stack
from src.ats_analyzer import ATSAnalyzer

EASY_APPLY_HISTORY_FILE = DATA_DIR / "easy_apply_history.json"
PENDING_EASY_APPLY_FILE = DATA_DIR / "pending_easy_apply.json"
CVS_OUTPUT_DIR = OUTPUT_DIR / "cvs"
CVS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# Directorio de CVs oficiales reales precargados
ASSETS_CVS_DIR = BASE_DIR / "assets" / "cvs"
ASSETS_CVS_DIR.mkdir(parents=True, exist_ok=True)

# Catálogo de perfiles reutilizando los PDFs oficiales existentes de Gabriel
CV_PROFILES: Dict[str, Dict[str, Any]] = {
    "sys_cyber": {
        "key": "sys_cyber",
        "label": "Sistemas Linux, Ciberseguridad & Infraestructura IT",
        "linkedin_resume_name": "GTV_CV_Sys_ES2026.pdf",
        "official_pdf_filename": "GTV_CV_Sys_ES2026.pdf",
        "headline": "Técnico de Sistemas Linux, Ciberseguridad & Automatización Python (DAM)",
        "keywords": [
            "linux", "sistemas", "systems", "ciberseguridad", "cybersecurity", "security",
            "soc", "siem", "redes", "network", "infraestructura", "infrastructure", "devops",
            "cloud", "docker", "bash", "support", "soporte", "helpdesk", "asir", "sysadmin",
            "operador", "microinformática", "seguridad", "firewall", "pentest", "it"
        ],
    },
    "qa_sdet": {
        "key": "qa_sdet",
        "label": "QA Automation, SDET & Testing con Playwright/Python",
        "linkedin_resume_name": "GTV_CV_ES2026.pdf",
        "official_pdf_filename": "GTV_CV_ES2026.pdf",
        "headline": "QA Automation Engineer / SDET Junior · Python, Playwright & Pytest (DAM)",
        "keywords": [
            "qa", "sdet", "test", "testing", "tester", "playwright", "selenium", "cypress",
            "calidad", "quality", "pytest", "e2e", "pruebas", "automatización de pruebas",
            "automation", "bug", "regression", "jira"
        ],
    },
    "ai_python": {
        "key": "ai_python",
        "label": "Desarrollo Python, Backend, Automatización & IA",
        "linkedin_resume_name": "GTV_CV_IA_ES2026.pdf",
        "official_pdf_filename": "GTV_CV_IA_ES2026.pdf",
        "headline": "Python Backend & AI Automation Developer Junior (DAM)",
        "keywords": [
            "python", "ia", "ai", "inteligencia artificial", "llm", "rag", "fastapi",
            "django", "flask", "backend", "data", "datos", "api", "bot", "machine learning",
            "automatización", "pandas", "sql", "etl", "genai", "gemini", "openai"
        ],
    },
    "ios_dam": {
        "key": "ios_dam",
        "label": "Desarrollo Multiplataforma (DAM), SwiftUI & Full-Stack",
        "linkedin_resume_name": "GTV_CV_iOS_ES2026.pdf",
        "official_pdf_filename": "GTV_CV_iOS_ES2026.pdf",
        "headline": "Desarrollador de Aplicaciones Multiplataforma Junior (DAM) · SwiftUI, Python & Web",
        "keywords": [
            "dam", "multiplataforma", "ios", "swift", "swiftui", "mobile", "móvil",
            "android", "kotlin", "java", "frontend", "fullstack", "full stack", "full-stack",
            "javascript", "typescript", "react", "html", "css", "web", "desarrollador",
            "programador", "software", "junior"
        ],
    }
}


class EasyApplyEngine:
    """
    Motor de Solicitud Sencilla (Easy Apply) en LinkedIn con selector y generador
    de Currículum Adaptado al puesto (Human-in-the-Loop por Telegram o ejecución directa).
    """

    @staticmethod
    def _load_history() -> List[Dict[str, Any]]:
        if not EASY_APPLY_HISTORY_FILE.exists():
            return []
        try:
            return json.loads(EASY_APPLY_HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []

    @staticmethod
    def _save_history(records: List[Dict[str, Any]]) -> None:
        EASY_APPLY_HISTORY_FILE.write_text(
            json.dumps(records, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    @classmethod
    def record_application(cls, job: Dict[str, Any], status: str, reason: str = "") -> None:
        records = cls._load_history()
        records.append({
            "date": date.today().isoformat(),
            "timestamp": datetime.now().isoformat(),
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "url": job.get("url", ""),
            "cv_profile": job.get("cv_profile_key", ""),
            "cv_label": job.get("cv_label", ""),
            "cv_pdf_path": job.get("cv_pdf_path", ""),
            "status": status,
            "reason": reason
        })
        cls._save_history(records)

    @classmethod
    def get_already_applied_urls(cls) -> set:
        return {
            r.get("url", "").split("?")[0].rstrip("/")
            for r in cls._load_history()
            if r.get("status") == "success" and r.get("url")
        }

    # ------------------------------------------------------------------
    # 1. SELECCIÓN INTELIGENTE Y GENERACIÓN DEL CV MÁS ADAPTADO AL PUESTO
    # ------------------------------------------------------------------
    @classmethod
    def select_best_cv_profile(cls, job: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analiza el título, stack detectado y descripción con ATSAnalyzer (HR Tech)
        para calcular el Score ATS exacto y elegir el mejor CV oficial pre-existente.
        """
        title = job.get("title") or ""
        desc = job.get("description_preview") or ""
        stack = job.get("detected_stack") or []

        ats_analysis = ATSAnalyzer.analyze_match(title, desc, stack)

        best_key = ats_analysis["best_profile_key"]
        prof = CV_PROFILES.get(best_key, CV_PROFILES["sys_cyber"])

        matched_str = ", ".join(ats_analysis["matched_keywords"][:5]) if ats_analysis["matched_keywords"] else "perfil DAM general"
        reason = f"Score ATS: {ats_analysis['ats_score']}% ({ats_analysis['tier_badge']}) · Keywords: {matched_str}"

        return {
            "cv_profile_key": best_key,
            "cv_label": ats_analysis["best_label"],
            "cv_linkedin_name": ats_analysis["best_cv"],
            "cv_headline": prof.get("headline", ""),
            "cv_reason": reason,
            "cv_score": ats_analysis["ats_score"],
            "cv_matched_keywords": ats_analysis["matched_keywords"],
            "ats_analysis": ats_analysis
        }

    @classmethod
    def build_tailored_cv_html(cls, job: Dict[str, Any]) -> str:
        """
        Construye el HTML de 1 página optimizado para ATS (Applicant Tracking Systems):
        - Estructura estándar ATS limpia (sin tablas complejas, fuentes estándar, etiquetas semánticas h1/h2/p/ul).
        - Extracción e inyección de palabras clave de la vacante (Keywords matching exacto).
        - Inclusión de metadatos y sección técnica indexable con stack tecnológico normalizado.
        """
        prof_key = job.get("cv_profile_key") or cls.select_best_cv_profile(job)["cv_profile_key"]
        prof = CV_PROFILES.get(prof_key, CV_PROFILES["sys_cyber"])
        target_title = job.get("title", "Desarrollador / Ingeniero IT")
        target_company = job.get("company", "Empresa Tecnológica")
        detected_stack = job.get("detected_stack") or []
        desc_preview = job.get("description_preview", "")

        # Inyección dinámica de palabras clave del puesto para scoring ATS
        keywords_pool = list(dict.fromkeys(detected_stack + prof["keywords"][:8]))
        ats_keywords_str = " · ".join(keywords_pool[:12])

        custom_summary = prof["summary"]
        if detected_stack:
            stack_highlight = ", ".join(detected_stack[:6])
            custom_summary += f" Especializado en la resolución de problemas técnicos aplicando {stack_highlight} y metodologías de ingeniería orientadas a resultados en {target_company}."

        skills_html = "".join(f"<li>{s}</li>" for s in prof["core_skills"])
        projects_html = "".join(
            f"""
            <div class="proj">
                <div class="proj-head"><strong>{p['name']}</strong> — <span class="proj-stack">{p['stack']}</span></div>
                <div class="proj-desc">{p['desc']}</div>
            </div>
            """
            for p in prof["projects"]
        )

        return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="keywords" content="{ats_keywords_str}">
<meta name="description" content="Currículum Técnico de Gabriel Trujillo Vallejo adaptado para {target_title}">
<title>Gabriel Trujillo Vallejo - CV {target_title}</title>
<style>
  @page {{ size: A4; margin: 12mm 15mm; }}
  body {{ font-family: Arial, Helvetica, sans-serif; color: #111827; line-height: 1.35; font-size: 10pt; margin: 0; padding: 0; }}
  .header {{ border-bottom: 2px solid #1e3a8a; padding-bottom: 6px; margin-bottom: 8px; }}
  .name {{ font-size: 20pt; font-weight: bold; color: #1e3a8a; margin: 0; text-transform: uppercase; letter-spacing: 0.5px; }}
  .headline {{ font-size: 11pt; font-weight: bold; color: #2563eb; margin: 3px 0 4px 0; }}
  .contact {{ font-size: 9pt; color: #374151; }}
  .section-title {{ font-size: 10.5pt; font-weight: bold; text-transform: uppercase; color: #1e3a8a; border-bottom: 1px solid #93c5fd; padding-bottom: 2px; margin-top: 9px; margin-bottom: 5px; }}
  .ats-keywords {{ font-size: 8.5pt; color: #4b5563; background: #f3f4f6; padding: 4px 6px; border-radius: 3px; margin-bottom: 6px; }}
  p {{ margin: 0 0 5px 0; text-align: justify; }}
  ul {{ margin: 0 0 5px 0; padding-left: 18px; }}
  li {{ margin-bottom: 2px; }}
  .proj {{ margin-bottom: 6px; }}
  .proj-head {{ font-size: 9.8pt; color: #111827; }}
  .proj-stack {{ color: #1d4ed8; font-weight: 600; font-size: 9pt; }}
  .proj-desc {{ font-size: 9.2pt; color: #374151; }}
  .edu-item {{ margin-bottom: 3px; display: flex; justify-content: space-between; }}
</style>
</head>
<body>
  <div class="header">
    <h1 class="name">GABRIEL TRUJILLO VALLEJO</h1>
    <div class="headline">{prof['headline']}</div>
    <div class="contact">
      Ubicación: Sevilla, España (Disponibilidad: Presencial / Híbrido / Remoto) | 
      Teléfono: +34 661 666 806 | 
      Email: gtrujillov.dev@gmail.com | 
      LinkedIn: linkedin.com/in/gabriel-trujillo-vallejo-9b3088196 | 
      GitHub: github.com/gtrujillovdev-cyber
    </div>
  </div>

  <div class="section-title">Perfil Técnico Profesional · Optimizado para {target_title[:55]}</div>
  <p>{custom_summary}</p>
  <div class="ats-keywords"><strong>Palabras Clave & Tecnologías Relevantes (ATS):</strong> {ats_keywords_str}</div>

  <div class="section-title">Habilidades Técnicas y Competencias</div>
  <ul>{skills_html}</ul>

  <div class="section-title">Proyectos de Ingeniería Aplicada (GitHub)</div>
  {projects_html}

  <div class="section-title">Educación, Titulaciones Oficiales y Certificaciones</div>
  <div class="edu-item">
    <div><strong>Grado Superior en Desarrollo de Aplicaciones Multiplataforma (DAM)</strong> — CESUR Sevilla</div>
    <div>2024 – 2026</div>
  </div>
  <div class="edu-item">
    <div><strong>Certificación Profesional en Ciberseguridad de Google</strong> (Linux, Redes, SIEM, Python, SQL)</div>
    <div>Acreditada</div>
  </div>
  <div class="edu-item">
    <div><strong>Especialización en Automatización en Python, Testing E2E e Integración de IA</strong></div>
    <div>Acreditada</div>
  </div>

  <div class="section-title">Idiomas y Disponibilidad de Contratación</div>
  <p><strong>Español:</strong> Nativo | <strong>Inglés:</strong> B2 Profesional (Capacidad técnica y documentación fluida) | <strong>Incorporación:</strong> Inmediata sin restricciones de movilidad.</p>
</body>
</html>"""

    @classmethod
    def get_existing_official_cv(cls, job: Dict[str, Any]) -> Path:
        """
        Obtiene el archivo PDF oficial real ya existente que mejor corresponde al puesto
        según el perfil (Sys/Linux/Cyber, AI/Python, iOS/DAM o General).
        Cero generación ad-hoc: reutiliza exactamente tus CVs oficiales de assets/cvs/.
        """
        if "cv_profile_key" not in job:
            job.update(cls.select_best_cv_profile(job))

        prof_key = job.get("cv_profile_key", "sys_cyber")
        prof = CV_PROFILES.get(prof_key, CV_PROFILES["sys_cyber"])
        pdf_name = prof.get("official_pdf_filename", "GTV_CV_ES2026.pdf")
        pdf_path = ASSETS_CVS_DIR / pdf_name

        if not pdf_path.exists():
            # Fallback a cualquier PDF en assets/cvs
            candidates = list(ASSETS_CVS_DIR.glob("*.pdf"))
            if candidates:
                pdf_path = candidates[0]

        job["cv_pdf_path"] = str(pdf_path)
        return pdf_path

    # ------------------------------------------------------------------
    # 2. ESCANEO DE VACANTES CON SOLICITUD SENCILLA (EASY APPLY)
    # ------------------------------------------------------------------
    @classmethod
    def scan_easy_apply_jobs(
        cls,
        keywords: Optional[str] = None,
        location: Optional[str] = None,
        max_results: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Busca ofertas activas en LinkedIn con filtro 'Solicitud sencilla' (&f_AL=true),
        extrae su descripción y stack, y selecciona/genera el CV más adaptado para cada una.
        """
        if not BROWSER_PROFILE_DIR.exists():
            print("[EasyApply] No hay sesión de LinkedIn configurada.")
            return []

        already_applied = cls.get_already_applied_urls()
        search_plans = []
        if keywords:
            search_plans.append((keywords, location or JOB_SEARCH_LOCATION))
        else:
            search_plans = [
                ("Python OR QA OR Linux OR Ciberseguridad OR Sistemas OR Junior OR DAM", "Sevilla"),
                ("Junior Developer OR Python OR QA Automation OR Sistemas Linux OR Ciberseguridad", "España"),
            ]

        discovered_jobs: List[Dict[str, Any]] = []
        seen_urls = set(already_applied)

        try:
            from playwright.sync_api import sync_playwright
            from src.browser_helper import get_playwright_browser_context

            with sync_playwright() as p:
                browser, context = get_playwright_browser_context(p)
                page = context.pages[0] if context.pages else context.new_page()

                for kw_query, loc_query in search_plans:
                    if len(discovered_jobs) >= max_results:
                        break

                    search_url = (
                        f"https://www.linkedin.com/jobs/search/"
                        f"?keywords={quote_plus(kw_query)}"
                        f"&location={quote_plus(loc_query)}"
                        f"&f_AL=true"
                    )
                    print(f"[EasyApply] Buscando vacantes de Solicitud Sencilla: '{kw_query}' en '{loc_query}'...")
                    page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                    time.sleep(3.5)

                    # Extraer tarjetas del nuevo DOM SDUI (div[role="button"]) o clásico
                    cards_meta = page.evaluate("""() => {
                        const out = [];
                        // 1. Enlaces directos si existen
                        const links = document.querySelectorAll('a[href*="/jobs/view/"]');
                        links.forEach(a => {
                            const txt = (a.innerText || '').trim();
                            if (txt.length > 5) {
                                out.push({ type: 'link', title: txt.split('\\n')[0].trim(), company: '', location: '', href: a.href.split('?')[0], idx: -1 });
                            }
                        });
                        // 2. Tarjetas SDUI div[role="button"] en la columna izquierda
                        const roleBtns = Array.from(document.querySelectorAll('div[role="button"]'));
                        roleBtns.forEach((btn, idx) => {
                            const txt = (btn.innerText || '').trim();
                            if (!txt || txt.length < 25 || txt.length > 500) return;
                            if (!/Solicitud sencilla|Easy Apply/i.test(txt)) return;
                            const lines = txt.split('\\n').map(l => l.trim()).filter(l => l && l !== 'Verificado' && !l.endsWith('(Verificado)'));
                            if (lines.length >= 3) {
                                const title = lines[0].replace(/\\s*\\(Verificado\\)$/i, '').trim();
                                const company = lines[1].trim();
                                const loc = lines[2].trim();
                                out.push({ type: 'sdui', title, company, location: loc, href: '', idx });
                            }
                        });
                        return out;
                    }""")

                    role_btns = page.locator("div[role='button']")
                    for card in cards_meta:
                        if len(discovered_jobs) >= max_results:
                            break
                        title = card.get("title", "").strip()
                        company = card.get("company", "").strip()
                        if title and not _is_relevant_it_job(title, company):
                            continue

                        job_url = card.get("href", "")
                        if not job_url and card.get("type") == "sdui" and card.get("idx", -1) >= 0:
                            try:
                                btn = role_btns.nth(card["idx"])
                                if btn.count() > 0 and btn.is_visible():
                                    btn.click(timeout=3000)
                                    time.sleep(1.2)
                                    m_id = re.search(r"currentJobId=(\d+)", page.url)
                                    if m_id:
                                        job_url = f"https://www.linkedin.com/jobs/view/{m_id.group(1)}/"
                            except Exception:
                                continue

                        if not job_url:
                            continue
                        clean_url = job_url.split("?")[0].rstrip("/")
                        if clean_url in seen_urls:
                            continue
                        seen_urls.add(clean_url)

                        discovered_jobs.append({
                            "title": title,
                            "company": company,
                            "location": card.get("location", loc_query),
                            "url": clean_url + "/",
                            "easy_apply": True,
                            "enabled": True
                        })

                # Enriquecer cada oferta visitando su página /jobs/view/<id>/, verificando botón Solicitud sencilla
                # y además descubriendo ofertas similares con Solicitud sencilla si faltan hasta max_results
                verified_jobs: List[Dict[str, Any]] = []
                idx_cursor = 0
                while idx_cursor < len(discovered_jobs) and len(verified_jobs) < max_results:
                    job = discovered_jobs[idx_cursor]
                    idx_cursor += 1
                    try:
                        page.goto(job["url"], wait_until="domcontentloaded", timeout=25000)
                        time.sleep(2.5)

                        page_info = page.evaluate("""() => {
                            const bodyText = document.body.innerText || '';
                            const h1 = document.querySelector('h1, .job-details-jobs-unified-top-card__job-title');
                            const title = h1 ? h1.innerText.trim() : document.title.split('|')[0].trim();
                            // Verificar botón Solicitud sencilla
                            const easyBtn = document.querySelector('button[aria-label*="Solicitud sencilla"], button[aria-label*="Easy Apply"]')
                                || Array.from(document.querySelectorAll('button')).find(b => /Solicitud sencilla|Easy Apply/i.test(b.innerText || ''));
                            const alreadySent = /Solicitud enviada|Application submitted/i.test(bodyText.substring(0, 1500));

                            // Extraer empleos similares con Solicitud sencilla en la misma página
                            const similar = [];
                            document.querySelectorAll('a[href*="/jobs/view/"]').forEach(a => {
                                const t = (a.innerText || '').trim();
                                if (/Solicitud sencilla|Easy Apply/i.test(t)) {
                                    const lines = t.split('\\n').map(l => l.trim()).filter(Boolean);
                                    if (lines.length >= 3) {
                                        similar.push({
                                            title: lines[0].replace(/\\s*\\(Verificado\\)$/i, '').trim(),
                                            company: lines[1],
                                            location: lines[2],
                                            url: a.href.split('?')[0]
                                        });
                                    }
                                }
                            });

                            return {
                                title,
                                hasEasyApply: Boolean(easyBtn) && !alreadySent,
                                desc: bodyText.substring(0, 3500),
                                similar
                            };
                        }""")

                        # Añadir similares relevantes a la cola por si necesitamos completar max_results
                        for sim in page_info.get("similar", []):
                            sim_url = sim.get("url", "").split("?")[0].rstrip("/")
                            if sim_url and sim_url not in seen_urls and _is_relevant_it_job(sim.get("title", ""), sim.get("company", "")):
                                seen_urls.add(sim_url)
                                discovered_jobs.append({
                                    "title": sim["title"],
                                    "company": sim["company"],
                                    "location": sim.get("location", ""),
                                    "url": sim_url + "/",
                                    "easy_apply": True,
                                    "enabled": True
                                })

                        if not page_info.get("hasEasyApply"):
                            continue

                        if not job.get("title") and page_info.get("title"):
                            job["title"] = page_info["title"]

                        desc_text = page_info.get("desc", "")
                        job["description_preview"] = desc_text[:600]
                        job["detected_stack"] = _extract_tech_stack(desc_text)

                        # Seleccionar y asociar el PDF oficial existente más adecuado a esta oferta
                        cv_info = cls.select_best_cv_profile(job)
                        job.update(cv_info)
                        cls.get_existing_official_cv(job)

                        verified_jobs.append(job)
                        print(f"  [EasyApply] [✓] Vacante verificada: {job['title']} ({job['company']}) -> CV: {job['cv_label']}")
                    except Exception as e_job:
                        print(f"  [EasyApply] Aviso verificando {job.get('url')}: {e_job}")
                        continue

                context.close()
                return verified_jobs

        except Exception as e:
            print(f"[EasyApply] Error en escaneo Easy Apply: {e}")
            return []

    # ------------------------------------------------------------------
    # 3. EJECUCIÓN DEL FLUJO MULTI-PASO EASY APPLY EN PLAYWRIGHT
    # ------------------------------------------------------------------
    @classmethod
    def _answer_additional_question(cls, label: str, job: Dict[str, Any], is_numeric: bool = False) -> str:
        """
        Responde preguntas adicionales de formularios Easy Apply de forma coherente
        con el perfil real de Gabriel en Sevilla.
        """
        l_low = label.lower()

        if is_numeric:
            if any(w in l_low for w in ["salario", "salary", "bruto", "expectativa", "remuneración", "compensation", "sueldo"]):
                return "20000"
            if any(w in l_low for w in ["python", "linux", "sistemas", "it", "software", "desarrollo", "sql", "git"]):
                return "2"
            if any(w in l_low for w in ["año", "year", "experiencia", "experience", "cuántos", "how many", "meses"]):
                return "1"
            return "1"

        if any(w in l_low for w in ["ciudad", "city", "ubicación", "location", "residencia", "dirección"]):
            return "Sevilla, España"
        if any(w in l_low for w in ["incorporación", "notice", "disponibilidad", "cuándo", "start date"]):
            return "Inmediata"
        if any(w in l_low for w in ["salario", "salary", "bruto", "expectativa", "remuneración"]):
            return "18.000 - 22.000 EUR brutos/año (flexible según proyecto)"
        if any(w in l_low for w in ["inglés", "english", "idioma"]):
            return "B2"
        if any(w in l_low for w in ["github", "portfolio", "web", "repositorio"]):
            return "https://github.com/gtrujillovdev-cyber"
        if any(w in l_low for w in ["linkedin"]):
            return "https://www.linkedin.com/in/gabriel-trujillo-vallejo-9b3088196/"
        if any(w in l_low for w in ["teléfono", "phone", "móvil", "mobile"]):
            return "661666806"
        if any(w in l_low for w in ["correo", "email", "e-mail"]):
            return "gtrujillov.dev@gmail.com"

        # Si hay API Key de Gemini, generar respuesta concisa
        if GEMINI_API_KEY:
            try:
                from google import genai
                client = genai.Client(api_key=GEMINI_API_KEY)
                prompt = (
                    f"Responde de forma muy breve (máximo 10 palabras) a esta pregunta de un formulario de empleo IT:\n"
                    f"Pregunta: {label}\n"
                    f"Candidato: Gabriel Trujillo Vallejo, Graduado DAM en Sevilla, 1-2 años de experiencia práctica en Python, Linux, Ciberseguridad, QA Playwright y SwiftUI. Incorporación inmediata. Permiso de trabajo en España (ciudadano UE). Nivel de inglés B2.\n"
                    f"Devuelve SOLO la respuesta directa."
                )
                res = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
                if res.text and res.text.strip():
                    return res.text.strip()[:120]
            except Exception:
                pass

        return "Sí, cuento con disponibilidad inmediata en Sevilla/remoto y formación técnica DAM."

    @classmethod
    def _fill_dialog_fields(cls, page, dialog, job: Dict[str, Any], cv_uploaded: bool) -> bool:
        """
        Rellena los campos visibles del paso actual del modal <dialog> de Solicitud Sencilla:
        - Datos de contacto (email, teléfono)
        - Selección o subida del CV adaptado en PDF
        - Preguntas adicionales (inputs numéricos, texto, selects, radios y checkboxes)
        Devuelve True si en este paso se subió/seleccionó el CV.
        """
        dlg_text = ""
        try:
            dlg_text = dialog.inner_text()
        except Exception:
            pass

        # 1. Paso de Currículum: subir el PDF adaptado o seleccionar el radio button correspondiente
        if not cv_uploaded and ("Currículum" in dlg_text or "Resume" in dlg_text or "Cargar currículum" in dlg_text):
            pdf_path = job.get("cv_pdf_path")
            target_li_name = job.get("cv_linkedin_name", "GTV_CV_ES2026_General.pdf")

            # Intentar subir el PDF adaptado recién generado si existe input[type="file"]
            file_inputs = dialog.locator("input[type='file']")
            if pdf_path and Path(pdf_path).exists() and file_inputs.count() > 0:
                try:
                    file_inputs.first.set_input_files(str(pdf_path))
                    time.sleep(2.0)
                    cv_uploaded = True
                    print(f"    [EasyApply] CV PDF adaptado subido: {Path(pdf_path).name}")
                except Exception as e_up:
                    print(f"    [EasyApply] Aviso subiendo PDF ({e_up}), seleccionando CV pre-cargado...")

            # Seleccionar también el radio button del CV más adaptado si hay radios en el diálogo
            radios = dialog.locator("input[type='radio']")
            if radios.count() > 0:
                matched_radio = False
                for r_idx in range(radios.count()):
                    r_el = radios.nth(r_idx)
                    aria = (r_el.get_attribute("aria-label") or "").strip()
                    if target_li_name.lower() in aria.lower():
                        try:
                            r_el.check(force=True)
                        except Exception:
                            r_el.evaluate("el => el.click()")
                        matched_radio = True
                        cv_uploaded = True
                        print(f"    [EasyApply] CV seleccionado en LinkedIn: {aria}")
                        break
                if not matched_radio and not cv_uploaded:
                    try:
                        radios.first.check(force=True)
                    except Exception:
                        radios.first.evaluate("el => el.click()")
                    cv_uploaded = True

        # 2. Rellenar inputs de texto y numéricos vacíos
        inputs = dialog.locator("input[type='text'], input[type='number'], input[type='tel'], textarea")
        for i in range(inputs.count()):
            inp = inputs.nth(i)
            if not inp.is_visible():
                continue
            val = (inp.input_value() or "").strip()
            if val:
                continue

            input_type = (inp.get_attribute("type") or "text").lower()
            input_mode = (inp.get_attribute("inputmode") or "").lower()
            label_text = inp.evaluate("""(el) => {
                const id = el.id;
                if (id) {
                    const lbl = document.querySelector(`label[for="${CSS.escape(id)}"]`);
                    if (lbl) return lbl.innerText.trim();
                }
                const parentLbl = el.closest('label') || el.parentElement?.querySelector('label');
                return parentLbl ? parentLbl.innerText.trim() : (el.getAttribute('aria-label') || el.placeholder || '');
            }""") or ""

            if "móvil" in label_text.lower() or "teléfono" in label_text.lower() or "phone" in label_text.lower():
                inp.fill("661666806")
            else:
                is_num = input_type == "number" or "numeric" in input_mode or "decimal" in input_mode
                ans = cls._answer_additional_question(label_text, job, is_numeric=is_num)
                inp.fill(ans)
            time.sleep(0.3)

        # 3. Rellenar desplegables <select> que estén sin seleccionar
        selects = dialog.locator("select")
        for i in range(selects.count()):
            sel = selects.nth(i)
            if not sel.is_visible():
                continue
            curr_val = (sel.input_value() or "").strip()
            if curr_val and "urn:li" not in curr_val and curr_val.lower() not in ["seleccionar una opción", "select an option", ""]:
                continue

            chosen_val = sel.evaluate("""(el) => {
                const opts = Array.from(el.options).filter(o => o.value && !/seleccionar|select an option/i.test(o.text));
                if (opts.length === 0) return '';
                const preferred = opts.find(o => /^(sí|si|yes|españa|spain|sevilla|b2|grado|profesional|inmediata)/i.test(o.text.trim()));
                return preferred ? preferred.value : opts[0].value;
            }""")
            if chosen_val:
                try:
                    sel.select_option(chosen_val)
                    time.sleep(0.3)
                except Exception:
                    pass

        # 4. Rellenar grupos de radio buttons (<fieldset>) en pasos de preguntas adicionales
        if "Currículum" not in dlg_text and "Resume" not in dlg_text:
            fieldsets = dialog.locator("fieldset")
            for i in range(fieldsets.count()):
                fs = fieldsets.nth(i)
                if not fs.is_visible():
                    continue
                fs.evaluate("""(fsEl) => {
                    const radios = Array.from(fsEl.querySelectorAll('input[type="radio"]'));
                    if (radios.length === 0 || radios.some(r => r.checked)) return;
                    const legend = (fsEl.querySelector('legend')?.innerText || fsEl.innerText || '').toLowerCase();
                    const wantNo = /patrocinio|visado|visa|sponsorship|discapacidad/i.test(legend);
                    let target = radios.find(r => {
                        const lbl = (fsEl.querySelector(`label[for="${CSS.escape(r.id)}"]`)?.innerText || r.value || '').trim().toLowerCase();
                        return wantNo ? /^(no)\b/.test(lbl) : /^(sí|si|yes)\b/.test(lbl);
                    }) || radios[0];
                    if (target) {
                        target.click();
                        target.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                }""")

        # 5. Marcar checkboxes obligatorios (términos / consentimiento) pero DESMARCAR "Seguir a <Empresa>" si está en revisión
        checkboxes = dialog.locator("input[type='checkbox']")
        for i in range(checkboxes.count()):
            cb = checkboxes.nth(i)
            cb_label = cb.evaluate("""(el) => {
                const id = el.id;
                const lbl = id ? document.querySelector(`label[for="${CSS.escape(id)}"]`) : el.closest('label');
                return lbl ? lbl.innerText.trim() : '';
            }""") or ""
            if "seguir a" in cb_label.lower() or "follow" in cb_label.lower():
                continue
            if not cb.is_checked():
                try:
                    cb.check(force=True)
                except Exception:
                    pass

        return cv_uploaded

    @classmethod
    def apply_to_job(cls, page, job: Dict[str, Any]) -> Dict[str, Any]:
        """
        Navega a la oferta en LinkedIn, abre el modal de Solicitud Sencilla,
        adjunta/selecciona el CV más adaptado al puesto, completa los pasos y envía la candidatura.
        """
        url = job.get("url", "")
        title = job.get("title", "Vacante IT")
        company = job.get("company", "Empresa")
        print(f"\n  [EasyApply] Aplicando a: {title} en {company} ({url})")

        if not url:
            return {**job, "status": "skipped", "reason": "missing_url"}

        try:
            # Asegurar que el PDF oficial reutilizado existe antes de abrir el modal
            if not job.get("cv_pdf_path") or not Path(job["cv_pdf_path"]).exists():
                cls.get_existing_official_cv(job)

            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            time.sleep(3.0)

            body_text = page.evaluate("() => (document.body.innerText || '').substring(0, 1800)")
            if re.search(r"Solicitud enviada|Application submitted", body_text, re.I):
                print(f"  [EasyApply] Ya se había enviado solicitud a {company}.")
                return {**job, "status": "skipped", "reason": "already_applied"}

            easy_btn = page.locator(
                "button[aria-label*='Solicitud sencilla'], button[aria-label*='Easy Apply'], "
                "button:has-text('Solicitud sencilla'), button:has-text('Easy Apply')"
            ).first

            if easy_btn.count() == 0 or not easy_btn.is_visible():
                return {**job, "status": "skipped", "reason": "no_easy_apply_button"}

            easy_btn.click()
            time.sleep(2.2)

            all_dialogs = page.locator("dialog[open], dialog, div[role='dialog']")
            dialog = None
            for d_idx in range(all_dialogs.count()):
                cand = all_dialogs.nth(d_idx)
                try:
                    if cand.is_visible() and cand.locator("button").count() > 0:
                        dialog = cand
                        break
                except Exception:
                    continue

            if dialog is None:
                return {**job, "status": "skipped", "reason": "dialog_not_opened"}

            cv_uploaded = False
            for step in range(1, 11):
                cv_uploaded = cls._fill_dialog_fields(page, dialog, job, cv_uploaded)
                time.sleep(0.8)

                # ¿Estamos en el paso final con botón "Enviar solicitud"?
                submit_btn = dialog.locator(
                    "button[aria-label*='Enviar solicitud'], button:has-text('Enviar solicitud'), "
                    "button[aria-label*='Submit application'], button:has-text('Submit application')"
                ).first
                if submit_btn.count() > 0 and submit_btn.is_visible() and submit_btn.is_enabled():
                    submit_btn.click()
                    time.sleep(3.5)

                    # Captura de pantalla de confirmación
                    job_id_match = re.search(r"/jobs/view/(\d+)", url)
                    job_id = job_id_match.group(1) if job_id_match else str(int(time.time()))
                    shot_path = SCREENSHOTS_DIR / f"easy_apply_{job_id}.png"
                    try:
                        page.screenshot(path=str(shot_path))
                    except Exception:
                        pass

                    cls.record_application(job, status="success")
                    print(f"  [EasyApply] [✓] Solicitud enviada con éxito a {company} ({title}) usando CV [{job.get('cv_label')}]")
                    return {
                        **job,
                        "status": "success",
                        "screenshot_path": str(shot_path)
                    }

                # Buscar botón "Revisar" o "Siguiente"
                next_btn = dialog.locator(
                    "button[aria-label*='Revisar'], button:has-text('Revisar'), "
                    "button[aria-label*='Review'], button:has-text('Review'), "
                    "button[aria-label*='Siguiente'], button:has-text('Siguiente'), "
                    "button[aria-label*='Continue'], button:has-text('Next')"
                ).first

                if next_btn.count() > 0 and next_btn.is_visible() and next_btn.is_enabled():
                    prev_text = ""
                    try:
                        prev_text = dialog.inner_text()[:300]
                    except Exception:
                        pass
                    next_btn.click()
                    time.sleep(1.6)

                    # Si el paso no avanzó por un campo requerido con error, re-intentar rellenar
                    curr_text = ""
                    try:
                        curr_text = dialog.inner_text()[:300]
                    except Exception:
                        pass
                    if curr_text == prev_text:
                        cls._fill_dialog_fields(page, dialog, job, cv_uploaded)
                        time.sleep(0.5)
                        if next_btn.is_visible() and next_btn.is_enabled():
                            next_btn.click()
                            time.sleep(1.5)
                else:
                    break

            # Cerrar modal si no se pudo completar
            close_btn = dialog.locator("button[aria-label='Descartar'], button[aria-label='Dismiss']").first
            if close_btn.count() > 0 and close_btn.is_visible():
                close_btn.click()
                time.sleep(0.8)
                discard_btn = page.locator("button:has-text('Descartar'), button:has-text('Discard')").first
                if discard_btn.count() > 0 and discard_btn.is_visible():
                    discard_btn.click()

            cls.record_application(job, status="skipped", reason="complex_form_steps")
            return {**job, "status": "skipped", "reason": "max_steps_exceeded"}

        except Exception as e:
            print(f"  [EasyApply] Error aplicando a {company}: {e}")
            cls.record_application(job, status="error", reason=str(e))
            return {**job, "status": "error", "reason": str(e)}

    @classmethod
    def execute_applications(cls, jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Ejecuta el envío de Solicitud Sencilla con Playwright para la lista de ofertas aprobadas."""
        results = []
        if not jobs:
            return results

        try:
            from playwright.sync_api import sync_playwright
            from src.browser_helper import get_playwright_browser_context

            with sync_playwright() as p:
                browser, context = get_playwright_browser_context(p)
                page = context.pages[0] if context.pages else context.new_page()

                for job in jobs:
                    if not job.get("enabled", True):
                        continue
                    res = cls.apply_to_job(page, job)
                    results.append(res)
                    time.sleep(random.uniform(3.0, 6.0))

                context.close()
        except Exception as e:
            print(f"[EasyApply] Error en Playwright: {e}")

        return results

    # ------------------------------------------------------------------
    # 4. INTERFAZ TELEGRAM CO-PILOT (VISTA PREVIA DE VACANTES + CV ADAPTADO)
    # ------------------------------------------------------------------
    @classmethod
    def _build_telegram_message_and_keyboard(cls, jobs: List[Dict[str, Any]]) -> Tuple[str, dict]:
        lines = ["🎯 *VACANTES SOLICITUD SENCILLA (ATS MATCHING HR)*\n"]
        toggle_row = []

        for i, job in enumerate(jobs, 1):
            enabled = job.get("enabled", True)
            icon = "✅" if enabled else "⏭️ (Omitida)"
            cv_label = job.get("cv_label", "CV General IT")
            cv_file = Path(job.get("cv_pdf_path", "")).name or job.get("cv_linkedin_name", "GTV_CV_ES2026.pdf")
            ats = job.get("ats_analysis") or {}
            ats_score = ats.get("ats_score", job.get("cv_score", 85))
            tier_badge = ats.get("tier_badge", "🟢 ALTO MATCH")
            matched_kws = ats.get("matched_keywords") or job.get("cv_matched_keywords") or []
            gaps = ats.get("gaps") or []

            lines.append(f"*{i}. {icon} {job.get('title', 'Vacante IT')}*")
            lines.append(f"   🏢 {job.get('company', '')} · 📍 {job.get('location', '')}")
            lines.append(f"   📊 *Score ATS:* `{ats_score}%` ({tier_badge})")
            lines.append(f"   📄 *CV Oficial:* `{cv_file}` ({cv_label})")
            if matched_kws:
                lines.append(f"   🎯 *Match:* `{', '.join(matched_kws[:5])}`")
            if gaps:
                lines.append(f"   ⚠️ *Gaps:* `{', '.join(gaps[:3])}`")
            if job.get("url"):
                lines.append(f"   🔗 {job['url']}")
            lines.append("")

            toggle_row.append({
                "text": f"{'✅' if enabled else '❌'} #{i}",
                "callback_data": f"apply:toggle_{i - 1}"
            })

        lines.append("Pulsa `#1..#5` para activar/desactivar ofertas o pulsa *Aplicar con CV adaptado*:")
        keyboard_rows = []
        if toggle_row:
            keyboard_rows.append(toggle_row)
        keyboard_rows.append([
            {"text": "🚀 Aplicar con CV adaptado", "callback_data": "apply:approve"},
            {"text": "❌ Cancelar", "callback_data": "apply:reject"}
        ])
        return "\n".join(lines), {"inline_keyboard": keyboard_rows}

    @classmethod
    def send_proposals_to_telegram(cls, jobs: List[Dict[str, Any]]) -> Optional[str]:
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID or not jobs:
            return None

        try:
            PENDING_EASY_APPLY_FILE.write_text(
                json.dumps(jobs, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        except Exception:
            pass

        import requests
        text, keyboard = cls._build_telegram_message_and_keyboard(jobs)

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
            if res.status_code != 200:
                res = requests.post(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": TELEGRAM_CHAT_ID,
                        "text": text[:4000],
                        "disable_web_page_preview": True,
                        "reply_markup": keyboard
                    },
                    timeout=15
                )
            return "apply" if res.status_code == 200 else None
        except Exception as e:
            print(f"[EasyApply] Error enviando propuesta a Telegram: {e}")
            return None

    @classmethod
    def report_results_to_telegram(cls, results: List[Dict[str, Any]], chat_id: Optional[Any] = None) -> None:
        target_chat = chat_id or TELEGRAM_CHAT_ID
        if not TELEGRAM_BOT_TOKEN or not target_chat:
            return

        import requests
        success = [r for r in results if r.get("status") == "success"]
        skipped = [r for r in results if r.get("status") == "skipped"]
        errors = [r for r in results if r.get("status") == "error"]

        lines = ["📋 *RESULTADO DE CANDIDATURAS (SOLICITUD SENCILLA)*\n"]
        lines.append(f"✅ Enviadas con éxito: {len(success)}")
        lines.append(f"⏭️ Omitidas: {len(skipped)}")
        lines.append(f"❌ Errores: {len(errors)}\n")

        for r in success:
            lines.append(f"🎯 *{r.get('title')}* — {r.get('company')}")
            lines.append(f"   📄 CV enviado: `{r.get('cv_label', 'CV Adaptado')}`")
            if r.get("url"):
                lines.append(f"   🔗 {r['url']}")

        if skipped:
            lines.append("\nOmitidas:")
            for r in skipped[:4]:
                lines.append(f"  • {r.get('company')}: {r.get('reason', '?')}")

        text = "\n".join(lines)
        try:
            res = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": target_chat, "text": text[:4000], "parse_mode": "Markdown", "disable_web_page_preview": True},
                timeout=15
            )
            if res.status_code != 200:
                requests.post(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                    json={"chat_id": target_chat, "text": text[:4000], "disable_web_page_preview": True},
                    timeout=15
                )
        except Exception:
            pass

    @classmethod
    def listen_and_execute(cls, jobs: List[Dict[str, Any]], timeout: int = 900) -> bool:
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID or not jobs:
            return False

        import requests
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

                    if not data.startswith("apply:"):
                        continue

                    decision = data.split(":")[1]
                    if decision.startswith("toggle_"):
                        idx = int(decision.split("_")[1])
                        if 0 <= idx < len(jobs):
                            jobs[idx]["enabled"] = not jobs[idx].get("enabled", True)
                            new_text, new_kb = cls._build_telegram_message_and_keyboard(jobs)
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
                                json={"callback_query_id": cb_id, "text": f"Oferta #{idx + 1} actualizada"}
                            )
                        continue

                    requests.post(
                        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageReplyMarkup",
                        json={"chat_id": chat_id, "message_id": message_id, "reply_markup": {"inline_keyboard": []}}
                    )

                    if decision == "approve":
                        selected = [j for j in jobs if j.get("enabled", True)]
                        requests.post(
                            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery",
                            json={"callback_query_id": cb_id, "text": f"Aplicando a {len(selected)} vacantes..."}
                        )
                        results = cls.execute_applications(selected)
                        cls.report_results_to_telegram(results, chat_id)
                        return True
                    elif decision == "reject":
                        requests.post(
                            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery",
                            json={"callback_query_id": cb_id, "text": "Candidaturas canceladas."}
                        )
                        requests.post(
                            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                            json={"chat_id": chat_id, "text": "❌ Envío de candidaturas Easy Apply cancelado."}
                        )
                        return False
            except Exception:
                time.sleep(2)

        return False
