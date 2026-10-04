import os
import sys
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    sys.exit("ERRORE: BOT_TOKEN mancante nel file .env")

# Supporta sia ALLOWED_USER_IDS che il vecchio ALLOWED_USER_ID per retrocompatibilità
raw_ids = os.getenv("ALLOWED_USER_IDS") or os.getenv("ALLOWED_USER_ID", "")
ALLOWED_USER_IDS: set[int] = {
    int(uid.strip()) 
    for uid in raw_ids.split(",") 
    if uid.strip().isdigit()
}

DATABASE_PATH = os.getenv("DATABASE_PATH", "workout_tracker.db")