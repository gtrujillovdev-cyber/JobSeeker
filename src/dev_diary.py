import json
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

from config import BASE_DIR, DATA_DIR, GEMINI_API_KEY, CANDIDATE_PROFILE
from src.project_capturer import ProjectCapturer
from src.telegram_reviewer import TelegramReviewer

DEV_DIARY_HISTORY_FILE = DATA_DIR / "dev_diary_history.json"
PROJECTS_ROOT = BASE_DIR.parent  # /Users/.../Developer/Projects

# Catálogo de proyectos reales de Gabriel con archivo real para la captura de código
CURATED_DEVLOG_PROJECTS: List[Dict[str, Any]] = [
    {
        "dir_name": "Tv-streamer",
        "target_file": "stream_manager.py",
        "anchor_keyword": "def ",
        "live_capture": {
            "mode": "web_command",
            "cwd": "",
            "command": ["python3", "-m", "streamlit", "run", "app.py", "--server.port", "18505", "--server.headless", "true"],
            "port": 18505,
            "url_path": "/",
            "wait_seconds": 4.0,
            "click_selectors": [
                "summary:has-text('Asistente de Configuración Rápida')",
                "summary:has-text('Transmitir Archivo Directo')"
            ]
        },
        "display_name": "Tv-streamer — Servidor Multimedia Local y Google Cast en Red",
        "domain": "Redes Locales, Python y Docker",
        "tech_stack": ["Python", "Networking", "Docker", "macOS"],
        "default_headline": "Diario de Desarrollo #1 — Creando un servidor de streaming local en Python para eliminar el cable HDMI",
        "default_context": (
            "Quería enviar vídeo desde mi Mac a la TV por la red local sin depender de cables HDMI ni configuraciones pesadas, "
            "así que diseñé `Tv-streamer` en Python."
        ),
        "default_learning": (
            "Autodescubrimiento Google Cast en LAN y chequeo previo de socket antes de iniciar el streaming."
        ),
        "fallback_snippet": (
            "# Gestión de reproducción local y descubrimiento Cast\n"
            "def start_cast_session(device_ip: str, media_url: str):\n"
            "    cast = pychromecast.Chromecast(device_ip)\n"
            "    cast.wait()\n"
            "    mc = cast.media_controller\n"
            "    mc.play_media(media_url, 'video/mp4')\n"
            "    mc.block_until_active()"
        ),
    },
    {
        "dir_name": "InteractiveCV",
        "target_file": "src/main.js",
        "anchor_keyword": "",
        "live_capture": {
            "mode": "static_server",
            "serve_dir": "dist",
            "port": 18912,
            "extra_views": [
                {
                    "scroll_y": 520,
                    "wait_seconds": 1.5
                }
            ]
        },
        "display_name": "InteractiveCV — CV Técnico Dinámico con Vite, Tailwind v4 y CI/CD",
        "domain": "Frontend con Vite, Tailwind CSS y GitHub Actions",
        "tech_stack": ["Vite", "TailwindCSS", "GitHubActions", "QA"],
        "default_headline": "Diario de Desarrollo #2 — Mi CV web interactivo con perfiles dinámicos y validación en GitHub Actions",
        "default_context": (
            "Como mi formación en DAM y mis proyectos abarcan Sistemas Linux/Ciberseguridad, Desarrollo en Python y QA, "
            "construí `InteractiveCV` para que quien visite mi CV pueda filtrar mi perfil según el rol técnico que busque."
        ),
        "default_learning": (
            "Migración a Vite + Tailwind v4 con pipeline en GitHub Actions que valida cada build automáticamente."
        ),
        "fallback_snippet": (
            "// Cambio dinámico de perfil técnico en InteractiveCV\n"
            "export function selectProfile(profileKey) {\n"
            "  const active = PROFILES[profileKey] || PROFILES.default;\n"
            "  renderSkills(active.skills);\n"
            "  renderProjects(active.projects);\n"
            "}"
        ),
    },
    {
        "dir_name": "JobSeekerGA",
        "target_file": "src/linkedin_publisher.py",
        "anchor_keyword": "expect_file_chooser",
        "live_capture": {
            "mode": "terminal_command",
            "cwd": "",
            "command": ["python3", "main.py", "--scan-summary"],
            "terminal_title": "JobSeekerGA — Radar de Empleo & Empresas Target en Sevilla"
        },
        "display_name": "JobSeekerGA — Automatización Web & Control por Telegram",
        "domain": "Python, Playwright y Gestión de Sesiones",
        "tech_stack": ["Python", "Playwright", "Linux", "TelegramAPI"],
        "default_headline": "Diario de Desarrollo #3 — Por qué fallaban las sesiones persistentes en Playwright y cómo lo solucioné",
        "default_context": (
            "Estoy desarrollando `JobSeekerGA` en Python para automatizar mi flujo de búsqueda de empleo IT en Sevilla y controlar mis publicaciones "
            "desde Telegram con confirmación previa, sin dejar demonios consumiendo memoria en mi Mac."
        ),
        "default_learning": (
            "Persistencia nativa del perfil en Chromium y subida de archivos mediante expect_file_chooser()."
        ),
        "fallback_snippet": (
            "with page.expect_file_chooser(timeout=6000) as fc_info:\n"
            "    try:\n"
            "        btn.evaluate('el => el.click()')\n"
            "    except Exception:\n"
            "        btn.click(force=True)\n"
            "file_chooser = fc_info.value\n"
            "file_chooser.set_files(str(image_path))"
        ),
    },
    {
        "dir_name": "LawLab",
        "target_file": "backend-api/main.py",
        "anchor_keyword": "def ",
        "live_capture": {
            "mode": "web_command",
            "cwd": "backend-api",
            "command": ["python3", "-m", "uvicorn", "main:app", "--port", "18008"],
            "port": 18008,
            "url_path": "/docs",
            "wait_seconds": 3.0,
            "click_selectors": [
                "div.opblock-summary"
            ]
        },
        "display_name": "LawLab — Backend en FastAPI + Cliente Nativo macOS en SwiftUI",
        "domain": "Arquitectura Cliente-Servidor con FastAPI, Docker y SwiftUI",
        "tech_stack": ["FastAPI", "Python", "SwiftUI", "Docker"],
        "default_headline": "Diario de Desarrollo #4 — Conectando un backend en FastAPI (Docker) con una app nativa en SwiftUI",
        "default_context": (
            "En `LawLab` diseñé una arquitectura dividida en dos capas: una API en Python con FastAPI desplegada en Docker "
            "y una aplicación nativa de escritorio para macOS escrita en SwiftUI."
        ),
        "default_learning": (
            "Gestión reactiva con ObservableObject en Swift conectada a servicios FastAPI en Docker."
        ),
        "fallback_snippet": (
            "@app.post('/api/v1/analyze')\n"
            "async def analyze_document(payload: DocumentRequest):\n"
            "    result = await pipeline.run_extraction(payload.text)\n"
            "    return {'status': 'completed', 'data': result}"
        ),
    },
    {
        "dir_name": "GeminiJobBot",
        "target_file": "src/orchestrator.py",
        "anchor_keyword": "def ",
        "live_capture": {
            "mode": "web_command",
            "cwd": "",
            "command": ["python3", "-m", "uvicorn", "src.app:app", "--port", "18099"],
            "port": 18099,
            "url_path": "/",
            "wait_seconds": 2.5,
            "extra_views": [
                {
                    "url_path": "/docs",
                    "wait_seconds": 2.0,
                    "click_selectors": ["div.opblock-summary"]
                }
            ]
        },
        "display_name": "GeminiJobBot — Descubrimiento de Ofertas y Control de Rate-Limit",
        "domain": "Python, Automatización y Resiliencia en Red",
        "tech_stack": ["Python", "SQLite", "Automation", "Backend"],
        "default_headline": "Diario de Desarrollo #5 — Evitando bloqueos en portales de empleo mediante búsqueda indexada y backoff",
        "default_context": (
            "Al construir `GeminiJobBot` comprobé que lanzar peticiones directas seguidas contra portales de empleo termina rápido en bloqueos por rate-limit."
        ),
        "default_learning": (
            "Descubrimiento por búsquedas indexadas en SQLite con tiempos de espera progresivos anti-bloqueo."
        ),
        "fallback_snippet": (
            "def run_discovery_cycle(queries: list[str]):\n"
            "    for q in queries:\n"
            "        results = search_proxy_index(q)\n"
            "        save_discovered_jobs(results)\n"
            "        time.sleep(random.uniform(3.5, 7.0))"
        ),
    },
    {
        "dir_name": "PolyPrec",
        "target_file": "poly-football-arb/src/ws_client.py",
        "anchor_keyword": "def ",
        "live_capture": {
            "mode": "terminal_command",
            "cwd": "",
            "command": ["git", "--no-pager", "log", "-n", "5", "--stat", "--oneline"],
            "terminal_title": "PolyPrec — Arquitectura WebSockets & Historial de Commits"
        },
        "display_name": "PolyPrec — Monitor en Tiempo Real con WebSockets Asíncronos",
        "domain": "Programación Asíncrona en Python, WebSockets y Testing",
        "tech_stack": ["Python", "WebSockets", "AsyncIO", "Pytest"],
        "default_headline": "Diario de Desarrollo #6 — Gestionando conexiones WebSocket en tiempo real con reconexión automática en Python",
        "default_context": (
            "En `PolyPrec` necesitaba escuchar múltiples flujos de datos en vivo al mismo tiempo sin que un corte de red puntual tumbara el proceso."
        ),
        "default_learning": (
            "Cliente asíncrono con reconexión automática en websockets, alertas en Telegram y tests en Pytest."
        ),
        "fallback_snippet": (
            "async def connect_and_listen(self):\n"
            "    async for ws in websockets.connect(self.uri, ping_interval=20):\n"
            "        try:\n"
            "            async for message in ws:\n"
            "                await self.handle_event(json.loads(message))\n"
            "        except websockets.ConnectionClosed:\n"
            "            continue"
        ),
    },
    {
        "dir_name": "GaBookAutoDownloader ",
        "target_file": "src/gabook/services/book_client.py",
        "anchor_keyword": "def ",
        "live_capture": {
            "mode": "terminal_command",
            "cwd": "",
            "command": ["git", "--no-pager", "log", "-n", "5", "--stat", "--oneline"],
            "terminal_title": "GaBookAutoDownloader — Historial de Commits & Arquitectura Multi-Mirror"
        },
        "display_name": "GaBookAutoDownloader — Motor de Búsqueda con Ranking y Failover",
        "domain": "Python, Tolerancia a Fallos y Arquitectura de Servicios",
        "tech_stack": ["Python", "Linux", "Automation", "Backend"],
        "default_headline": "Diario de Desarrollo #7 — Tolerancia a fallos multi-servidor y algoritmo de relevancia en Python",
        "default_context": (
            "En `GaBookAutoDownloader` busqué resolver un problema clásico: cuando dependes de servidores externos, tarde o temprano alguno cae o va lento."
        ),
        "default_learning": (
            "Ranking de resultados por relevancia y failover automático entre servidores espejo."
        ),
        "fallback_snippet": (
            "async def download_with_failover(mirrors: list[str], dest: Path) -> bool:\n"
            "    for mirror_url in mirrors:\n"
            "        try:\n"
            "            return await fetch_stream(mirror_url, dest)\n"
            "        except NetworkError:\n"
            "            continue\n"
            "    return False"
        ),
    },
    {
        "dir_name": "BtcBriefing_iOS_ShortCut",
        "target_file": "main.py",
        "anchor_keyword": "def ",
        "live_capture": {
            "mode": "terminal_command",
            "cwd": "",
            "command": ["git", "--no-pager", "log", "-n", "5", "--stat", "--oneline"],
            "terminal_title": "BtcBriefing_iOS_ShortCut — Pipeline CI & Atajos de iOS"
        },
        "display_name": "BtcBriefing — Automatización en Python integrada con Atajos de iOS",
        "domain": "Python, APIs REST y CI con GitHub Actions",
        "tech_stack": ["Python", "APIs", "GitHubActions", "Automation"],
        "default_headline": "Diario de Desarrollo #8 — Conectando scripts de Python con Atajos de iOS y control de calidad en CI",
        "default_context": (
            "Construí `BtcBriefing_iOS_ShortCut` para consultar varias APIs desde un script en Python y recibir el resumen directamente "
            "en mi iPhone al ejecutar un Atajo de iOS."
        ),
        "default_learning": (
            "Integración directa con Atajos de iOS y validación automática de linting en GitHub Actions."
        ),
        "fallback_snippet": (
            "def build_daily_briefing() -> dict:\n"
            "    metrics = fetch_market_snapshot()\n"
            "    sentiment = fetch_fear_and_greed_index()\n"
            "    return {'summary': format_for_ios(metrics, sentiment)}"
        ),
    },
]


