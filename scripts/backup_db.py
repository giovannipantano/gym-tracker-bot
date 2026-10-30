"""
Backup a caldo del database SQLite, con copie locali a rotazione.

Il backup non viene più inviato su Telegram. Le copie restano sul server (cartella BACKUP_DIR, di
default "backups/"): proteggono da errori e corruzioni, ma NON dalla perdita del server. Per quello
copia periodicamente la cartella altrove (rsync, rclone verso uno storage cloud, ecc.): vedi README.
"""
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Percorsi derivati dalla posizione dello script: funziona ovunque sia clonato il progetto
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


DB_PATH = _resolve(os.getenv("DATABASE_PATH", "workout_tracker.db"))
BACKUP_DIR = _resolve(os.getenv("BACKUP_DIR", "backups"))
try:
    BACKUP_KEEP = max(1, int(os.getenv("BACKUP_KEEP", "14")))
except ValueError:
    BACKUP_KEEP = 14


def run_backup() -> bool:
    """Crea una copia verificata e ruota le vecchie. True solo se la copia è valida."""
    if not DB_PATH.exists():
        print(f"Errore: File di database non trovato in {DB_PATH}")
        return False

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(BACKUP_DIR, 0o700)  # il backup contiene dati personali di tutti gli utenti
    target = BACKUP_DIR / f"workout_tracker_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"

    print(f"Avvio backup atomico di {DB_PATH}...")
    src_conn = dst_conn = None
    try:
        src_conn = sqlite3.connect(DB_PATH)
        dst_conn = sqlite3.connect(target)
        src_conn.backup(dst_conn)
        check = dst_conn.execute("PRAGMA integrity_check").fetchone()[0]
        if check != "ok":
            raise RuntimeError(f"controllo di integrità fallito: {check}")
    except Exception as e:
        print(f"Errore durante la creazione del backup SQLite: {e}")
        target.unlink(missing_ok=True)
        return False
    finally:
        # Il context manager di sqlite3 non chiude le connessioni
        for conn in (dst_conn, src_conn):
            if conn is not None:
                conn.close()

    os.chmod(target, 0o600)
    print(f"Backup creato e verificato: {target}")

    # Rotazione: i nomi contengono la data, quindi l'ordine alfabetico è quello cronologico
    for old in sorted(BACKUP_DIR.glob("workout_tracker_*.db"))[:-BACKUP_KEEP]:
        old.unlink()
        print(f"Rimosso backup vecchio: {old.name}")
    return True


if __name__ == "__main__":
    # Exit code diverso da zero in caso di errore, così cron/log lo rendono visibile
    sys.exit(0 if run_backup() else 1)
