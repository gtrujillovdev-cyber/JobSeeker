import os
import time
import socket
import subprocess
import textwrap
from pathlib import Path
from typing import Optional
from config import SCREENSHOTS_DIR, BROWSER_CHANNEL
from playwright.sync_api import sync_playwright

class ProjectCapturer:
    """Capturador de interfaces reales en vivo (web, dashboards, Swagger, tests/terminal) y código de repositorios."""

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
        with sync_playwright() as p:
            launch_kwargs = {"headless": True}
            if BROWSER_CHANNEL:
                launch_kwargs["channel"] = BROWSER_CHANNEL
            browser = p.chromium.launch(**launch_kwargs)
            page = browser.new_page(viewport={"width": 1280, "height": 760}, device_scale_factor=2)
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
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
            page.screenshot(path=str(output_path), full_page=False)
            browser.close()
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
                cmd = capture_spec.get("command", [])
                cwd = project_dir / capture_spec.get("cwd", "")
                title = capture_spec.get("terminal_title", f"{project_dir.name} — zsh")
                if not cwd.exists():
                    return None
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
                    cmd_str = " ".join(cmd)
                    full_term = f"$ {cmd_str}\n\n{raw_out}"
                    return cls.generate_terminal_card(
                        project_name=project_dir.name.strip(),
                        terminal_title=title,
                        terminal_output=full_term,
                        filename=filename
                    )
        except Exception as e:
            print(f"[ProjectCapturer] Aviso en captura en vivo ({mode}): {e}")

        return None

    @staticmethod
    def generate_terminal_card(
        project_name: str,
        terminal_title: str,
        terminal_output: str,
        filename: str = "terminal_capture.png"
    ) -> Path:
        """Renderiza la salida real de consola (pytest, git log, ejecución CLI) en una ventana de terminal macOS."""
        output_path = SCREENSHOTS_DIR / filename
        lines = terminal_output.splitlines()[:22]
        safe_text = (
            "\n".join(lines)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    width: 1200px; height: 675px;
    display: flex; align-items: center; justify-content: center;
    background: #0b0f17;
    font-family: "SF Mono", Menlo, monospace;
  }}
  .term {{
    width: 1100px; background: #0d1117;
    border-radius: 12px; border: 1px solid #30363d;
    box-shadow: 0 20px 50px rgba(0,0,0,0.85); overflow: hidden;
  }}
  .bar {{
    background: #161b22; padding: 12px 18px;
    display: flex; align-items: center; justify-content: space-between;
    border-bottom: 1px solid #30363d; color: #8b949e; font-size: 13px;
  }}
  .dots {{ display: flex; gap: 8px; }}
  .dot {{ width: 12px; height: 12px; border-radius: 50%; }}
  .r {{ background: #ff5f56; }} .y {{ background: #ffbd2e; }} .g {{ background: #27c93f; }}
  pre {{
    padding: 22px 26px; color: #3fb950;
    font-size: 14px; line-height: 1.55;
    min-height: 480px; max-height: 520px; overflow: hidden;
    white-space: pre-wrap;
  }}
</style>
</head>
<body>
  <div class="term">
    <div class="bar">
      <div class="dots"><div class="dot r"></div><div class="dot y"></div><div class="dot g"></div></div>
      <div>{terminal_title}</div>
      <div>macOS · zsh</div>
    </div>
    <pre>{safe_text}</pre>
  </div>
</body>
</html>"""
        with sync_playwright() as p:
            launch_kwargs = {"headless": True}
            if BROWSER_CHANNEL:
                launch_kwargs["channel"] = BROWSER_CHANNEL
            browser = p.chromium.launch(**launch_kwargs)
            page = browser.new_page(viewport={"width": 1200, "height": 675}, device_scale_factor=2)
            page.set_content(html)
            page.screenshot(path=str(output_path))
            browser.close()
        return output_path

    @staticmethod
    def generate_code_card(
        project_name: str,
        headline: str,
        code_snippet: str,
        tech_tags: list = None,
        filename: str = "code_card.png",
        source_file: str = "main.py",
        git_commit: str = "",
        start_line: int = 1
    ) -> Path:
        """
        Genera una captura de código limpia estilo IDE/Terminal con el archivo y bloque
        de código real del repositorio (sin titulares gigantes ni adornos artificiales).
        """
        output_path = SCREENSHOTS_DIR / filename
        tech_tags = tech_tags or ["Python", "Linux", "Automation"]
        tags_html = "".join([f'<span class="tag">{t}</span>' for t in tech_tags[:5]])

        # Numeración de líneas real como en un editor de código o vista git diff (+/- con colores reales)
        import textwrap
        dedented = textwrap.dedent(code_snippet.strip("\n"))
        raw_lines = dedented.rstrip().splitlines()[:18]
        numbered_rows = []
        for idx, line in enumerate(raw_lines, start_line):
            safe_line = (
                line.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            ) or " "
            row_class = "code-line"
            if line.startswith("+") and not line.startswith("+++"):
                row_class = "code-line diff-add"
            elif line.startswith("-") and not line.startswith("---"):
                row_class = "code-line diff-del"
            elif line.startswith("@@"):
                row_class = "code-line diff-hunk"
            numbered_rows.append(
                f'<div class="{row_class}"><span class="ln">{idx:3d}</span><span class="lc">{safe_line}</span></div>'
            )
        code_html = "\n".join(numbered_rows)
        commit_badge = f'<span class="commit-hash">git: {git_commit[:55]}</span>' if git_commit else f'<span class="commit-hash">{headline[:65]}</span>'

        html_template = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    width: 1200px;
    height: 675px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #0b0f17;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }}
  .card {{
    width: 1100px;
    background: #0d1117;
    border-radius: 12px;
    border: 1px solid #30363d;
    box-shadow: 0 20px 50px rgba(0, 0, 0, 0.8);
    overflow: hidden;
  }}
  .window-header {{
    background: #161b22;
    padding: 12px 18px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid #30363d;
  }}
  .header-left {{
    display: flex;
    align-items: center;
  }}
  .dots {{
    display: flex;
    gap: 8px;
  }}
  .dot {{
    width: 12px;
    height: 12px;
    border-radius: 50%;
  }}
  .dot-red {{ background: #ff5f56; }}
  .dot-yellow {{ background: #ffbd2e; }}
  .dot-green {{ background: #27c93f; }}
  .window-title {{
    margin-left: 16px;
    color: #c9d1d9;
    font-size: 13px;
    font-family: "SF Mono", Menlo, monospace;
    background: #0d1117;
    padding: 4px 12px;
    border-radius: 6px;
    border: 1px solid #30363d;
  }}
  .commit-hash {{
    color: #8b949e;
    font-size: 12px;
    font-family: "SF Mono", Menlo, monospace;
  }}
  .code-box {{
    background: #0d1117;
    padding: 22px 24px;
    color: #e6edf3;
    font-family: "SF Mono", Menlo, Consolas, monospace;
    font-size: 14.5px;
    line-height: 1.58;
    min-height: 450px;
    max-height: 490px;
    overflow: hidden;
  }}
  .code-line {{
    display: flex;
    white-space: pre;
    padding: 0 6px;
    border-radius: 3px;
  }}
  .diff-add {{
    background: rgba(46, 160, 67, 0.18);
  }}
  .diff-add .lc {{
    color: #56d364;
  }}
  .diff-del {{
    background: rgba(248, 81, 73, 0.18);
  }}
  .diff-del .lc {{
    color: #ff7b72;
  }}
  .diff-hunk .lc {{
    color: #79c0ff;
  }}
  .ln {{
    color: #484f58;
    width: 36px;
    text-align: right;
    padding-right: 16px;
    user-select: none;
  }}
  .lc {{
    color: #e6edf3;
  }}
  .status-bar {{
    background: #161b22;
    border-top: 1px solid #30363d;
    padding: 10px 20px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-family: "SF Mono", Menlo, monospace;
    font-size: 12px;
    color: #8b949e;
    white-space: nowrap;
  }}
  .tags {{
    display: flex;
    flex-wrap: nowrap;
    gap: 8px;
    white-space: nowrap;
  }}
  .tag {{
    background: #21262d;
    color: #58a6ff;
    padding: 3px 10px;
    border-radius: 4px;
    border: 1px solid #30363d;
    font-size: 12px;
    white-space: nowrap;
  }}
</style>
</head>
<body>
  <div class="card">
    <div class="window-header">
      <div class="header-left">
        <div class="dots">
          <div class="dot dot-red"></div>
          <div class="dot dot-yellow"></div>
          <div class="dot dot-green"></div>
        </div>
        <div class="window-title">{project_name} / {source_file}</div>
      </div>
      {commit_badge}
    </div>
    <div class="code-box">{code_html}</div>
    <div class="status-bar">
      <div>UTF-8 · Python / macOS · Gabriel Trujillo</div>
      <div class="tags">{tags_html}</div>
    </div>
  </div>
</body>
</html>"""

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1200, "height": 675})
            page.set_content(html_template)
            page.screenshot(path=str(output_path))
            browser.close()

        return output_path
