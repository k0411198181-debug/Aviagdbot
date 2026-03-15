import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str       = os.getenv("BOT_TOKEN", "")
TP_TOKEN: str        = os.getenv("TP_TOKEN", "")
TP_MARKER: str       = os.getenv("TP_MARKER", "")
BOT_USERNAME: str    = os.getenv("BOT_USERNAME", "ticketradaRubot")
DB_PATH: str         = os.getenv("DB_PATH", "bot.db")
CHECK_INTERVAL: int  = int(os.getenv("CHECK_INTERVAL", "3600"))
LOG_LEVEL: str       = os.getenv("LOG_LEVEL", "INFO")
ADMIN_SECRET: str    = os.getenv("ADMIN_SECRET", "changeme_please")
MAX_ALERTS_FREE: int = int(os.getenv("MAX_ALERTS_FREE", "5"))
MAX_ALERTS_PRO: int  = int(os.getenv("MAX_ALERTS_PRO", "30"))
MAX_HISTORY: int     = int(os.getenv("MAX_HISTORY", "20"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан в .env")
if not TP_TOKEN:
    raise RuntimeError("TP_TOKEN не задан — получи на travelpayouts.com")
