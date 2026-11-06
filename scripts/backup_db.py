"""
Backup a caldo del database SQLite, con copie locali a rotazione.

Le copie restano sul server (cartella BACKUP_DIR, di default "backups/"): proteggono da errori e
corruzioni, ma NON dalla perdita del server. Per quello, se nel .env c'è BACKUP_REMOTE (una destinazione
di rclone, es. "gdrive-crypt:gym-backups"), ogni nuova copia viene caricata anche lì e le copie remote
più vecchie di BACKUP_REMOTE_KEEP_DAYS giorni vengono eliminate. Vedi README.

Codici di uscita: 0 tutto ok; 1 backup locale fallito; 2 backup locale ok ma copia remota fallita.
"""
import os
import shutil
import sqlite3
import subprocess
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


BACKUP_REMOTE = (os.getenv("BACKUP_REMOTE") or "").strip()
try:
    REMOTE_KEEP_DAYS = max(1, int(os.getenv("BACKUP_REMOTE_KEEP_DAYS", "30")))
except ValueError:
    REMOTE_KEEP_DAYS = 30


def upload_offsite(target: Path, remote: str = "") -> bool:
    """Carica la copia su un archivio esterno con rclone e ripulisce le copie remote vecchie."""
    remote = remote or BACKUP_REMOTE
    if not remote:
        return True
    rclone = shutil.which("rclone")
    if not rclone:
        print("Errore: BACKUP_REMOTE è impostato ma rclone non è installato (sudo apt install rclone)")
        return False
    try:
        subprocess.run([rclone, "copy", str(target), remote], check=True, timeout=1800)
        subprocess.run(
            [rclone, "delete", remote, "--min-age", f"{REMOTE_KEEP_DAYS}d", "--include", "workout_tracker_*.db"],
            check=True, timeout=600,
        )
    except (subprocess.SubprocessError, OSError) as e:
        print(f"Errore nella copia remota verso {remote}: {e}")
        return False
    print(f"Copia remota completata: {remote}")
    return True


def run_backup() -> Path | None:
    """Crea una copia verificata e ruota le vecchie. Restituisce il file creato, None se fallisce."""
    if not DB_PATH.exists():
        print(f"Errore: File di database non trovato in {DB_PATH}")
        return None

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
        return None
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
    return target


if __name__ == "__main__":
    # Exit code diverso da zero in caso di errore, così cron/log lo rendono visibile
    created = run_backup()
    if created is None:
        sys.exit(1)
    sys.exit(0 if upload_offsite(created) else 2)
