"""Account: utenti, sessioni, token monouso inviati per email, esportazione ed eliminazione dei dati."""
import hashlib
import sqlite3

from src.auth import new_token
from src.config import SESSION_DAYS
from src.database import get_connection
from src.routines import list_routines


class EmailTaken(Exception):
    """L'email è già registrata."""


_USER_COLS = "id, email, password_hash, email_verified_at, marketing_opt_in, created_at"


def _user_from_row(row) -> dict | None:
    if row is None:
        return None
    return {
        "id": row[0],
        "email": row[1],
        "password_hash": row[2],
        "email_verified": row[3] is not None,
        "marketing_opt_in": bool(row[4]),
        "created_at": row[5],
    }


def public_user(user: dict) -> dict:
    """Il profilo senza dati sensibili (mai l'hash della password), adatto alle risposte API."""
    return {k: user[k] for k in ("id", "email", "email_verified", "marketing_opt_in", "created_at")}


def _hash_token(raw: str) -> str:
    # I token (alta entropia) si salvano solo come SHA-256: un furto del database non li rivela.
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# --- Utenti ------------------------------------------------------------------

def create_user(email: str, password_hash: str, marketing_opt_in: bool = False) -> int:
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                """INSERT INTO users (email, password_hash, marketing_opt_in, marketing_consent_at)
                   VALUES (?, ?, ?, CASE WHEN ? THEN datetime('now') END)""",
                (email, password_hash, int(marketing_opt_in), int(marketing_opt_in))
            )
        except sqlite3.IntegrityError as e:
            raise EmailTaken(email) from e
        return cursor.lastrowid


def get_user(user_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(f"SELECT {_USER_COLS} FROM users WHERE id = ?", (user_id,)).fetchone()
    return _user_from_row(row)


def get_user_by_email(email: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(f"SELECT {_USER_COLS} FROM users WHERE email = ?", (email,)).fetchone()
    return _user_from_row(row)


def mark_email_verified(user_id: int):
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET email_verified_at = COALESCE(email_verified_at, datetime('now')) WHERE id = ?",
            (user_id,)
        )


def set_password_hash(user_id: int, password_hash: str):
    with get_connection() as conn:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))


def set_marketing_opt_in(user_id: int, opt_in: bool):
    """Registra anche il momento del consenso (utile come prova); lo azzera se revocato."""
    with get_connection() as conn:
        conn.execute(
            """UPDATE users SET marketing_opt_in = ?,
                   marketing_consent_at = CASE
                       WHEN ? AND marketing_opt_in = 0 THEN datetime('now')
                       WHEN ? THEN marketing_consent_at
                       END
               WHERE id = ?""",
            (int(opt_in), int(opt_in), int(opt_in), user_id)
        )


def list_newsletter_recipients() -> list[dict]:
    """Solo utenti con email verificata E consenso esplicito a ricevere novità."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT id, email FROM users
               WHERE marketing_opt_in = 1 AND email_verified_at IS NOT NULL
               ORDER BY id"""
        ).fetchall()
    return [{"id": r[0], "email": r[1]} for r in rows]


def count_users() -> int:
    with get_connection() as conn:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


# --- Sessioni ----------------------------------------------------------------

def create_session(user_id: int, days: int = SESSION_DAYS) -> str:
    raw = new_token()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO sessions (user_id, token_hash, expires_at) VALUES (?, ?, datetime('now', ?))",
            (user_id, _hash_token(raw), f"{int(days):+d} days")
        )
    return raw


def get_user_by_session(raw_token: str) -> dict | None:
    token_hash = _hash_token(raw_token)
    with get_connection() as conn:
        row = conn.execute(
            """SELECT u.id, u.email, u.password_hash, u.email_verified_at, u.marketing_opt_in, u.created_at
               FROM sessions s JOIN users u ON u.id = s.user_id
               WHERE s.token_hash = ? AND s.expires_at > datetime('now')""",
            (token_hash,)
        ).fetchone()
        if row is None:
            return None
        # Aggiorna l'ultimo utilizzo al massimo una volta all'ora (evita una scrittura per richiesta)
        conn.execute(
            "UPDATE sessions SET last_used_at = datetime('now') WHERE token_hash = ? AND last_used_at < datetime('now', '-1 hour')",
            (token_hash,)
        )
    return _user_from_row(row)


def delete_session(raw_token: str):
    with get_connection() as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_hash_token(raw_token),))


