import os
import sqlite3
import urllib.request
from datetime import datetime
from dotenv import load_dotenv

# Carica le variabili d'ambiente dal file .env del bot
ENV_PATH = "/home/ubuntu/gym-tracker-bot/.env"
load_dotenv(ENV_PATH)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USERS = os.getenv("ALLOWED_USER_IDS", "").split(",")
TARGET_CHAT_ID = ALLOWED_USERS[0].strip() if ALLOWED_USERS and ALLOWED_USERS[0].strip() else None

DB_PATH = "/home/ubuntu/gym-tracker-bot/workout_tracker.db"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP_PATH = f"/tmp/workout_tracker_backup_{TIMESTAMP}.db"


def run_backup():
    if not BOT_TOKEN:
        print("Errore: TELEGRAM_BOT_TOKEN non trovato nel file .env")
        return

    if not TARGET_CHAT_ID:
        print("Errore: Nessun ID utente valido specificato in ALLOWED_USER_IDS")
        return

    if not os.path.exists(DB_PATH):
        print(f"Errore: File di database non trovato in {DB_PATH}")
        return

    # 1. Esegui il backup a caldo (sicuro anche durante letture/scritture attive)
    print(f"Avvio backup atomico di {DB_PATH}...")
    try:
        with sqlite3.connect(DB_PATH) as src_conn, sqlite3.connect(BACKUP_PATH) as dst_conn:
            src_conn.backup(dst_conn)
        print(f"File temporaneo di backup generato in {BACKUP_PATH}")
    except Exception as e:
        print(f"Errore durante la creazione del backup SQLite: {e}")
        return

    # 2. Invia il file tramite Telegram Bot API senza dipendenze esterne
    boundary = "----GymTrackerBackupBoundary7MA4YWxkTrZu0gW"
    filename = f"gym_backup_{datetime.now().strftime('%Y-%m-%d')}.db"

    with open(BACKUP_PATH, "rb") as f:
        file_bytes = f.read()

    caption_text = f"📦 *Backup Automatico Gym Tracker*\nData: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="chat_id"\r\n\r\n{TARGET_CHAT_ID}\r\n'
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="parse_mode"\r\n\r\nMarkdown\r\n'
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="caption"\r\n\r\n{caption_text}\r\n'
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="document"; filename="{filename}"\r\n'
        f'Content-Type: application/x-sqlite3\r\n\r\n'
    ).encode("utf-8") + file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
    )

    try:
        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                print("Backup inviato con successo alla chat Telegram!")
            else:
                print(f"Risposta inattesa da Telegram: HTTP {response.status}")
    except Exception as e:
        print(f"Errore durante l'invio su Telegram: {e}")
    finally:
        # Pulizia del file temporaneo da /tmp
        if os.path.exists(BACKUP_PATH):
            os.remove(BACKUP_PATH)


if __name__ == "__main__":
    run_backup()