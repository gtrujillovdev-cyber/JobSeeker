import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

# Cargar variables de entorno desde .env si existe
load_dotenv(BASE_DIR / ".env")

# Directorios del sistema
ASSETS_DIR = BASE_DIR / "assets"
BROWSER_PROFILE_DIR = ASSETS_DIR / ".browser_profiles" / "linkedin_user_data"
STORAGE_STATE_FILE = ASSETS_DIR / ".browser_profiles" / "storage_state.json"
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
SCREENSHOTS_DIR = OUTPUT_DIR / "screenshots"
LOGS_DIR = BASE_DIR / "logs"

# Archivos de control
PROCESSED_FILE = DATA_DIR / "published_history.json"
ENGAGEMENT_FILE = DATA_DIR / "engagement_history.json"

# Asegurar existencia de directorios
for directory in [ASSETS_DIR, BROWSER_PROFILE_DIR, DATA_DIR, OUTPUT_DIR, SCREENSHOTS_DIR, LOGS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# Configuración de ejecución
HEADLESS = os.getenv("HEADLESS_BROWSER", "true").lower() in ["true", "1", "yes"]
MAX_DAILY_POSTS = int(os.getenv("MAX_DAILY_POSTS", "2"))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Detección inteligente de navegador: Chrome instalado o Chromium estándar
CHROMIUM_EXECUTABLE_PATH = os.getenv("CHROMIUM_EXECUTABLE_PATH")
if CHROMIUM_EXECUTABLE_PATH and not Path(CHROMIUM_EXECUTABLE_PATH).exists():
    CHROMIUM_EXECUTABLE_PATH = None

CHROME_PATH = Path("/Applications/Google Chrome.app")
default_channel = "chrome" if CHROME_PATH.exists() and not CHROMIUM_EXECUTABLE_PATH else None
BROWSER_CHANNEL = os.getenv("BROWSER_CHANNEL", default_channel)
if BROWSER_CHANNEL in ["", "none", "None"] or CHROMIUM_EXECUTABLE_PATH:
    BROWSER_CHANNEL = None

# Configurar Node.js personalizado si está definido en .env (para compatibilidad macOS legacy)
if os.getenv("PLAYWRIGHT_NODEJS_PATH"):
    os.environ["PLAYWRIGHT_NODEJS_PATH"] = os.getenv("PLAYWRIGHT_NODEJS_PATH")

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Job Scanner - Radar filtrado por Sevilla (España) y roles Junior / Prácticas / Becario IT
JOB_SEARCH_KEYWORDS = os.getenv(
    "JOB_SEARCH_KEYWORDS",
    'Junior IT OR Practicas OR Becario OR Ciberseguridad'
)
JOB_SEARCH_LOCATION = os.getenv("JOB_SEARCH_LOCATION", "Sevilla, Spain")
JOB_SCAN_MAX_RESULTS = int(os.getenv("JOB_SCAN_MAX_RESULTS", "15"))
JOB_EXPERIENCE_LEVEL = os.getenv("JOB_EXPERIENCE_LEVEL", "1,2") # 1 = Prácticas, 2 = Sin experiencia / Nivel inicial

# Engagement Engine - Limites diarios de seguridad
MAX_DAILY_CONNECTIONS = int(os.getenv("MAX_DAILY_CONNECTIONS", "5"))
MAX_DAILY_COMMENTS = int(os.getenv("MAX_DAILY_COMMENTS", "8"))
MAX_DAILY_REACTIONS = int(os.getenv("MAX_DAILY_REACTIONS", "15"))

# Perfil del Candidato para Notas de Conexión y Posts
CANDIDATE_PROFILE = {
    "name": "Gabriel Trujillo Vallejo",
    "location": "Sevilla",
    "headline": "Desarrollador de Software Junior (DAM) | Python, Sistemas Linux & Ciberseguridad",
    "background": "Estudiante/Graduado DAM (CESUR Sevilla) enfocado en ingeniería de software práctica, automatización en Python, sistemas Linux y ciberseguridad.",
    "skills": ["Linux / Redes", "Ciberseguridad", "Python / Bash", "FastAPI / Docker", "SwiftUI", "QA / Testing"],
    "target_roles": ["Desarrollador Junior", "Becario / Prácticas Ciberseguridad", "Administrador de Sistemas Junior", "Junior QA / Python", "Freelance"]
}
