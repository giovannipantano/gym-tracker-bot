import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _require(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        sys.exit(f"ERRORE: {name} mancante nel file .env")
    return value


def _bool(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "si", "sì", "on"}


def _int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        sys.exit(f"ERRORE: {name} deve essere un numero intero")


# --- Sicurezza -------------------------------------------------------------
# Chiave segreta per firmare i link di disiscrizione. Nessun default: va generata
# con  python3 -c "import secrets; print(secrets.token_urlsafe(48))"
SECRET_KEY = _require("SECRET_KEY")
if len(SECRET_KEY) < 32:
    sys.exit("ERRORE: SECRET_KEY troppo corta (servono almeno 32 caratteri)")

# Se impostato, chi si registra deve inserire questo codice (utile per famiglia e amici).
REGISTRATION_INVITE_CODE = (os.getenv("REGISTRATION_INVITE_CODE") or "").strip()
# Se True, non si può accedere finché l'email non è verificata (richiede SMTP funzionante).
REQUIRE_EMAIL_VERIFICATION = _bool("REQUIRE_EMAIL_VERIFICATION", False)
SESSION_DAYS = _int("SESSION_DAYS", 30)

# --- Indirizzi e database --------------------------------------------------
# URL pubblico dell'app: usato nei link delle email (verifica, reset, disiscrizione).
BASE_URL = (os.getenv("BASE_URL") or "http://127.0.0.1:8000").strip().rstrip("/")

# Un percorso relativo viene risolto rispetto alla radice del progetto, non alla cwd.
_db_path = Path(os.getenv("DATABASE_PATH", "workout_tracker.db"))
DATABASE_PATH = str(_db_path if _db_path.is_absolute() else PROJECT_ROOT / _db_path)

# --- Invio email (SMTP) ----------------------------------------------------
SMTP_HOST = (os.getenv("SMTP_HOST") or "").strip()
SMTP_PORT = _int("SMTP_PORT", 587)
SMTP_USER = (os.getenv("SMTP_USER") or "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD") or ""
SMTP_STARTTLS = _bool("SMTP_STARTTLS", True)
SMTP_FROM = (os.getenv("SMTP_FROM") or SMTP_USER).strip()
SMTP_ENABLED = bool(SMTP_HOST and SMTP_FROM)

if REQUIRE_EMAIL_VERIFICATION and not SMTP_ENABLED:
    sys.exit("ERRORE: REQUIRE_EMAIL_VERIFICATION richiede SMTP_HOST e SMTP_FROM configurati")
if not SMTP_ENABLED:
    logging.warning("SMTP non configurato: le email (verifica, reset password, novità) NON verranno inviate.")
