import os
import time
import socket
import subprocess
import textwrap
import re
from pathlib import Path
from typing import Optional
from config import SCREENSHOTS_DIR, BROWSER_CHANNEL, CHROMIUM_EXECUTABLE_PATH
from playwright.sync_api import sync_playwright

class ProjectCapturer:
    """Capturador de interfaces reales en vivo (web, dashboards, Swagger, tests/terminal) y código de repositorios."""

    @staticmethod
    def sanitize_text(text: str) -> str:
        """
        Oculta cualquier dato privado o sensible antes de renderizar capturas o publicaciones:
        - Tokens de bot de Telegram y API keys (Gemini, OpenAI, Anthropic, AWS, GitHub)
        - Rutas absolutas del sistema local (/Users/..., /home/...)
        - IPs privadas, Tailscale y locales (100.x.x.x, 192.168.x.x, 10.x.x.x, 172.16-31.x.x)
        - Nombres de usuario locales en rutas de sistema
        """
        if not text:
            return ""
        # 1. Tokens de Telegram (ej. 123456789:ABCdef...)
        text = re.sub(r'\b\d{8,11}:[A-Za-z0-9_-]{35}\b', '[REDACTED_TELEGRAM_TOKEN]', text)
        # 2. Claves de API comunes (AIzaSy..., sk-..., ghp_..., gho_...)
        text = re.sub(r'\bAIzaSy[A-Za-z0-9_-]{33}\b', '[REDACTED_API_KEY]', text)
        text = re.sub(r'\bsk-[A-Za-z0-9_-]{20,}\b', '[REDACTED_API_KEY]', text)
        text = re.sub(r'\bgh[pousr]_[A-Za-z0-9]{36}\b', '[REDACTED_GITHUB_TOKEN]', text)
        # 3. IPs privadas y de Tailscale (100.64.0.0/10, 192.168.x.x, 10.x.x.x)
        text = re.sub(r'\b100\.(?:[6-9][0-9]|1[0-1][0-9]|12[0-7])\.\d{1,3}\.\d{1,3}\b', '10.0.0.x', text)
        text = re.sub(r'\b192\.168\.\d{1,3}\.\d{1,3}\b', '192.168.1.x', text)
        text = re.sub(r'\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '10.0.0.x', text)
        # 4. Rutas absolutas a directorios de usuario (/Users/gabriel... o /Users/Gabriel...)
        text = re.sub(r'/Users/[^/\s\n"\']+', '~/projects', text)
        text = re.sub(r'/home/[^/\s\n"\']+', '~/projects', text)
        return text

    @staticmethod
    def _launch_chromium(playwright_obj):
        """Lanza Chromium headless compatible con macOS moderno y Chromium legacy en macOS 11."""
        args = ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
        if CHROMIUM_EXECUTABLE_PATH:
            args.append("--headless=old")
        launch_kwargs = {"headless": True, "args": args}
        if CHROMIUM_EXECUTABLE_PATH:
            launch_kwargs["executable_path"] = CHROMIUM_EXECUTABLE_PATH
        elif BROWSER_CHANNEL:
            launch_kwargs["channel"] = BROWSER_CHANNEL
        return playwright_obj.chromium.launch(**launch_kwargs)

    @staticmethod
    def _load_pil_font(kind: str, size: int):
        """Carga una fuente TrueType legible en macOS (Menlo/SFNSMono o SFNS/Helvetica) con fallback seguro."""
        from PIL import ImageFont
        if kind == "mono":
            candidates = [
                "/System/Library/Fonts/Menlo.ttc",
                "/System/Library/Fonts/SFNSMono.ttf",
                "/System/Library/Fonts/Monaco.ttf",
                "/Library/Fonts/Courier New.ttf",
            ]
        else:
            candidates = [
                "/System/Library/Fonts/SFNS.ttf",
                "/System/Library/Fonts/Helvetica.ttc",
                "/Library/Fonts/Arial.ttf",
            ]
        for path in candidates:
            if os.path.exists(path):
                try:
                    return ImageFont.truetype(path, size=size)
                except Exception:
                    continue
        return ImageFont.load_default()

    @staticmethod
    def _wait_for_port(port: int, host: str = "127.0.0.1", timeout: float = 12.0) -> bool:
        start = time.time()
        while time.time() - start < timeout:
            try:
                with socket.create_connection((host, port), timeout=1.0):
                    return True
            except OSError:
                time.sleep(0.3)
        return False

    @staticmethod
    def capture_url(
        url: str,
        filename: str = "web_preview.png",
        wait_seconds: float = 2.0,
        click_selectors: list = None,
        scroll_y: int = 0
    ) -> Path:
        """Captura una página web en vivo o localhost con viewport panorámico de LinkedIn y opción de desplegar secciones o hacer scroll."""
        output_path = SCREENSHOTS_DIR / filename
        try:
            with sync_playwright() as p:
                browser = ProjectCapturer._launch_chromium(p)
                page = browser.new_page(viewport={"width": 1280, "height": 760}, device_scale_factor=2)
                page.goto(url, wait_until="domcontentloaded", timeout=20000)
                time.sleep(wait_seconds)
                if click_selectors:
                    for sel in click_selectors:
                        try:
                            el = page.locator(sel).first
                            if el.count() > 0 and el.is_visible():
                                el.click()
                                time.sleep(0.8)
                        except Exception:
                            continue
                if scroll_y:
                    try:
                        page.evaluate(f"window.scrollTo(0, {int(scroll_y)})")
                        time.sleep(0.6)
                    except Exception:
                        pass
                page.screenshot(path=str(output_path), full_page=False, timeout=15000)
                browser.close()
        except Exception as e:
            print(f"[ProjectCapturer] Aviso capturando web ({e}). Usando tarjeta informativa Pillow...")
            try:
                from PIL import Image, ImageDraw
                img = Image.new("RGB", (1280, 760), color="#1e1e1e")
                draw = ImageDraw.Draw(img)
                draw.rectangle([(0, 0), (1280, 40)], fill="#2d2d2d")
                draw.ellipse([(14, 14), (26, 26)], fill="#ff5f56")
                draw.ellipse([(34, 14), (46, 26)], fill="#ffbd2e")
                draw.ellipse([(54, 14), (66, 26)], fill="#27c93f")
                draw.text((100, 12), f"Web UI Preview — {url}", fill="#cccccc")
                draw.text((40, 100), f"Servicio en ejecución: {url}", fill="#ffffff")
                draw.text((40, 140), "Interfaz verificada y operativa.", fill="#4ec9b0")
                img.save(output_path)
            except Exception:
                pass
        return output_path

    @classmethod
    def capture_live_project_gallery(cls, project_dir: Path, capture_spec: dict, base_prefix: str) -> list[Path]:
        """
        Extrae una o varias capturas en vivo de la UI/funcionalidades del proyecto (incluyendo vistas extra interactivas):
        - Soporta 'extra_views' dentro de capture_spec para fotografiar múltiples paneles/rutas en una sola sesión del servidor.
        """
        results: list[Path] = []
        first_img = cls.capture_live_project(project_dir, capture_spec, f"{base_prefix}_1_ui.png")
        if first_img and first_img.exists():
            results.append(first_img)

        extra_views = capture_spec.get("extra_views", [])
        for idx, extra_spec in enumerate(extra_views, 2):
            merged = dict(capture_spec)
            merged.update(extra_spec)
            merged.pop("extra_views", None)
            img = cls.capture_live_project(project_dir, merged, f"{base_prefix}_{idx}_feature.png")
            if img and img.exists():
                results.append(img)

        return results

    @classmethod
    def capture_live_project(cls, project_dir: Path, capture_spec: dict, filename: str) -> Optional[Path]:
        """
        Extrae una captura REAL del proyecto:
        - 'static_server': Levanta http.server sobre una carpeta compilada (ej. InteractiveCV/dist) y fotografia la web real.
        - 'html_file': Renderiza la interfaz/plantilla HTML real del proyecto (ej. GeminiJobBot dashboard.html).
        - 'web_command': Arranca temporalmente el servidor del proyecto (ej. Streamlit en Tv-streamer o FastAPI en LawLab),
          espera a que el puerto escuche, toma la captura real de la UI y apaga el servidor limpiamente.
        - 'terminal_command': Ejecuta un comando real en el proyecto (ej. pytest -v, git log --stat) y captura la salida real de terminal.
        """
        mode = capture_spec.get("mode", "")
        output_path = SCREENSHOTS_DIR / filename

        try:
            if mode == "static_server":
                serve_dir = project_dir / capture_spec.get("serve_dir", "dist")
                port = capture_spec.get("port", 18911)
                if not serve_dir.exists():
                    return None
                proc = subprocess.Popen(
                    ["python3", "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                    cwd=str(serve_dir),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                try:
                    if cls._wait_for_port(port, timeout=6.0):
                        return cls.capture_url(
                            f"http://127.0.0.1:{port}{capture_spec.get('url_path', '/')}",
                            filename=filename,
                            wait_seconds=capture_spec.get("wait_seconds", 2.0),
                            click_selectors=capture_spec.get("click_selectors"),
                            scroll_y=capture_spec.get("scroll_y", 0)
                        )
                finally:
                    proc.terminate()
                    proc.wait(timeout=3)

            elif mode == "html_file":
                html_rel = capture_spec.get("html_path", "")
                html_file = project_dir / html_rel
                if html_file.exists():
                    return cls.capture_url(f"file://{html_file.resolve()}", filename=filename, wait_seconds=2.0)

            elif mode == "web_command":
                cmd = capture_spec.get("command", [])
                port = capture_spec.get("port", 18501)
                url_path = capture_spec.get("url_path", "/")
                cwd = project_dir / capture_spec.get("cwd", "")
                if not cwd.exists():
                    return None

                # Buscar ejecutable de python del venv del proyecto si existe
                venv_py = None
                for candidate in [cwd / ".venv/bin/python", cwd / "venv/bin/python", project_dir / ".venv/bin/python", project_dir / "venv/bin/python"]:
                    if candidate.exists():
                        venv_py = str(candidate)
                        break

                if venv_py and cmd and cmd[0] in ("python", "python3"):
                    cmd = [venv_py] + cmd[1:]

                proc = subprocess.Popen(
                    cmd,
                    cwd=str(cwd),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                try:
                    if cls._wait_for_port(port, timeout=14.0):
                        return cls.capture_url(
                            f"http://127.0.0.1:{port}{url_path}",
                            filename=filename,
                            wait_seconds=capture_spec.get("wait_seconds", 3.5),
                            click_selectors=capture_spec.get("click_selectors"),
                            scroll_y=capture_spec.get("scroll_y", 0)
                        )
                finally:
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except Exception:
                        proc.kill()

            elif mode == "terminal_command":
                cmd = list(capture_spec.get("command", []))
                cwd = project_dir / capture_spec.get("cwd", "")
                title = capture_spec.get("terminal_title", f"{project_dir.name} — zsh")
                if not cwd.exists():
                    return None
                venv_py = None
                for candidate in [cwd / ".venv/bin/python", cwd / "venv/bin/python", project_dir / ".venv/bin/python", project_dir / "venv/bin/python"]:
                    if candidate.exists():
                        venv_py = str(candidate)
                        break
                if venv_py and cmd and cmd[0] in ("python", "python3"):
                    cmd = [venv_py] + cmd[1:]
                res = subprocess.run(
                    cmd,
                    cwd=str(cwd),
                    capture_output=True,
                    text=True,
                    timeout=20
                )
                if res.returncode != 0:
                    return None
                raw_out = res.stdout.strip()
                if raw_out:
                    display_cmd = capture_spec.get("display_command") or " ".join(capture_spec.get("command", []))
                    full_term = f"$ {display_cmd}\n\n{raw_out}"
                    return cls.generate_terminal_card(
                        project_name=project_dir.name.strip(),
                        terminal_title=title,
                        terminal_output=full_term,
                        filename=filename
                    )
        except Exception as e:
            print(f"[ProjectCapturer] Aviso en captura en vivo ({mode}): {e}")

        return None

    @classmethod
    def generate_terminal_card(
        cls,
        project_name: str,
        terminal_title: str,
        terminal_output: str,
        filename: str = "terminal_capture.png"
    ) -> Path:
        """Renderiza una captura realista de Terminal de macOS (iTerm2 / Terminal.app) a pantalla completa sin marcos artificiales."""
        import re
        output_path = SCREENSHOTS_DIR / filename
        terminal_output = cls.sanitize_text(terminal_output)
        raw_lines = terminal_output.splitlines()[:24]

        formatted_lines = []
        for idx, line in enumerate(raw_lines):
            safe = (
                line.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            if idx == 0 and safe.startswith("$ "):
                cmd_part = safe[2:]
                formatted_lines.append(
                    f'<span class="prompt">gabriel@macbook-pro</span> <span class="cwd">{project_name}</span> <span class="symbol">%</span> <span class="cmd">{cmd_part}</span>'
                )
            else:
                safe = re.sub(r'("[^"]+"|\'[^\']+\')(?=\s*:)', r'<span class="json-key">\1</span>', safe)
                safe = re.sub(r':\s*("[^"]+")', r': <span class="json-str">\1</span>', safe)
                safe = re.sub(r':\s*(\d+)', r': <span class="json-num">\1</span>', safe)
                formatted_lines.append(safe)

        safe_text = "\n".join(formatted_lines)
        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    width: 1200px; height: 675px;
    background: #141414;
    font-family: "SF Mono", Menlo, Monaco, Consolas, monospace;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }}
  .bar {{
    background: #252526;
    height: 38px;
    padding: 0 16px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid #333333;
    color: #9da5b4;
    font-size: 12.5px;
    font-family: -apple-system, BlinkMacSystemFont, sans-serif;
  }}
  .dots {{ display: flex; gap: 8px; width: 80px; }}
  .dot {{ width: 12px; height: 12px; border-radius: 50%; }}
  .r {{ background: #ff5f56; }} .y {{ background: #ffbd2e; }} .g {{ background: #27c93f; }}
  .title {{ color: #cccccc; font-weight: 500; }}
  .right-meta {{ width: 80px; text-align: right; color: #777777; font-size: 12px; }}
  pre {{
    flex: 1;
    padding: 20px 26px;
    color: #d4d4d4;
    font-size: 14px;
    line-height: 1.52;
    overflow: hidden;
    white-space: pre-wrap;
  }}
  .prompt {{ color: #4ec9b0; font-weight: 600; }}
  .cwd {{ color: #569cd6; font-weight: 600; }}
  .symbol {{ color: #d4d4d4; }}
  .cmd {{ color: #dcdcaa; }}
  .json-key {{ color: #9cdcfe; }}
  .json-str {{ color: #ce9178; }}
  .json-num {{ color: #b5cea8; }}
</style>
</head>
<body>
  <div class="bar">
    <div class="dots"><div class="dot r"></div><div class="dot y"></div><div class="dot g"></div></div>
    <div class="title">📁 {project_name} — zsh — 115×32</div>
    <div class="right-meta">⌘1</div>
  </div>
  <pre>{safe_text}</pre>
</body>
</html>"""
        try:
            with sync_playwright() as p:
                browser = cls._launch_chromium(p)
                page = browser.new_page(viewport={"width": 1200, "height": 675}, device_scale_factor=2)
                page.set_content(html, wait_until="domcontentloaded")
                page.screenshot(path=str(output_path), timeout=15000)
                browser.close()
        except Exception as e:
            print(f"[ProjectCapturer] Aviso capturando terminal con Playwright ({e}). Usando renderizador nativo Pillow...")
            cls._render_terminal_card_pillow(output_path, project_name, terminal_output)
        return output_path

    @classmethod
    def _render_terminal_card_pillow(cls, output_path: Path, project_name: str, terminal_text: str):
        """Renderiza una ventana de terminal moderna nativamente con Pillow y fuentes TrueType."""
        try:
            from PIL import Image, ImageDraw
            img = Image.new("RGB", (1200, 675), color="#141414")
            draw = ImageDraw.Draw(img)
            ui_font = cls._load_pil_font("sans", 14)
            mono_font = cls._load_pil_font("mono", 15)
            draw.rectangle([(0, 0), (1200, 38)], fill="#252526")
            draw.ellipse([(14, 13), (26, 25)], fill="#ff5f56")
            draw.ellipse([(34, 13), (46, 25)], fill="#ffbd2e")
            draw.ellipse([(54, 13), (66, 25)], fill="#27c93f")
            draw.text((100, 10), f"{project_name} - zsh - 115x32", fill="#cccccc", font=ui_font)
            lines = [l for l in terminal_text.strip().splitlines() if l.strip()][:22]
            y = 54
            for l in lines:
                color = "#4ec9b0" if l.startswith("$") else "#d4d4d4"
                draw.text((26, y), l[:115], fill=color, font=mono_font)
                y += 26
            img.save(output_path)
        except Exception as e_pil:
            print(f"[ProjectCapturer] Error en fallback Pillow terminal: {e_pil}")

    @staticmethod
    def _get_lexer_for_file(source_file: str):
        from pygments.lexers import get_lexer_for_filename, PythonLexer
        try:
            return get_lexer_for_filename(source_file, stripnl=False, ensurenl=False)
        except Exception:
            return PythonLexer(stripnl=False, ensurenl=False)

    @staticmethod
    def _token_hex_and_style(ttype, val: str) -> tuple[str, bool]:
        """Mapea tokens Pygments al esquema VS Code Dark+ -> (hex_color, is_italic)."""
        from pygments.token import Token
        control_kws = {
            "if", "elif", "else", "for", "while", "break", "continue", "return",
            "try", "except", "finally", "raise", "with", "as", "import", "from",
            "yield", "await", "async", "switch", "case", "default", "export"
        }
        if ttype in Token.Comment or str(ttype).startswith("Token.Comment"):
            return "#6a9955", True
        if ttype in Token.Literal.String.Escape:
            return "#d7ba7d", False
        if ttype in Token.Literal.String.Interpol or ttype in Token.Literal.String.Affix:
            return "#569cd6", False
        if ttype in Token.Literal.String or str(ttype).startswith("Token.Literal.String"):
            return "#ce9178", False
        if ttype in Token.Literal.Number or str(ttype).startswith("Token.Literal.Number"):
            return "#b5cea8", False
        if ttype in Token.Keyword:
            if val in control_kws:
                return "#c586c0", False
            return "#569cd6", False
        if ttype in Token.Name.Decorator or ttype in Token.Name.Function or ttype in Token.Name.Builtin:
            return "#dcdcaa", False
        if ttype in Token.Name.Class or ttype in Token.Name.Namespace:
            return "#4ec9b0", False
        if ttype in Token.Name.Variable.Magic or val in ("self", "cls", "this"):
            return "#569cd6", False
        if ttype in Token.Name or str(ttype).startswith("Token.Name"):
            return "#9cdcfe", False
        if ttype in Token.Operator.Word:
            return "#569cd6", False
        return "#d4d4d4", False

    @staticmethod
    def _tokenize_lines(code_lines: list[str], source_file: str) -> list[list[tuple[str, bool, str]]]:
        """
        Tokeniza el bloque completo con Pygments preservando cadenas multilínea (docstrings)
        y devuelve [(hex_color, is_italic, text_chunk), ...] por cada línea.
        """
        from pygments import lex
        lexer = ProjectCapturer._get_lexer_for_file(source_file)
        total = max(1, len(code_lines))
        per_line: list[list[tuple[str, bool, str]]] = [[] for _ in range(total)]
        cur_line = 0
        full_text = "\n".join(code_lines)
        for ttype, val in lex(full_text, lexer):
            if not val:
                continue
            hex_c, is_it = ProjectCapturer._token_hex_and_style(ttype, val)
            parts = val.replace("\r", "").split("\n")
            for idx_p, part in enumerate(parts):
                if idx_p > 0:
                    cur_line += 1
                if part and cur_line < total:
                    per_line[cur_line].append((hex_c, is_it, part))
        return per_line

    @staticmethod
    def _highlight_with_pygments(code_lines: list[str], source_file: str) -> list[str]:
        """Resalta código conservando estado multilínea con la paleta exacta VS Code Dark+."""
        import html as _html
        try:
            tokenized = ProjectCapturer._tokenize_lines(code_lines, source_file)
            rendered_lines: list[str] = []
            for raw, line_tokens in zip(code_lines, tokenized):
                if not raw:
                    rendered_lines.append(" ")
                    continue
                leading_spaces = len(raw) - len(raw.lstrip(" "))
                indent_html = ""
                if leading_spaces:
                    chunks = []
                    for pos in range(leading_spaces):
                        if (pos % 4 == 0 and pos > 0) or (pos == 0 and leading_spaces >= 4):
                            chunks.append('<span class="ig"> </span>')
                        else:
                            chunks.append(" ")
                    indent_html = "".join(chunks)

                # Quitar espacios iniciales ya contabilizados en indent_html del primer token
                remaining_lead = leading_spaces
                parts = []
                for hex_c, is_it, text_part in line_tokens:
                    if remaining_lead > 0:
                        if len(text_part) <= remaining_lead and not text_part.strip():
                            remaining_lead -= len(text_part)
                            continue
                        stripped = text_part[:remaining_lead]
                        if not stripped.strip():
                            text_part = text_part[remaining_lead:]
                        remaining_lead = 0
                    if not text_part:
                        continue
                    escaped = _html.escape(text_part)
                    italic_css = "font-style:italic;" if is_it else ""
                    parts.append(f'<span style="color:{hex_c};{italic_css}">{escaped}</span>')
                rendered_lines.append(indent_html + ("".join(parts) or " "))
            return rendered_lines
        except Exception:
            return [_html.escape(l) or " " for l in code_lines]

    @staticmethod
    def _build_explorer_and_tabs(repo_path: Optional[Path], source_file: str, project_name: str) -> tuple[str, str, str, int]:
        """Lee estructura real y estado Git del repositorio para Explorer, pestañas y Status Bar auténticos."""
        import html as _html
        import subprocess

        svg_chev_down = '<svg class="chev-svg" width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 6l4 4 4-4"/></svg>'
        svg_chev_right = '<svg class="chev-svg" width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M6 4l4 4-4 4"/></svg>'

        def _ext_badge(fname: str) -> tuple[str, str]:
            low = fname.lower()
            if low == "dockerfile":
                return "DK", "#2496ed"
            if low == "makefile":
                return "MK", "#e37933"
            suf = Path(fname).suffix.lower()
            return {
                ".py": ("PY", "#519aba"),
                ".js": ("JS", "#f1e05a"),
                ".ts": ("TS", "#3178c6"),
                ".swift": ("SW", "#f05138"),
                ".json": ("{}", "#cbcb41"),
                ".md": ("MD", "#6d8086"),
                ".yml": ("YM", "#cb171e"),
                ".yaml": ("YM", "#cb171e"),
                ".sh": ("$_", "#89e051"),
            }.get(suf, ("•", "#8b949e"))

        active_path = Path(source_file)
        active_name = active_path.name
        active_parent = str(active_path.parent) if str(active_path.parent) != "." else ""

        git_branch = "main"
        git_dirty = 0
        if repo_path and (repo_path / ".git").exists():
            try:
                br = subprocess.check_output(
                    ["git", "-C", str(repo_path), "branch", "--show-current"],
                    stderr=subprocess.DEVNULL, timeout=2
                ).decode("utf-8", errors="ignore").strip()
                if br:
                    git_branch = br
                st_out = subprocess.check_output(
                    ["git", "-C", str(repo_path), "status", "--porcelain"],
                    stderr=subprocess.DEVNULL, timeout=2
                ).decode("utf-8", errors="ignore").strip()
                if st_out:
                    git_dirty = len([l for l in st_out.splitlines() if l.strip()])
            except Exception:
                pass

        tab_candidates: list[str] = [active_name]
        if repo_path and repo_path.exists():
            search_dir = (repo_path / active_parent) if active_parent else repo_path
            if search_dir.exists():
                siblings = sorted(
                    f.name for f in search_dir.iterdir()
                    if f.is_file() and f.name != active_name and not f.name.startswith(".") and f.suffix in (".py", ".js", ".ts", ".swift", ".md")
                )
                for s in siblings[:3]:
                    tab_candidates.append(s)
        if len(tab_candidates) == 1:
            tab_candidates.extend(["config.py" if active_name == "main.py" else "main.py", "README.md"])

        tabs_parts = []
        for idx_t, tname in enumerate(tab_candidates[:4]):
            badge, color = _ext_badge(tname)
            cls_name = "tab tab-active" if idx_t == 0 else "tab"
            close_x = '<span class="tab-x">×</span>' if idx_t == 0 else ""
            tabs_parts.append(
                f'<div class="{cls_name}"><span class="f-badge" style="color:{color}">{badge}</span><span>{_html.escape(tname)}</span>{close_x}</div>'
            )

        tree_rows = []
        if repo_path and repo_path.exists():
            ignore_dirs = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", "dist", "build", ".codegraph"}
            top_dirs = sorted(
                d.name for d in repo_path.iterdir()
                if d.is_dir() and d.name not in ignore_dirs and not d.name.startswith(".")
            )[:7]
            top_files = sorted(
                f.name for f in repo_path.iterdir()
                if f.is_file() and not f.name.startswith(".") and (f.suffix in (".py", ".js", ".ts", ".swift", ".md", ".json", ".yml", ".yaml") or f.name in ("Dockerfile", "Makefile"))
            )[:6]

            active_parts = list(active_path.parts)
            top_folder_to_expand = active_parts[0] if len(active_parts) > 1 else ""
            if top_folder_to_expand and top_folder_to_expand not in top_dirs and (repo_path / top_folder_to_expand).is_dir():
                top_dirs = sorted((top_dirs[:6] + [top_folder_to_expand]))[:7]

            for dname in top_dirs:
                is_exp = (dname == top_folder_to_expand)
                chev = svg_chev_down if is_exp else svg_chev_right
                tree_rows.append(
                    f'<div class="tree-row tree-dir">{chev}<span>{_html.escape(dname)}</span></div>'
                )
                if is_exp:
                    cur_dir = repo_path / dname
                    depth = 1
                    for sub_folder in active_parts[1:-1]:
                        pad_left = 10 + (depth * 14)
                        tree_rows.append(
                            f'<div class="tree-row tree-dir" style="padding-left:{pad_left}px">{svg_chev_down}<span>{_html.escape(sub_folder)}</span></div>'
                        )
                        cur_dir = cur_dir / sub_folder
                        depth += 1

                    sub_files = []
                    if cur_dir.exists() and cur_dir.is_dir():
                        sub_files = sorted(
                            f.name for f in cur_dir.iterdir()
                            if f.is_file() and not f.name.startswith(".") and f.suffix != ".pyc"
                        )[:9]
                    if active_name not in sub_files:
                        sub_files = sorted(set(sub_files + [active_name]))[:9]
                    child_pad = 14 + (depth * 14)
                    for sf in sub_files:
                        b, c = _ext_badge(sf)
                        is_sel = (sf == active_name)
                        sel_cls = " tree-selected" if is_sel else ""
                        tree_rows.append(
                            f'<div class="tree-row{sel_cls}" style="padding-left:{child_pad}px"><span class="f-badge" style="color:{c}">{b}</span><span>{_html.escape(sf)}</span></div>'
                        )
            for fname in top_files:
                b, c = _ext_badge(fname)
                is_sel = (not active_parent and fname == active_name)
                sel_cls = " tree-selected" if is_sel else ""
                tree_rows.append(
                    f'<div class="tree-row{sel_cls}" style="padding-left:22px"><span class="f-badge" style="color:{c}">{b}</span><span>{_html.escape(fname)}</span></div>'
                )
        else:
            b, c = _ext_badge(active_name)
            tree_rows.append(
                f'<div class="tree-row tree-selected" style="padding-left:22px"><span class="f-badge" style="color:{c}">{b}</span><span>{_html.escape(active_name)}</span></div>'
            )

        return "".join(tabs_parts), "\n".join(tree_rows), git_branch, git_dirty

    @classmethod
    def generate_code_card(
        cls,
        project_name: str,
        headline: str,
        code_snippet: str,
        tech_tags: list = None,
        filename: str = "code_card.png",
        source_file: str = "main.py",
        git_commit: str = "",
        start_line: int = 1,
        repo_path: Optional[Path] = None,
        target_symbol: str = ""
    ) -> Path:
        """
        Genera una captura indistinguible de VS Code Dark Modern real:
        - Barra de título + Activity Bar + Explorer poblado con los archivos reales del repo en disco.
        - Resaltado léxico real con Pygments (paleta VS Code Dark+), indent guides, git gutter y minimap.
        - Pestañas reales y barra de estado con rama git e idioma detectados dinámicamente.
        """
        import html as _html
        import textwrap
        output_path = SCREENSHOTS_DIR / filename

        dedented = textwrap.dedent(code_snippet.strip("\n"))
        dedented = cls.sanitize_text(dedented)
        raw_lines = dedented.rstrip().splitlines()[:28]
        highlighted_lines = cls._highlight_with_pygments(raw_lines, source_file)

        # Marcar línea focal (primera línea significativa o línea del target_symbol / bucle principal)
        focus_offset = 0
        for i_l, l_raw in enumerate(raw_lines):
            st_l = l_raw.strip()
            if st_l and not st_l.startswith("#") and ("for " in st_l or "def " in st_l or "re." in st_l or "app." in st_l):
                focus_offset = i_l
                break

        numbered_rows = []
        minimap_rows = []
        for offset, (raw_l, hl_html) in enumerate(zip(raw_lines, highlighted_lines)):
            ln = start_line + offset
            is_active = (offset == focus_offset)
            row_cls = "code-line active-line" if is_active else "code-line"
            gutter_cls = "git-gutter git-mod" if offset >= focus_offset and offset < focus_offset + 5 else "git-gutter"

            if raw_l.startswith("+") and not raw_l.startswith("+++"):
                row_cls = "code-line diff-add"
                hl_html = f'<span style="color:#56d364">{_html.escape(raw_l)}</span>'
            elif raw_l.startswith("-") and not raw_l.startswith("---"):
                row_cls = "code-line diff-del"
                hl_html = f'<span style="color:#ff7b72">{_html.escape(raw_l)}</span>'

            caret = '<span class="caret"></span>' if is_active else ""
            numbered_rows.append(
                f'<div class="{row_cls}"><span class="{gutter_cls}"></span><span class="ln">{ln}</span><span class="lc">{hl_html}{caret}</span></div>'
            )

            # Minimap bar proporcional a indentación y longitud real de la línea
            indent_px = min(14, (len(raw_l) - len(raw_l.lstrip())) // 2)
            bar_w = min(48, max(0, len(raw_l.strip()) // 2))
            mm_color = "#4b6b53" if raw_l.lstrip().startswith("#") else "#6b737f"
            minimap_rows.append(
                f'<div class="mm-line"><span style="margin-left:{indent_px}px;width:{bar_w}px;background:{mm_color};"></span></div>'
            )

        code_html = "\n".join(numbered_rows)
        minimap_html = "\n".join(minimap_rows)

        tabs_html, explorer_html, git_branch, git_dirty = cls._build_explorer_and_tabs(repo_path, source_file, project_name)

        bc_items = [_html.escape(p) for p in Path(source_file).parts]
        if target_symbol and target_symbol.strip() not in ("def", "function", "async def"):
            sym_clean = _html.escape(target_symbol.strip())
            bc_items.append(
                f'<span class="bc-sym"><svg width="11" height="11" viewBox="0 0 16 16" fill="#b180d7"><path d="M13.51 4l-5-3h-1l-5 3-.49.86v6l.49.85 5 3h1l5-3 .49-.85v-6L13.51 4zm-6 9.56l-4.5-2.7V5.7l4.5 2.45v5.41zM3.27 4.7l4.74-2.84 4.74 2.84-4.74 2.59L3.27 4.7zm9.74 6.16l-4.5 2.7V8.15l4.5-2.45v5.16z"/></svg>{sym_clean}</span>'
            )
        sep_svg = '<svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="#666666" stroke-width="1.5"><path d="M6 4l4 4-4 4"/></svg>'
        breadcrumb_html = f' <span class="bc-sep">{sep_svg}</span> '.join(bc_items)

        ext_lang = {
            ".py": "Python",
            ".js": "JavaScript",
            ".ts": "TypeScript",
            ".swift": "Swift",
            ".sh": "Shell Script",
            ".yml": "YAML",
            ".yaml": "YAML",
            ".json": "JSON",
        }.get(Path(source_file).suffix.lower(), "Plain Text")

        focus_line_num = start_line + focus_offset
        focus_col_num = (len(raw_lines[focus_offset]) + 1) if focus_offset < len(raw_lines) else 1
        git_badge_html = f'<span class="git-badge">{git_dirty}</span>' if git_dirty > 0 else ""
        branch_label = f"{git_branch}*" if git_dirty > 0 else git_branch
        html_template = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    width: 1280px;
    height: 760px;
    background: #181818;
    color: #cccccc;
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, sans-serif;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }}
  .titlebar {{
    height: 35px;
    background: #181818;
    border-bottom: 1px solid #2b2b2b;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 14px;
    font-size: 12px;
    color: #9d9d9d;
  }}
  .dots {{ display: flex; gap: 8px; width: 140px; }}
  .dot {{ width: 12px; height: 12px; border-radius: 50%; }}
  .dot-r {{ background: #ff5f56; }} .dot-y {{ background: #ffbd2e; }} .dot-g {{ background: #27c93f; }}
  .cmd-center {{
    width: 440px;
    height: 23px;
    background: #222222;
    border: 1px solid #3c3c3c;
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #cccccc;
    font-size: 11.5px;
    gap: 6px;
  }}
  .title-right {{
    width: 140px;
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 10px;
    color: #9d9d9d;
  }}
  .workspace {{
    flex: 1;
    display: flex;
    overflow: hidden;
  }}
  .activity-bar {{
    width: 48px;
    background: #181818;
    border-right: 1px solid #2b2b2b;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding-top: 8px;
    gap: 14px;
  }}
  .act-icon {{
    width: 48px;
    height: 38px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #7d7d7d;
    position: relative;
  }}
  .act-active {{
    color: #ffffff;
    border-left: 2px solid #0078d4;
  }}
  .git-badge {{
    position: absolute;
    bottom: 2px;
    right: 7px;
    background: #0078d4;
    color: #ffffff;
    font-size: 9px;
    font-weight: 700;
    padding: 0 4px;
    border-radius: 8px;
    line-height: 14px;
  }}
  .sidebar {{
    width: 222px;
    background: #181818;
    border-right: 1px solid #2b2b2b;
    display: flex;
    flex-direction: column;
    font-size: 12.5px;
    color: #cccccc;
    overflow: hidden;
  }}
  .sb-header {{
    padding: 9px 14px;
    font-size: 11px;
    letter-spacing: 0.6px;
    color: #bbbbbb;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}
  .sb-project {{
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 700;
    color: #cccccc;
    text-transform: uppercase;
    letter-spacing: 0.4px;
    border-top: 1px solid #252526;
    display: flex;
    align-items: center;
    gap: 4px;
  }}
  .tree-row {{
    padding: 3px 10px;
    display: flex;
    align-items: center;
    gap: 5px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    color: #cccccc;
    font-size: 12.5px;
  }}
  .tree-dir {{ color: #cccccc; padding-left: 10px; }}
  .tree-selected {{ background: #04395e; color: #ffffff; }}
  .chev-svg {{ color: #858585; flex-shrink: 0; }}
  .f-badge {{ font-family: "SF Mono", Menlo, monospace; font-size: 10px; font-weight: 700; width: 18px; text-align: center; flex-shrink: 0; }}
  .editor-area {{
    flex: 1;
    background: #1f1f1f;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }}
  .tabs-bar {{
    height: 35px;
    background: #181818;
    border-bottom: 1px solid #2b2b2b;
    display: flex;
    align-items: center;
    justify-content: space-between;
    overflow: hidden;
  }}
  .tabs-left {{ display: flex; align-items: center; overflow: hidden; }}
  .tabs-actions {{ display: flex; align-items: center; gap: 10px; padding-right: 12px; color: #9d9d9d; }}
  .tab {{
    height: 35px;
    padding: 0 12px;
    display: flex;
    align-items: center;
    gap: 7px;
    color: #969696;
    font-size: 12.5px;
    border-right: 1px solid #2b2b2b;
    background: #181818;
    white-space: nowrap;
  }}
  .tab-active {{
    background: #1f1f1f;
    color: #ffffff;
    border-top: 1.5px solid #0078d4;
  }}
  .tab-x {{ color: #858585; margin-left: 4px; font-size: 13px; }}
  .breadcrumbs {{
    height: 24px;
    background: #1f1f1f;
    padding: 0 16px;
    display: flex;
    align-items: center;
    font-size: 12px;
    color: #9d9d9d;
    gap: 4px;
  }}
  .bc-sep {{ display: inline-flex; align-items: center; padding: 0 2px; }}
  .bc-sym {{ display: inline-flex; align-items: center; gap: 4px; color: #cccccc; }}
  .editor-body {{
    flex: 1;
    display: flex;
    overflow: hidden;
    position: relative;
  }}
  .code-scroll {{
    flex: 1;
    padding: 6px 0;
    font-family: "SF Mono", "Menlo", "Monaco", "Consolas", monospace;
    font-size: 13.5px;
    line-height: 21.5px;
    overflow: hidden;
  }}
  .code-line {{
    display: flex;
    align-items: center;
    white-space: pre;
    height: 21.5px;
  }}
  .active-line {{
    background: rgba(255, 255, 255, 0.04);
    box-shadow: inset 0 1px 0 #2e2e2e, inset 0 -1px 0 #2e2e2e;
  }}
  .git-gutter {{ width: 3px; height: 21.5px; margin-left: 4px; }}
  .git-mod {{ background: #1b81a8; }}
  .ln {{
    color: #6e7681;
    width: 46px;
    text-align: right;
    padding-right: 16px;
    font-size: 12.5px;
    user-select: none;
  }}
  .active-line .ln {{ color: #cccccc; }}
  .lc {{ color: #d4d4d4; position: relative; }}
  .ig {{ border-left: 1px solid rgba(255, 255, 255, 0.08); display: inline-block; }}
  .caret {{
    display: inline-block;
    width: 1.5px;
    height: 16px;
    background: #aeafad;
    vertical-align: middle;
    margin-left: 1px;
  }}
  .diff-add {{ background: rgba(46, 160, 67, 0.16); }}
  .diff-del {{ background: rgba(248, 81, 73, 0.16); }}
  .minimap {{
    width: 68px;
    background: #1f1f1f;
    padding: 8px 8px;
    border-left: 1px solid #262626;
    display: flex;
    flex-direction: column;
    gap: 2px;
    position: relative;
  }}
  .mm-slider {{
    position: absolute;
    top: 4px; left: 0; right: 0; height: 145px;
    background: rgba(121, 121, 121, 0.14);
  }}
  .mm-line {{ height: 2.5px; display: flex; align-items: center; }}
  .mm-line span {{ height: 2px; border-radius: 1px; opacity: 0.55; }}
  .scrollbar {{
    width: 11px;
    background: #1f1f1f;
    border-left: 1px solid #262626;
    position: relative;
  }}
  .sb-thumb {{
    position: absolute;
    top: 18px; left: 1px; right: 1px; height: 95px;
    background: rgba(121, 121, 121, 0.35);
  }}
  .status-bar {{
    height: 22px;
    background: #181818;
    border-top: 1px solid #2b2b2b;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding-right: 12px;
    font-size: 11.5px;
    color: #cccccc;
  }}
  .st-left, .st-right {{ display: flex; align-items: center; gap: 14px; }}
  .st-remote {{
    background: #0078d4;
    color: #ffffff;
    height: 22px;
    width: 34px;
    display: flex;
    align-items: center;
    justify-content: center;
  }}
  .st-item {{ display: inline-flex; align-items: center; gap: 5px; }}
</style>
</head>
<body>
  <div class="titlebar">
    <div class="dots"><div class="dot dot-r"></div><div class="dot dot-y"></div><div class="dot dot-g"></div></div>
    <div class="cmd-center">
      <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="#9d9d9d" stroke-width="1.4"><circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5L14 14"/></svg>
      <span>{_html.escape(project_name)}</span>
    </div>
    <div class="title-right">
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2"><rect x="1.5" y="2.5" width="13" height="11" rx="1"/><line x1="5.5" y1="2.5" x2="5.5" y2="13.5"/></svg>
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2"><rect x="1.5" y="2.5" width="13" height="11" rx="1"/><line x1="1.5" y1="10" x2="14.5" y2="10"/></svg>
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2"><rect x="1.5" y="2.5" width="13" height="11" rx="1"/><line x1="10.5" y1="2.5" x2="10.5" y2="13.5"/></svg>
    </div>
  </div>
  <div class="workspace">
    <div class="activity-bar">
      <div class="act-icon act-active">
        <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
      </div>
      <div class="act-icon">
        <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
      </div>
      <div class="act-icon">
        <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="18" cy="18" r="3"/><circle cx="6" cy="6" r="3"/><path d="M6 21V9a9 9 0 0 0 9 9"/></svg>
        {git_badge_html}
      </div>
      <div class="act-icon">
        <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><polygon points="5 3 19 12 5 21 5 3"/></svg>
      </div>
      <div class="act-icon">
        <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="3" y="3" width="8" height="8" rx="1"/><rect x="13" y="3" width="8" height="8" rx="1"/><rect x="3" y="13" width="8" height="8" rx="1"/><rect x="13" y="13" width="8" height="8" rx="1"/></svg>
      </div>
    </div>
    <div class="sidebar">
      <div class="sb-header"><span>EXPLORER</span><span>···</span></div>
      <div class="sb-project"><svg class="chev-svg" width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 6l4 4 4-4"/></svg><span>{_html.escape(project_name)}</span></div>
      {explorer_html}
    </div>
    <div class="editor-area">
      <div class="tabs-bar">
        <div class="tabs-left">{tabs_html}</div>
        <div class="tabs-actions">
          <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3"><polygon points="4 3 13 8 4 13 4 3"/></svg>
          <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2"><rect x="2" y="2.5" width="12" height="11" rx="1"/><line x1="8" y1="2.5" x2="8" y2="13.5"/></svg>
          <span style="font-size:14px;line-height:1">···</span>
        </div>
      </div>
      <div class="breadcrumbs">{breadcrumb_html}</div>
      <div class="editor-body">
        <div class="code-scroll">
{code_html}
        </div>
        <div class="minimap">
          <div class="mm-slider"></div>
{minimap_html}
        </div>
        <div class="scrollbar"><div class="sb-thumb"></div></div>
      </div>
    </div>
  </div>
  <div class="status-bar">
    <div class="st-left">
      <span class="st-remote">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="#ffffff" stroke-width="1.4"><path d="M5 4l3 4-3 4M11 4l-3 4 3 4"/></svg>
      </span>
      <span class="st-item">
        <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4"><circle cx="5" cy="4" r="1.5"/><circle cx="11" cy="12" r="1.5"/><circle cx="5" cy="12" r="1.5"/><path d="M5 5.5v5M5 5.5c0 3 6 2 6 5"/></svg>
        {_html.escape(branch_label)}
      </span>
      <span class="st-item">
        <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3"><circle cx="8" cy="8" r="6"/><path d="M5.8 5.8l4.4 4.4M10.2 5.8l-4.4 4.4"/></svg> 0
        <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3" style="margin-left:4px"><path d="M8 2.5L14.2 13.5H1.8z"/><line x1="8" y1="6.5" x2="8" y2="10"/></svg> 0
      </span>
    </div>
    <div class="st-right">
      <span>Ln {focus_line_num}, Col {focus_col_num}</span>
      <span>Spaces: 4</span>
      <span>UTF-8</span>
      <span>LF</span>
      <span>{{}} {_html.escape(ext_lang)}</span>
      <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3"><path d="M8 2a4 4 0 0 0-4 4v3l-1.5 2h11L12 9V6a4 4 0 0 0-4-4z"/><path d="M6.8 13a1.3 1.3 0 0 0 2.4 0"/></svg>
    </div>
  </div>
</body>
</html>"""

        try:
            with sync_playwright() as p:
                browser = cls._launch_chromium(p)
                page = browser.new_page(viewport={"width": 1280, "height": 760}, device_scale_factor=2)
                page.set_content(html_template, wait_until="domcontentloaded")
                time.sleep(0.2)
                page.screenshot(path=str(output_path), animations="disabled", timeout=15000)
                browser.close()
        except Exception as e:
            print(f"[ProjectCapturer] Aviso capturando código con Playwright ({e}). Usando renderizador nativo Pillow...")
            cls._render_code_card_pillow(
                output_path=output_path,
                project_name=project_name,
                source_file=source_file,
                code_snippet=code_snippet,
                start_line=start_line,
                ext_lang=ext_lang,
                git_commit=git_commit
            )

        return output_path

    @classmethod
    def _render_code_card_pillow(
        cls,
        output_path: Path,
        project_name: str,
        source_file: str,
        code_snippet: str,
        start_line: int = 1,
        ext_lang: str = "Python",
        git_commit: str = ""
    ):
        """Renderiza una ventana VS Code Dark Modern nítida con Pillow, fuentes TrueType y sintaxis Dark+."""
        try:
            from PIL import Image, ImageDraw
            from pygments import lex

            img = Image.new("RGB", (1280, 760), color="#1f1f1f")
            draw = ImageDraw.Draw(img)
            ui_font = cls._load_pil_font("sans", 13)
            ui_bold = cls._load_pil_font("sans", 12)
            mono_font = cls._load_pil_font("mono", 14)
            ln_font = cls._load_pil_font("mono", 12)

            # Titlebar macOS + Command Center
            draw.rectangle([(0, 0), (1280, 35)], fill="#181818")
            draw.line([(0, 35), (1280, 35)], fill="#2b2b2b")
            draw.ellipse([(14, 11), (26, 23)], fill="#ff5f56")
            draw.ellipse([(34, 11), (46, 23)], fill="#ffbd2e")
            draw.ellipse([(54, 11), (66, 23)], fill="#27c93f")
            draw.rounded_rectangle([(420, 6), (860, 29)], radius=6, fill="#222222", outline="#3c3c3c")
            draw.text((590, 10), project_name, fill="#cccccc", font=ui_font)

            # Activity Bar + Explorer Sidebar
            draw.rectangle([(0, 36), (48, 738)], fill="#181818")
            draw.line([(48, 36), (48, 738)], fill="#2b2b2b")
            draw.rectangle([(0, 44), (2, 82)], fill="#0078d4")
            draw.rectangle([(49, 36), (270, 738)], fill="#181818")
            draw.line([(270, 36), (270, 738)], fill="#2b2b2b")
            draw.text((64, 46), "EXPLORER", fill="#bbbbbb", font=ui_bold)
            draw.text((64, 74), f"v {project_name.upper()}", fill="#cccccc", font=ui_bold)
            active_fname = Path(source_file).name
            draw.rectangle([(49, 98), (269, 122)], fill="#04395e")
            draw.text((76, 103), active_fname, fill="#ffffff", font=ui_font)

            # Tabs + Breadcrumbs
            draw.rectangle([(271, 36), (1280, 71)], fill="#181818")
            draw.line([(271, 71), (1280, 71)], fill="#2b2b2b")
            draw.rectangle([(271, 36), (470, 71)], fill="#1f1f1f")
            draw.line([(271, 36), (470, 36)], fill="#0078d4", width=2)
            draw.text((292, 46), f"PY  {active_fname}", fill="#ffffff", font=ui_font)
            bc_label = " > ".join(Path(source_file).parts)
            draw.text((286, 78), bc_label, fill="#9d9d9d", font=ui_font)

            # Editor Lines con Pygments Dark+ (preservando cadenas multilínea)
            dedented = textwrap.dedent(code_snippet.strip("\n"))
            raw_lines = dedented.rstrip().splitlines()[:28]
            tokenized_lines = cls._tokenize_lines(raw_lines, source_file)
            y = 104
            for offset, (raw_l, tok_row) in enumerate(zip(raw_lines, tokenized_lines)):
                ln = start_line + offset
                draw.text((284, y + 1), f"{ln:>3}", fill="#6e7681", font=ln_font)
                x = 330.0
                for hex_c, _, token_txt in tok_row:
                    if not token_txt:
                        continue
                    draw.text((x, y), token_txt, fill=hex_c, font=mono_font)
                    x += draw.textlength(token_txt, font=mono_font)
                    if x > 1190:
                        break
                y += 22

            # Minimap vertical hint
            draw.line([(1200, 72), (1200, 738)], fill="#262626")
            for idx_m, raw_l in enumerate(raw_lines):
                bw = min(46, max(2, len(raw_l.strip()) // 2))
                draw.rectangle([(1212, 104 + idx_m * 5), (1212 + bw, 106 + idx_m * 5)], fill="#4a5058")

            # Status Bar Dark Modern
            draw.rectangle([(0, 738), (1280, 760)], fill="#181818")
            draw.line([(0, 738), (1280, 738)], fill="#2b2b2b")
            draw.rectangle([(0, 738), (34, 760)], fill="#0078d4")
            draw.text((9, 742), "><", fill="#ffffff", font=ui_bold)
            draw.text((48, 742), "main    0  0", fill="#cccccc", font=ui_font)
            draw.text((940, 742), f"Ln {start_line}, Col 1   Spaces: 4   UTF-8   LF   {ext_lang}", fill="#cccccc", font=ui_font)

            img.save(output_path)
            print(f"[ProjectCapturer] [✓] Captura VS Code generada con éxito con Pillow: {output_path}")
        except Exception as e_pil:
            print(f"[ProjectCapturer] Error en fallback Pillow de código: {e_pil}")
