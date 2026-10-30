import os
import tempfile
from pathlib import Path

import pytest

# Le variabili vanno impostate PRIMA che src.config venga importato.
# DATABASE_PATH punta a una cartella temporanea: i test non toccano mai il database reale.
_TMP_DIR = tempfile.mkdtemp(prefix="gym_tests_")
os.environ["SECRET_KEY"] = "test-secret-key-0123456789-abcdefghijklmnop"
os.environ["DATABASE_PATH"] = str(Path(_TMP_DIR) / "test.db")
os.environ["BASE_URL"] = "https://gym.example.test"
# Valori vuoti ma presenti: load_dotenv non sovrascrive, quindi un .env reale non influenza i test.
for _name in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "REGISTRATION_INVITE_CODE", "REQUIRE_EMAIL_VERIFICATION"):
    os.environ[_name] = ""


@pytest.fixture(autouse=True)
def fresh_db():
    """Database vuoto prima di ogni test."""
    db = Path(os.environ["DATABASE_PATH"])
    for suffix in ("", "-wal", "-shm"):
        Path(f"{db}{suffix}").unlink(missing_ok=True)

    from src.database import init_db

    init_db()
    yield


@pytest.fixture
def make_user():
    """Crea un utente direttamente nel database e ne restituisce l'id."""
    from src import users
    from src.auth import hash_password

    counter = {"n": 0}

    def _make(email=None, password="password-lunga-1", marketing=False, verified=False):
        counter["n"] += 1
        email = email or f"utente{counter['n']}@example.com"
        user_id = users.create_user(email, hash_password(password), marketing)
        if verified:
            users.mark_email_verified(user_id)
        return user_id

    return _make
