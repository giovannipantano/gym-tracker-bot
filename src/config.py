import os
import sys
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    sys.exit("ERRORE: BOT_TOKEN mancante nel file .env")

ALLOWED_USER_ID_STR = os.getenv("ALLOWED_USER_ID")
ALLOWED_USER_ID = int(ALLOWED_USER_ID_STR) if ALLOWED_USER_ID_STR else None
DATABASE_PATH = os.getenv("DATABASE_PATH", "workout_tracker.db")