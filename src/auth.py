"""Primitive di autenticazione: hash delle password, token, rate limiting, link di disiscrizione firmati."""
import base64
import hashlib
import hmac
import os
import re
import secrets
import threading
import time
from collections import defaultdict, deque

from src.config import BASE_URL, SECRET_KEY

# --- Password ------------------------------------------------------------------
# scrypt è nella libreria standard (nessuna dipendenza extra) ed è resistente agli attacchi con GPU.
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P, _DKLEN = 2 ** 14, 8, 1, 32
_SCRYPT_MAXMEM = 64 * 1024 * 1024

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128  # evita che password enormi diventino un attacco di tipo DoS


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P,
        dklen=_DKLEN, maxmem=_SCRYPT_MAXMEM,
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest_b64)
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=base64.b64decode(salt_b64), n=int(n), r=int(r), p=int(p),
            dklen=len(expected), maxmem=_SCRYPT_MAXMEM,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# Hash di una password casuale: serve a impiegare lo stesso tempo anche quando l'email non esiste,
# così il tempo di risposta del login non rivela quali email sono registrate.
DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(16))

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(raw: str) -> str | None:
    """Email in minuscolo e senza spazi, oppure None se non plausibile."""
    email = (raw or "").strip().lower()
    if len(email) > 254 or not _EMAIL_RE.match(email):
        return None
    return email


def validate_password(password: str, email: str = "") -> str | None:
    """Messaggio di errore (in italiano) oppure None se la password è accettabile."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"La password deve avere almeno {MIN_PASSWORD_LENGTH} caratteri"
    if len(password) > MAX_PASSWORD_LENGTH:
        return f"La password può avere al massimo {MAX_PASSWORD_LENGTH} caratteri"
    if email and password.strip().lower() == email.lower():
        return "La password non può coincidere con l'email"
    return None


# --- Token -----------------------------------------------------------------------

def new_token() -> str:
    return secrets.token_urlsafe(32)


def _signature(purpose: str, user_id: int) -> str:
    message = f"{purpose}:{user_id}".encode("utf-8")
    return hmac.new(SECRET_KEY.encode("utf-8"), message, hashlib.sha256).hexdigest()


def unsubscribe_signature(user_id: int) -> str:
    return _signature("unsubscribe", user_id)


def verify_unsubscribe_signature(user_id: int, signature: str) -> bool:
    return hmac.compare_digest(unsubscribe_signature(user_id), signature or "")


def unsubscribe_url(user_id: int) -> str:
    """Link permanente (non scade) per disiscriversi dalle email di novità, senza bisogno di accedere."""
    return f"{BASE_URL}/unsubscribe?u={user_id}&t={unsubscribe_signature(user_id)}"


# --- Rate limiting -----------------------------------------------------------------

class RateLimiter:
    """
    Limite a finestra scorrevole, in memoria (il server gira in un solo processo).
    `blocked(key)` dice quanti secondi attendere (0 = via libera); `add(key)` registra un tentativo.
    """

    def __init__(self, max_attempts: int, window_seconds: int):
        self.max_attempts = max_attempts
        self.window = window_seconds
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque:
        hits = self._hits[key]
        while hits and now - hits[0] > self.window:
            hits.popleft()
        if not hits:
            self._hits.pop(key, None)
            return deque()
        return hits

    def blocked(self, key: str) -> int:
        now = time.monotonic()
        with self._lock:
            hits = self._prune(key, now)
            if len(hits) < self.max_attempts:
                return 0
            return max(1, int(self.window - (now - hits[0])))

    def add(self, key: str):
        now = time.monotonic()
        with self._lock:
            self._prune(key, now)
            self._hits[key].append(now)

    def clear(self, key: str):
        with self._lock:
            self._hits.pop(key, None)

    def reset_all(self):
        with self._lock:
            self._hits.clear()