class DevDiaryGenerator:
    """
    Extrae código real y commits de los repositorios de Gabriel en /Developer/Projects,
    genera una captura de código limpia del archivo real y envía el borrador a Telegram
    para que Gabriel lo revise y apruebe con 1 clic antes de publicar en LinkedIn.
    """

    @staticmethod
    def _load_history() -> List[Dict[str, Any]]:
        if not DEV_DIARY_HISTORY_FILE.exists():
            return []
        try:
            return json.loads(DEV_DIARY_HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []

    @staticmethod
    def _save_history(records: List[Dict[str, Any]]) -> None:
        DEV_DIARY_HISTORY_FILE.write_text(
            json.dumps(records, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    @classmethod
    def _inspect_repo(cls, project_meta: Dict[str, Any]) -> Dict[str, Any]:
        """
        Inspecciona en tiempo real el repositorio del proyecto:
        - Lee los últimos commits reales (`git log`).
        - Extrae los archivos modificados y el diff real del último commit (`git show`).
        - Enumera todos los archivos y funciones principales del proyecto para que cada post
          pueda hablar de un módulo o función distinta y generar su captura dinámica a medida.
        """
        repo_path = PROJECTS_ROOT / project_meta["dir_name"]
        commits = []
        recent_files = []
        last_commit_diff = ""
        repo_functions_inventory = []
        repo_url = ""
        snippet = project_meta["fallback_snippet"]
        source_file_label = project_meta.get("target_file", "main.py")

        if repo_path.exists():
            if (repo_path / ".git").exists():
                try:
                    rem = subprocess.check_output(
                        ["git", "-C", str(repo_path), "remote", "get-url", "origin"],
                        stderr=subprocess.DEVNULL,
                        timeout=4
                    ).decode("utf-8", errors="replace").strip()
                    if rem:
                        if rem.endswith(".git"):
                            rem = rem[:-4]
                        repo_url = rem
                except Exception:
                    pass

                try:
                    out = subprocess.check_output(
                        ["git", "-C", str(repo_path), "log", "-n", "5", "--oneline"],
                        stderr=subprocess.DEVNULL,
                        timeout=4
                    ).decode("utf-8", errors="replace").strip()
                    if out:
                        commits = [line.strip() for line in out.splitlines() if line.strip()]
                except Exception:
                    pass

                try:
                    files_out = subprocess.check_output(
                        ["git", "-C", str(repo_path), "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"],
                        stderr=subprocess.DEVNULL,
                        timeout=4
                    ).decode("utf-8", errors="replace").strip()
                    if files_out:
                        recent_files = [f.strip() for f in files_out.splitlines() if f.strip()][:6]
                except Exception:
                    pass

                try:
                    diff_out = subprocess.check_output(
                        ["git", "-C", str(repo_path), "show", "--stat", "--oneline", "HEAD"],
                        stderr=subprocess.DEVNULL,
                        timeout=4
                    ).decode("utf-8", errors="replace").strip()
                    if diff_out:
                        last_commit_diff = "\n".join(diff_out.splitlines()[:12])
                except Exception:
                    pass

            # Escanear archivos y sus funciones reales en el repositorio
            code_files = [
                f for f in repo_path.rglob("*")
                if f.is_file()
                and f.suffix in (".py", ".swift", ".js", ".ts")
                and "node_modules" not in f.parts
                and ".venv" not in f.parts
                and "venv" not in f.parts
                and "__pycache__" not in f.parts
                and "dist" not in f.parts
            ]
            for cf in code_files[:15]:
                try:
                    rel_cf = str(cf.relative_to(repo_path))
                    lines = cf.read_text(encoding="utf-8", errors="ignore").splitlines()
                    funcs = [
                        l.strip().split("(")[0].replace("def ", "").replace("async ", "").replace("class ", "")
                        for l in lines
                        if l.strip().startswith(("def ", "async def ", "class ", "export function "))
                    ]
                    if funcs:
                        repo_functions_inventory.append(f"{rel_cf}: {', '.join(funcs[:6])}")
                except Exception:
                    continue

        return {
            **project_meta,
            "commits": commits,
            "recent_files": recent_files,
            "last_commit_diff": last_commit_diff,
            "repo_inventory": repo_functions_inventory,
            "repo_url": repo_url,
            "code_snippet": snippet,
            "source_file": source_file_label
        }

    @classmethod
    def pick_next_diary_entry(cls, project_filter: Optional[str] = None) -> Dict[str, Any]:
        """
        Selecciona el siguiente proyecto en rotación contando SOLO las entradas ya publicadas/aprobadas.
        Así, hasta que Gabriel no acepte la Entrada #1, sigue siendo la Entrada #1.
        """
        history = cls._load_history()
        published_history = [h for h in history if h.get("status") == "published"]
        entry_number = len(published_history) + 1

        if project_filter:
            for proj in CURATED_DEVLOG_PROJECTS:
                if project_filter.lower() in proj["dir_name"].lower():
                    inspected = cls._inspect_repo(proj)
                    inspected["entry_number"] = entry_number
                    return inspected

        published_dirs = [h.get("dir_name") for h in published_history[-len(CURATED_DEVLOG_PROJECTS):]]

        chosen_meta = None
        for proj in CURATED_DEVLOG_PROJECTS:
            if proj["dir_name"] not in published_dirs:
                chosen_meta = proj
                break

        if not chosen_meta:
            idx = len(published_history) % len(CURATED_DEVLOG_PROJECTS)
            chosen_meta = CURATED_DEVLOG_PROJECTS[idx]

        inspected = cls._inspect_repo(chosen_meta)
        inspected["entry_number"] = entry_number
        return inspected

    @staticmethod
    def _format_clean_post(text: str, hashtags_line: str = "") -> str:
        """
        Regla permanente de maquetación para LinkedIn y Telegram (Directriz Anti-Apelotonamiento):
        1. Elimina cualquier emoji al principio de las líneas (mantiene seriedad técnica; máximo 1-2 al final de frase si existen).
        2. Agrupa todas las tecnologías y todos los hashtags en UNA SOLA LÍNEA continua (sin saltos entre tecnologías).
        3. DIRECTRIZ ANTI-APELOTONAMIENTO EN MÓVIL:
           - Prohibido pegar viñetas en líneas consecutivas: fuerza SIEMPRE una línea en blanco ('\\n\\n') entre cada viñeta ('• ').
           - Prohibido texto denso dentro de una viñeta: cada viñeta debe ser de 1 sola idea corta (máx. ~115 caracteres / 2 líneas en móvil).
             Si una viñeta supera los 120 caracteres por encadenar enumeraciones, se sintetiza automáticamente en su cláusula principal.
           - Viñetas a ras de margen ('• ') sin espacios previos que descuadren el sangrado en la app móvil de LinkedIn.
        """
        import re
        text = text.replace("`", "")
        raw_lines = [line.strip() for line in text.strip().splitlines()]

        # Regex para limpiar emojis o símbolos decorativos al inicio de cualquier línea
        leading_emoji_re = re.compile(r"^[\U00010000-\U0010ffff\u2600-\u27bf\ufe0f\u200d]+\s*")

        body_lines = []
        collected_hashtags = []

        def _ensure_blank_line():
            if body_lines and body_lines[-1] != "":
                body_lines.append("")

        def _condense_bullet(bullet_text: str, max_len: int = 120) -> str:
            bullet_text = " ".join(bullet_text.split()).strip()
            if len(bullet_text) <= max_len:
                return bullet_text
            # Cortar en el primer separador natural (. / ; / ,) a partir del carácter 65
            window = bullet_text[:max_len]
            for sep in [". ", "; ", ", "]:
                pos = window.find(sep, 60)
                if pos != -1:
                    trimmed = window[:pos].rstrip(".,;:") + "."
                    return trimmed
            # Si no hay puntuación intermedia, cortar por palabra limpia
            cut = window.rsplit(" ", 1)[0].rstrip(".,;:") + "."
            return cut

        for line in raw_lines:
            if not line:
                _ensure_blank_line()
                continue

            # Si la línea es solo de hashtags, recogerlos todos para unirlos en 1 sola línea al final
            tokens = line.split()
            if tokens and all(t.startswith("#") for t in tokens):
                for t in tokens:
                    if t not in collected_hashtags:
                        collected_hashtags.append(t)
                continue

            # Quitar cualquier emoji al principio de la línea
            line = leading_emoji_re.sub("", line).strip()

            # Normalizar viñetas con separación obligatoria de línea en blanco y concisión anti-apelotonamiento
            if line.startswith(("• ", "* ", "- ")):
                clean_bullet = leading_emoji_re.sub("", line[2:].strip()).strip()
                if clean_bullet.lower().startswith(("stack", "tecnologías", "tecnologias")):
                    clean_bullet = " ".join(clean_bullet.split())
                else:
                    clean_bullet = _condense_bullet(clean_bullet, max_len=120)
                _ensure_blank_line()
                body_lines.append(f"• {clean_bullet}")
                _ensure_blank_line()
            elif line.lower().startswith(("stack:", "tecnologías:", "tecnologias:", "repositorio:")):
                _ensure_blank_line()
                body_lines.append(" ".join(line.split()))
            else:
                body_lines.append(line)

        while body_lines and body_lines[-1] == "":
            body_lines.pop()

        final_hashtags = " ".join(collected_hashtags) if collected_hashtags else hashtags_line.strip()
        if final_hashtags:
            final_hashtags = " ".join(final_hashtags.splitlines()).strip()
            _ensure_blank_line()
            body_lines.append(final_hashtags)

        return "\n".join(body_lines).strip()

    @classmethod
    def generate_diary_copy(cls, entry: Dict[str, Any]) -> str:
        """
        Genera el texto del post centrado al 100% en ingeniería, el proyecto y el aprendizaje técnico,
        con maquetación limpia por bloques y viñetas aireadas (cero bloques apelotonados).
        """
        entry_num = entry["entry_number"]
        display_name = entry["display_name"]
        commits_str = " | ".join(entry.get("commits", [])[:3]) or "Refactorización y pruebas locales"
        stack_str = ", ".join(entry["tech_stack"])
        repo_url = entry.get("repo_url", "").strip()
        repo_line = f"Repositorio: {repo_url}\n\n" if repo_url else ""
        hashtags = " ".join([f"#{t.replace(' ', '')}" for t in entry["tech_stack"][:4]] + ["#DesarrolloDeSoftware", "#SevillaTech", "#DAM"])

        if GEMINI_API_KEY:
            try:
                from google import genai
                client = genai.Client(api_key=GEMINI_API_KEY)

                prompt = f"""
Eres {CANDIDATE_PROFILE['name']}, desarrollador de software en Sevilla (DAM, Python, Sistemas Linux y Ciberseguridad).
Redacta la entrada #{entry_num} de tu "Diario de Desarrollo" en LinkedIn sobre tu proyecto `{entry['dir_name'].strip()}`.

REGLAS DE MAQUETACIÓN Y FORMATO VISUAL (OBLIGATORIAS Y PERMANENTES):
1. CERO EMOJIS AL PRINCIPIO DE LAS FRASES/LÍNEAS: Nunca empieces ninguna línea ni título con emojis.
2. TECNOLOGÍAS EN UNA SOLA LÍNEA: Tanto la línea de `Stack:` como la línea final de `#Hashtags` deben ir en UNA SOLA LÍNEA continua separada por puntos o espacios (`Python · Networking · Docker · macOS`).
3. PROHIBIDO TEXTO APELOTONADO (REGLA CRÍTICA DE LECTURA EN MÓVIL):
   - Deja SIEMPRE una línea en blanco entre cada viñeta (`• `) y la siguiente. Jamás pegues dos o tres viñetas en líneas consecutivas sin espacio en blanco entre ellas.
   - Cada viñeta (`• `) debe tener MÁXIMO 15 palabras (máximo 110 caracteres, 1 sola idea directa). Prohibido meter enumeraciones largas o varias cláusulas en una misma viñeta.
   - Ningún párrafo del post puede superar las 2 líneas en móvil.
4. ESTRUCTURA VISUAL EXACTA (con línea en blanco entre cada viñeta):

Diario de Desarrollo #{entry_num} — [Título corto y directo]

[Párrafo corto de 1-2 frases explicando qué problema real resuelve {entry['dir_name'].strip()}.]

Qué he implementado y qué se ve en las capturas:

• [Punto 1 muy breve (máx 15 palabras) sobre la interfaz en vivo]

• [Punto 2 muy breve (máx 15 palabras) citando {entry['source_file']} y la función clave]

• [Punto 3 muy breve (máx 15 palabras) sobre despliegue o arquitectura]

{f"Repositorio: {repo_url}" if repo_url else ""}

Stack: {" · ".join(entry["tech_stack"])}

{hashtags}

REGLAS DE CONTENIDO:
- PROHIBIDO mencionar temas militares / La Legión.
- PROHIBIDO poner a la IA como autora del código. Habla tú en primera persona con naturalidad y criterio propio.
- No uses comillas invertidas (`) alrededor de los nombres.
- Extensión total: 450 - 700 caracteres (aireado, directo y fácil de escanear en móvil).

DATOS DEL PROYECTO:
- Proyecto: {display_name}
- Repositorio: {repo_url or "N/A"}
- Inventario real de archivos y funciones del repo: {" | ".join(entry.get("repo_inventory", [])[:6]) or entry['source_file']}
- Commits recientes: {commits_str}
- Contexto: {entry['default_context']}
- Detalles técnicos: {entry['default_learning']}
- Stack: {stack_str}
- IMPORTANTE: Menciona por su nombre exacto al menos 1 archivo y 1 función real del inventario anterior para que el capturador dinámico extraiga automáticamente ese bloque exacto de código para la imagen del post.

Devuelve SOLO el texto final respetando exactamente esta estructura con línea en blanco entre viñetas, sin comillas.
"""

                for model_name in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]:
                    try:
                        res = client.models.generate_content(model=model_name, contents=prompt)
                        if res.text and len(res.text.strip()) > 150:
                            cleaned_res = cls._format_clean_post(res.text, hashtags_line=hashtags)
                            if repo_url and repo_url not in cleaned_res:
                                cleaned_res = cleaned_res.replace("Stack:", f"Repositorio: {repo_url}\n\nStack:", 1)
                            return cleaned_res
                    except Exception:
                        continue
            except Exception as e:
                print(f"[DevDiary] Aviso al llamar a Gemini: {e}. Usando plantilla estructurada.")

        stack_inline = " · ".join(entry["tech_stack"])
        fallback = (
            f"Diario de Desarrollo #{entry_num} — {entry['default_headline'].split('—')[-1].strip()}\n\n"
            f"{entry['default_context']}\n\n"
            f"Qué he implementado y qué se ve en las capturas:\n\n"
            f"• Interfaz en vivo: panel de control y estado operativo del servicio.\n\n"
            f"• Núcleo en {entry['source_file']}: {entry['default_learning']}\n\n"
            f"• Despliegue directo en red local sin configuraciones manuales.\n\n"
            f"{repo_line}"
            f"Stack: {stack_inline}\n\n"
            f"{hashtags}"
        )
        return cls._format_clean_post(fallback, hashtags_line=hashtags)

    @classmethod
    def generate_first_comment(cls, entry: Dict[str, Any]) -> str:
        """
        Genera el texto del PRIMER COMENTARIO que se publica automáticamente justo después del post:
        incluye la URL real del repositorio de GitHub (si existe) y una pregunta abierta para abrir debate.
        """
        repo_url = entry.get("repo_url", "").strip()
        main_tech = entry["tech_stack"][0] if entry.get("tech_stack") else "Python"
        proj_name = entry["dir_name"].strip()

        if repo_url:
            return (
                f"Dejo por aquí el repositorio de {proj_name} con el código completo:\n"
                f"{repo_url}\n\n"
                f"¿Cómo soléis enfocar vosotros este tipo de implementaciones trabajando con {main_tech}?"
            )
        return (
            f"¿Cómo soléis enfocar vosotros este tipo de implementaciones trabajando con {main_tech} en vuestros proyectos?"
        )

    @classmethod
    def _extract_dynamic_code_from_post(cls, repo_path: Path, post_text: str, entry: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analiza el contenido real del post generado (y los commits/diffs recientes del repo)
        para extraer DINÁMICAMENTE el archivo, número de línea y bloque de código o git diff
        exacto del que está hablando la publicación de hoy.
        """
        import re
        source_file = entry.get("source_file", "main.py")
        snippet = entry.get("code_snippet", "")
        start_line = 1
        git_commit = entry["commits"][0] if entry.get("commits") else ""

        if not repo_path.exists():
            return {"source_file": source_file, "snippet": snippet, "start_line": 1, "git_commit": git_commit}

        # 1. Recopilar todos los archivos de código reales del proyecto
        all_files = [
            f for f in repo_path.rglob("*")
            if f.is_file()
            and f.suffix in (".py", ".swift", ".js", ".ts", ".tsx", ".sh", ".yml", ".yaml")
            and "node_modules" not in f.parts
            and ".venv" not in f.parts
            and "venv" not in f.parts
            and "__pycache__" not in f.parts
            and "dist" not in f.parts
        ]

        # 2. Detectar si el post menciona algún archivo concreto (ej. stream_manager.py, ws_client.py)
        matched_file = None
        for f in all_files:
            rel = str(f.relative_to(repo_path))
            if f.name in post_text or rel in post_text:
                matched_file = f
                break

        # 3. Extraer identificadores técnicos (funciones, clases, métodos, librerías) mencionados en el post
        words_in_post = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]{3,}\b", post_text)
        stop_words = {
            "Diario", "Desarrollo", "Para", "Como", "Esta", "Este", "Stack", "Python",
            "Docker", "Linux", "macOS", "SevillaTech", "DesarrolloDeSoftware", "implementado",
            "versión", "proyecto", "proyectos", "código", "sistema", "cuando", "donde",
            "antes", "después", "través", "permite", "usando", "arquitectura", "configuración"
        }
        candidate_symbols = [w for w in words_in_post if w not in stop_words]

        # 4. Buscar en los archivos del repo la función o bloque que más coincida con los símbolos del post
        best_score = -1
        best_block = None
        best_file = matched_file
        best_start_line = 1

        search_pool = [matched_file] if matched_file else all_files[:25]
        for f in search_pool:
            if not f or not f.exists():
                continue
            try:
                lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
                for idx, line in enumerate(lines):
                    s = line.strip()
                    if s.startswith(("def ", "async def ", "class ", "final class ", "func ", "export function ", "@app.")):
                        window = "\n".join(lines[idx:idx + 16])
                        score = sum(3 for sym in candidate_symbols if sym in s) + sum(1 for sym in candidate_symbols if sym in window)
                        if matched_file and f == matched_file:
                            score += 2
                        if score > best_score and len(window.strip()) > 40:
                            best_score = score
                            best_block = window
                            best_file = f
                            best_start_line = idx + 1
            except Exception:
                continue

        # 5. Si el post habla específicamente de un commit/diff y existe diff reciente corto, usarlo;
        # de lo contrario, priorizar el bloque de la función real mencionada en el post
        if best_block and best_file:
            return {
                "source_file": str(best_file.relative_to(repo_path)),
                "snippet": best_block,
                "start_line": best_start_line,
                "git_commit": git_commit
            }

        return {
            "source_file": source_file,
            "snippet": snippet,
            "start_line": start_line,
            "git_commit": git_commit
        }

    @classmethod
    def prepare_daily_diary_draft(cls, wait_approval: bool = True, project_filter: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        1. Inspecciona el repositorio y redacta PRIMERO el contenido de la publicación de hoy.
        2. En función de lo que cuenta la publicación (archivos, funciones o interfaz mencionadas),
           genera DINÁMICAMENTE la captura específica para este post (código exacto con líneas reales,
           git diff del commit o vista en vivo).
        3. Envía el borrador a Telegram (@JobGaBot) para confirmación previa.
        """
        entry = cls.pick_next_diary_entry(project_filter=project_filter)
        project_slug = entry["dir_name"].strip().lower().replace(" ", "_")
        repo_path = PROJECTS_ROOT / entry["dir_name"]

        print(f"\n📓 [DevDiary] Preparando Borrador #{entry['entry_number']}: {entry['display_name']}")

        # 1. Generar PRIMERO el texto de la publicación y el primer comentario (URL del repo + pregunta)
        post_text = cls.generate_diary_copy(entry)
        first_comment = cls.generate_first_comment(entry)

        # 2. Construir galería dinámica de capturas según el proyecto y el contenido del post:
        #    - Captura 1 (si tiene UI/consola en vivo): Interfaz y funcionalidades reales en ejecución
        #    - Captura 2 (siempre): Bloque de código exacto (archivo + líneas reales) del que habla el post
        dyn = cls._extract_dynamic_code_from_post(repo_path, post_text, entry)
        ts_suffix = datetime.now().strftime("%H%M%S")
        image_paths: List[Path] = []

        live_spec = entry.get("live_capture")
        if live_spec and repo_path.exists():
            print(f"[*] Extrayendo galería real de la UI/funcionalidades en vivo ({live_spec.get('mode')})...")
            ui_imgs = ProjectCapturer.capture_live_project_gallery(
                project_dir=repo_path,
                capture_spec=live_spec,
                base_prefix=f"devlog_{entry['entry_number']}_{project_slug}_{ts_suffix}"
            )
            for idx_img, ui_img in enumerate(ui_imgs, 1):
                image_paths.append(ui_img)
                print(f"[✓] Captura {idx_img} (UI / Funcionalidades en vivo): {ui_img}")

        print(f"[*] Extrayendo captura dinámica del código citado en el post -> {dyn['source_file']} (línea {dyn['start_line']})...")
        code_img = ProjectCapturer.generate_code_card(
            project_name=entry["dir_name"].strip(),
            headline=entry["default_headline"],
            code_snippet=dyn["snippet"],
            tech_tags=entry["tech_stack"][:4],
            filename=f"devlog_{entry['entry_number']}_{project_slug}_{ts_suffix}_{len(image_paths) + 1}_code.png",
            source_file=dyn["source_file"],
            git_commit=dyn["git_commit"],
            start_line=dyn["start_line"]
        )
        if code_img and code_img.exists():
            image_paths.append(code_img)
            print(f"[✓] Captura {len(image_paths)} (Código dinámico {dyn['source_file']}): {code_img}")

        # 3. Enviar a Telegram para revisión y confirmación previa (incluyendo las capturas y el primer comentario)
        project_title = f"Diario #{entry['entry_number']} · {entry['dir_name'].strip()}"
        draft_id = TelegramReviewer.send_draft(
            project_name=project_title,
            post_text=post_text,
            image_path=image_paths,
            first_comment=first_comment
        )

        if not draft_id:
            print("[!] No se pudo enviar el borrador a Telegram.")
            return None

        history = cls._load_history()
        record = {
            "entry_number": entry["entry_number"],
            "draft_id": draft_id,
            "date": datetime.now().isoformat(),
            "dir_name": entry["dir_name"],
            "source_file": dyn["source_file"],
            "display_name": entry["display_name"],
            "commits_included": entry.get("commits", [])[:3],
            "image_paths": [str(p) for p in image_paths],
            "first_comment": first_comment,
            "post_preview": post_text[:250],
            "status": "pending_approval"
        }
        history.append(record)
        cls._save_history(history)

        if wait_approval:
            published = TelegramReviewer.listen_and_process_decision(target_draft_id=draft_id, timeout=900)
            record["status"] = "published" if published else "pending_or_rejected"
            cls._save_history(history)

        return record

    @classmethod
    def regenerate_draft_by_id(cls, old_draft_id: str) -> Optional[str]:
        """
        Regenera un borrador existente seleccionando el mismo proyecto pero forzando un nuevo
        enfoque técnico / función distinta del repositorio y enviando el nuevo borrador a Telegram.
        """
        from src.telegram_reviewer import _get_drafts, _save_drafts
        drafts = _get_drafts()
        old = drafts.get(old_draft_id, {})
        proj_label = old.get("project_name", "")
        proj_filter = proj_label.split("·")[-1].strip() if "·" in proj_label else None
        if old_draft_id in drafts:
            drafts[old_draft_id]["status"] = "regenerated"
            _save_drafts(drafts)
        rec = cls.prepare_daily_diary_draft(wait_approval=False, project_filter=proj_filter)
        return rec.get("draft_id") if rec else None
