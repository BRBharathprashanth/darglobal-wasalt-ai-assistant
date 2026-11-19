
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# Website sources
SEED_URLS = [
    "https://www.darglobal.co.uk/",
    "https://wasalt.sa/en"
]

# OpenRouter configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

OPENROUTER_MODEL = os.getenv(
    "OPENROUTER_MODEL",
    "openrouter/free"
)

OPENROUTER_SITE_URL = os.getenv(
    "OPENROUTER_SITE_URL",
    "http://localhost:8501"
)

OPENROUTER_SITE_NAME = os.getenv(
    "OPENROUTER_SITE_NAME",
    "DarGlobal Wasalt Real Estate Assistant"
)

# AI request settings
OPENROUTER_MAX_RETRIES = int(
    os.getenv("OPENROUTER_MAX_RETRIES", "3")
)

OPENROUTER_RETRY_DELAY = float(
    os.getenv("OPENROUTER_RETRY_DELAY", "5")
)

OPENROUTER_TIMEOUT = int(
    os.getenv("OPENROUTER_TIMEOUT", "120")
)

OPENROUTER_MAX_TOKENS = int(
    os.getenv("OPENROUTER_MAX_TOKENS", "2500")
)

# Data and database paths
DATA_DIR = BASE_DIR / "data"
SQLITE_PATH = BASE_DIR / "knowledge_base.sqlite3"

# Scraper configuration
MAX_PAGES_PER_DOMAIN = int(
    os.getenv("MAX_PAGES_PER_DOMAIN", "20")
)

REQUEST_DELAY_SECONDS = float(
    os.getenv("REQUEST_DELAY_SECONDS", "1.5")
)

USER_AGENT = (
    "DarWasaltAcademicAssistant/1.0 "
    "(respectful public website research)"
)
