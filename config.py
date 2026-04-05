import os
from pathlib import Path
from dotenv import load_dotenv

# Explicitly find the .env file in the project root
BASE_DIR = Path(__file__).resolve().parent
env_path = BASE_DIR / ".env"
load_dotenv(dotenv_path=env_path)

# Telegram Bot
BOT_TOKEN = os.getenv("BOT_TOKEN")

# DeepSeek API
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")

# Database
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME")

DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Web App
WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = 8000
WEB_APP_URL = os.getenv("WEB_APP_URL", "http://localhost:8000")

# Validation to prevent start with missing keys
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set in .env file")
if not DEEPSEEK_API_KEY:
    raise ValueError("DEEPSEEK_API_KEY is not set in .env file")