def delete_user_sessions(user_id: int, keep_raw_token: str | None = None):
    """Chiude tutte le sessioni dell'utente (opzionalmente tranne quella corrente)."""
    keep_hash = _hash_token(keep_raw_token) if keep_raw_token else ""
    with get_connection() as conn:
        conn.execute("DELETE FROM sessions WHERE user_id = ? AND token_hash != ?", (user_id, keep_hash))


def purge_expired():
    """Pulizia di sessioni e token scaduti o già usati."""
    with get_connection() as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at <= datetime('now')")
        conn.execute(
            "DELETE FROM email_tokens WHERE expires_at <= datetime('now') OR used_at < datetime('now', '-1 day')"
        )


# --- Token monouso (verifica email, reset password) --------------------------

def create_email_token(user_id: int, purpose: str, ttl_hours: int) -> str:
    """Nuovo token monouso; invalida quelli precedenti non ancora usati per lo stesso scopo."""
    raw = new_token()
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM email_tokens WHERE user_id = ? AND purpose = ? AND used_at IS NULL",
            (user_id, purpose)
        )
        conn.execute(
            """INSERT INTO email_tokens (user_id, purpose, token_hash, expires_at)
               VALUES (?, ?, ?, datetime('now', ?))""",
            (user_id, purpose, _hash_token(raw), f"{int(ttl_hours):+d} hours")
        )
    return raw


def consume_email_token(raw_token: str, purpose: str) -> int | None:
    """Usa il token (una sola volta). Restituisce lo user_id, o None se non valido, scaduto o già usato."""
    token_hash = _hash_token(raw_token)
    with get_connection() as conn:
        cursor = conn.execute(
            """UPDATE email_tokens SET used_at = datetime('now')
               WHERE token_hash = ? AND purpose = ? AND used_at IS NULL AND expires_at > datetime('now')""",
            (token_hash, purpose)
        )
        if cursor.rowcount != 1:
            return None
        row = conn.execute("SELECT user_id FROM email_tokens WHERE token_hash = ?", (token_hash,)).fetchone()
    return row[0] if row else None


# --- Dati personali ----------------------------------------------------------

def delete_user(user_id: int) -> bool:
    """Elimina l'account e TUTTI i dati collegati (allenamenti, serie, schede, sessioni, token)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM sets WHERE workout_id IN (SELECT id FROM workouts WHERE user_id = ?)", (user_id,)
        )
        cursor.execute("DELETE FROM workouts WHERE user_id = ?", (user_id,))
        cursor.execute(
            "DELETE FROM routine_exercises WHERE routine_id IN (SELECT id FROM routines WHERE user_id = ?)",
            (user_id,)
        )
        cursor.execute("DELETE FROM routines WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM email_tokens WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        return cursor.rowcount > 0


def export_user_data(user_id: int) -> dict:
    """Tutti i dati dell'utente in un formato leggibile (portabilità dei dati)."""
    user = get_user(user_id)
    with get_connection() as conn:
        workouts = []
        for w_id, start, end, split, active in conn.execute(
            "SELECT id, start_time, end_time, split_name, is_active FROM workouts WHERE user_id = ? ORDER BY id",
            (user_id,)
        ).fetchall():
            sets = conn.execute(
                """SELECT exercise_name, set_order, weight, reps, duration_seconds
                   FROM sets WHERE workout_id = ? ORDER BY id""",
                (w_id,)
            ).fetchall()
            workouts.append({
                "start_time": start,
                "end_time": end,
                "routine": split,
                "in_progress": bool(active),
                "sets": [
                    {"exercise": s[0], "order": s[1], "weight_kg": s[2], "reps": s[3], "duration_seconds": s[4]}
                    for s in sets
                ],
            })
    return {
        "account": {
            "email": user["email"],
            "created_at": user["created_at"],
            "email_verified": user["email_verified"],
            "marketing_opt_in": user["marketing_opt_in"],
        },
        "routines": [
            {"name": r["name"], "notes": r["notes"], "exercises": r["exercises"]}
            for r in list_routines(user_id)
        ],
        "workouts": workouts,
    }


def count_legacy_workouts() -> int:
    """Allenamenti della versione a utente singolo non ancora assegnati a nessun account."""
    with get_connection() as conn:
        return conn.execute("SELECT COUNT(*) FROM workouts WHERE user_id IS NULL").fetchone()[0]


def claim_legacy_workouts(user_id: int) -> int:
    """Assegna all'utente gli allenamenti della versione a utente singolo (user_id NULL)."""
    with get_connection() as conn:
        cursor = conn.execute("UPDATE workouts SET user_id = ? WHERE user_id IS NULL", (user_id,))
        return cursor.rowcount
