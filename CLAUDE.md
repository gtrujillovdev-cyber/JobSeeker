# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# Primera vez: abrir navegador para login manual en LinkedIn
python main.py --setup-session
```

`.env` obligatorio:

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
GEMINI_API_KEY=...
# Opcionales:
HEADLESS_BROWSER=true
CHROMIUM_EXECUTABLE_PATH=
BROWSER_CHANNEL=chrome
JOB_SEARCH_KEYWORDS=Junior IT OR Practicas OR Becario
JOB_SEARCH_LOCATION=Sevilla, Spain
```

## Comandos de desarrollo

```bash
# Ejecutar suite completa (81 tests)
pytest -v

# Ejecutar un archivo de test concreto
pytest tests/test_anti_ban.py -v

# Pase diario completo (escaneo + engagement + borrador diario)
python main.py --pipeline

# Simulacion sin publicar
python main.py --pipeline --dry-run

# Daemon Telegram (long-polling, recibe approve/reject)
python main.py --bot

# Publicar borradores programados cuya hora haya llegado
python main.py --publish-scheduled
```

## Arquitectura

El sistema tiene **dos flujos independientes** que comparten infraestructura:

### Flujo 1: Publicacion de posts tecnicos en LinkedIn

```
main.py --pipeline
  └── scripts/daily_pass.py::run_daily_pass()
        └── src/pipeline.py::JobSeekerPipeline.run_post()
              1. ProjectCapturer   -> PNG de tarjeta de código (Playwright screenshot)
              2. CopyGenerator     -> texto del post via Gemini API
              3. TelegramReviewer  -> envía borrador con botones inline (aprobar/rechazar)
              4. LinkedInPublisher -> Playwright publica en LinkedIn tras aprobacion
```

### Flujo 2: Busqueda de empleo y aplicacion automatica

```
main.py --scan-jobs  -> JobScanner (Playwright scrape LinkedIn Jobs)
main.py --engage     -> EngagementEngine (propone conexiones RRHH via Telegram)
main.py --apply      -> EasyApplyEngine:
                          ATSAnalyzer.analyze_match() -> score 0-100% + CV elegido
                          Playwright sube CV PDF y completa Solicitud Sencilla
```

### Flujo 3: Diario de Desarrollo (pills educativas)

```
main.py --dev-diary
  └── DevDiaryGenerator.prepare_daily_diary_draft()
        EDUCATIONAL_PILLS_BY_PROJECT (banco de pildoras en dev_diary.py)
        -> extrae snippet real del codigo fuente del proyecto
        -> genera post educativo via Gemini (hook directo, parrafos cortos, sin URLs en el cuerpo; enlace al repo en primer comentario)
        -> TelegramReviewer para aprobacion o programacion (--publish-scheduled / bot)
        -> LinkedInPublisher
```

## Patrones criticos

### Browser y LinkedInPublisher (todos los modulos usan browser_helper)
`browser_helper.py::get_playwright_browser_context()` es el unico punto de entrada para Playwright. **Nunca instanciar `playwright.chromium` directamente en modulos de negocio.** Gestiona dos estrategias en orden de preferencia:
1. `storage_clean.json` / `storage_state.json` — inyeccion de cookies (portable entre maquinas)
2. `launch_persistent_context` con `BROWSER_PROFILE_DIR` (perfil local persistente)

En [`src/linkedin_publisher.py`](src/linkedin_publisher.py), tras adjuntar capturas, el boton `Siguiente`/`Next` del modal se selecciona por texto exacto visible (evitando botones del feed en segundo plano) y el editor TipTap/ProseMirror se valida por `offsetParent !== null` y se enfoca via JS (`focus()`) cuando su ancho inicial es `0px`.

### Anti-ban
`AntiBanValidator` (stateless, todo en disco) bloquea acciones si se supera el limite diario:
- Posts: `MAX_DAILY_POSTS` (default 2)
- Conexiones: `MAX_DAILY_CONNECTIONS` (default 5)
- Easy Apply: 5 candidaturas/dia

La deduplicacion de publicaciones usa triple verificacion: `pill_id`, hash SHA-256 normalizado del contenido, y firma del titulo. Siempre pasar `include_active_drafts=True` al comprobar duplicados desde el pipeline de diario.

### CV Routing (ATSAnalyzer)
CV unificado en `assets/cvs/`:
- `GTVCV_2027.pdf` — CV oficial actualizado (Software & Sistemas IT 2027)

`ATSAnalyzer.analyze_match()` hace keyword matching con limites de palabra (`\b`), pondera triple si la keyword aparece en el titulo de la vacante, y calcula score 0-100 siempre referenciando `GTVCV_2027.pdf`.

### Persistencia de estado
Todos los archivos JSON de estado viven en `data/` (git-excluido):
- `published_history.json` — historial de posts publicados (leido por `AntiBanValidator`)
- `engagement_history.json` — historial de conexiones/comentarios
- `dev_diary_history.json` — entradas del diario con `pill_id` y estado
- `pending_drafts.json` — borradores en espera de aprobacion Telegram

### config.py
Fuente unica de verdad para paths y variables de entorno. Importar siempre desde `config`, nunca usar `os.getenv()` directamente en modulos de `src/`.

## Sesion de LinkedIn

La sesion del navegador se guarda en `assets/.browser_profiles/` (git-excluido). Si expira, ejecutar de nuevo `python main.py --setup-session`. Para portabilidad entre maquinas, copiar `assets/.browser_profiles/storage_state.json` al destino; `browser_helper.py` lo detecta automaticamente.
