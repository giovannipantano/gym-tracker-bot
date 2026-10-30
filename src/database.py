import sqlite3
from contextlib import contextmanager

from src.config import DATABASE_PATH
from src.catalog import MUSCLE_GROUPS, canonical_exercise_name, guess_muscle_group


@contextmanager
def get_connection():
    """
    Connessione SQLite con commit/rollback automatici e chiusura garantita.

    Il context manager nativo di sqlite3 non chiude la connessione, e
    `PRAGMA foreign_keys` vale per singola connessione: va quindi impostato qui,
    non solo in init_db(), altrimenti ON DELETE CASCADE non scatta mai.
    """
    conn = sqlite3.connect(DATABASE_PATH, timeout=10)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Crea lo schema e aggiorna in modo non distruttivo un database della versione precedente."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode = WAL;")

        # --- Account ---------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                email_verified_at TIMESTAMP,
                marketing_opt_in INTEGER NOT NULL DEFAULT 0,
                marketing_consent_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token_hash TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS email_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                purpose TEXT NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                expires_at TIMESTAMP NOT NULL,
                used_at TIMESTAMP
            );
        """)

        # --- Schede di allenamento (una per utente, modificabili) -------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS routines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL COLLATE NOCASE,
                notes TEXT NOT NULL DEFAULT '',
                position INTEGER NOT NULL DEFAULT 0,
                UNIQUE (user_id, name)
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS routine_exercises (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                routine_id INTEGER NOT NULL REFERENCES routines(id) ON DELETE CASCADE,
                position INTEGER NOT NULL,
                exercise_name TEXT NOT NULL,
                muscle_group TEXT NOT NULL DEFAULT 'Altro',
                note TEXT NOT NULL DEFAULT ''
            );
        """)

        # --- Allenamenti -----------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workouts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                routine_id INTEGER REFERENCES routines(id) ON DELETE SET NULL,
                start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                end_time TIMESTAMP,
                split_name TEXT NOT NULL,
                is_active INTEGER DEFAULT 1
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workout_id INTEGER REFERENCES workouts(id) ON DELETE CASCADE,
                exercise_name TEXT NOT NULL,
                set_order INTEGER NOT NULL,
                weight REAL DEFAULT 0.0,
                reps INTEGER DEFAULT 0,
                duration_seconds INTEGER,
                rpe REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Migrazioni automatiche per database creati dalle versioni precedenti.
        # Le righe esistenti restano con user_id NULL (invisibili a tutti) finché non vengono
        # assegnate a un account con scripts/claim_legacy_data.py.
        cursor.execute("PRAGMA table_info(sets)")
        if "duration_seconds" not in [col[1] for col in cursor.fetchall()]:
            cursor.execute("ALTER TABLE sets ADD COLUMN duration_seconds INTEGER")

        cursor.execute("PRAGMA table_info(workouts)")
        workout_cols = [col[1] for col in cursor.fetchall()]
        if "user_id" not in workout_cols:
            cursor.execute("ALTER TABLE workouts ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE CASCADE")
        if "routine_id" not in workout_cols:
            cursor.execute("ALTER TABLE workouts ADD COLUMN routine_id INTEGER REFERENCES routines(id) ON DELETE SET NULL")

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_workouts_user ON workouts(user_id, is_active, start_time)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sets_workout_id ON sets(workout_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_email_tokens_user ON email_tokens(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_routines_user ON routines(user_id, position)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_routine_exercises_routine ON routine_exercises(routine_id, position)")


# ---------------------------------------------------------------------------
# Allenamenti. OGNI funzione riceve user_id e filtra per esso: un utente non deve
# mai poter leggere o modificare i dati di un altro, nemmeno conoscendo un workout_id.
# ---------------------------------------------------------------------------

def _owns_workout(cursor, user_id: int, workout_id: int) -> bool:
    cursor.execute("SELECT 1 FROM workouts WHERE id = ? AND user_id = ?", (workout_id, user_id))
    return cursor.fetchone() is not None


def start_new_workout(user_id: int, split_name: str, routine_id: int | None = None) -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        # Chiudi eventuali sessioni rimaste aperte (registrando anche l'orario di fine)
        cursor.execute(
            "UPDATE workouts SET is_active = 0, end_time = CURRENT_TIMESTAMP WHERE user_id = ? AND is_active = 1",
            (user_id,)
        )
        cursor.execute(
            "INSERT INTO workouts (user_id, split_name, routine_id, is_active) VALUES (?, ?, ?, 1)",
            (user_id, split_name, routine_id)
        )
        return cursor.lastrowid


def get_active_workout(user_id: int):
    """(id, split_name, start_time, routine_id) della sessione attiva, o None."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT id, split_name, start_time, routine_id FROM workouts
               WHERE user_id = ? AND is_active = 1 ORDER BY id DESC LIMIT 1""",
            (user_id,)
        )
        return cursor.fetchone()


def end_active_workout(user_id: int, workout_id: int) -> bool:
    with get_connection() as conn:
        # CURRENT_TIMESTAMP (UTC) come start_time: usare l'ora locale falserebbe la durata
        cursor = conn.execute(
            "UPDATE workouts SET is_active = 0, end_time = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?",
            (workout_id, user_id)
        )
        return cursor.rowcount > 0


def _user_exercise_names(cursor, user_id: int) -> list[str]:
    cursor.execute("""
        SELECT re.exercise_name
        FROM routine_exercises re
        JOIN routines r ON r.id = re.routine_id
        WHERE r.user_id = ?
    """, (user_id,))
    return [row[0] for row in cursor.fetchall()]


def log_sets_batch(user_id: int, workout_id: int, exercise: str, entries: list) -> bool:
    """
    Registra le serie in un workout dell'utente. False se il workout non è suo.

    Ogni entry è un dizionario {"weight", "reps", "duration"} oppure una tupla
    (peso, reps) / (peso, reps, durata_in_secondi).
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        if not _owns_workout(cursor, user_id, workout_id):
            return False

        # Stessa ortografia degli esercizi nelle schede dell'utente ("panca" -> "Panca")
        exercise = canonical_exercise_name(exercise, _user_exercise_names(cursor, user_id))

        cursor.execute(
            "SELECT COUNT(*) FROM sets WHERE workout_id = ? AND LOWER(TRIM(exercise_name)) = LOWER(?)",
            (workout_id, exercise)
        )
        current_count = cursor.fetchone()[0]

        to_insert = []
        for e in entries:
            if isinstance(e, dict):
                w = e.get("weight", 0.0) or 0.0
                r = e.get("reps", 0) or 0
                d = e.get("duration", None)
            elif isinstance(e, (list, tuple)):
                w = float(e[0]) if len(e) > 0 and e[0] is not None else 0.0
                r = int(e[1]) if len(e) > 1 and e[1] is not None else 0
                d = int(e[2]) if len(e) > 2 and e[2] is not None else None
            else:
                continue

            current_count += 1
            to_insert.append((workout_id, exercise, current_count, w, r, d))

        cursor.executemany(
            """INSERT INTO sets (workout_id, exercise_name, set_order, weight, reps, duration_seconds)
               VALUES (?, ?, ?, ?, ?, ?)""",
            to_insert
        )
        return True


def get_workout_summary(user_id: int, workout_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        # Raggruppa senza distinguere maiuscole/minuscole, nell'ordine di inserimento
        cursor.execute("""
            SELECT MIN(s.exercise_name), COUNT(*), SUM(s.weight * s.reps), MAX(s.weight)
            FROM sets s
            JOIN workouts w ON w.id = s.workout_id
            WHERE s.workout_id = ? AND w.user_id = ?
            GROUP BY LOWER(TRIM(s.exercise_name))
            ORDER BY MIN(s.id)
        """, (workout_id, user_id))
        return cursor.fetchall()


def get_recent_workouts(user_id: int, limit: int = 10):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT w.id, w.start_time, w.split_name,
                   COUNT(DISTINCT LOWER(TRIM(s.exercise_name))) as num_exercises,
                   COUNT(s.id) as total_sets,
                   COALESCE(SUM(s.weight * s.reps), 0) as total_volume
            FROM workouts w
            LEFT JOIN sets s ON w.id = s.workout_id
            WHERE w.user_id = ? AND w.is_active = 0
            GROUP BY w.id
            ORDER BY w.start_time DESC
            LIMIT ?
        """, (user_id, limit))
        return cursor.fetchall()


def get_workout_details(user_id: int, workout_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT split_name, start_time, end_time FROM workouts WHERE id = ? AND user_id = ?",
            (workout_id, user_id)
        )
        meta = cursor.fetchone()
        if not meta:
            return None, []

        # In ordine cronologico: gli esercizi compaiono nell'ordine in cui sono stati eseguiti
        cursor.execute("""
            SELECT exercise_name, set_order, weight, reps, duration_seconds
            FROM sets
            WHERE workout_id = ?
            ORDER BY id ASC
        """, (workout_id,))
        return meta, cursor.fetchall()


def delete_last_exercise_sets(user_id: int, workout_id: int) -> tuple[str, int] | None:
    """Elimina in modo deterministico tutte le serie dell'ultimo esercizio inserito."""
    with get_connection() as conn:
        cursor = conn.cursor()
        if not _owns_workout(cursor, user_id, workout_id):
            return None
        # Seleziona l'ultimo esercizio in base all'ID autoincrementale (evita problemi di granularità timestamp)
        cursor.execute(
            "SELECT exercise_name FROM sets WHERE workout_id = ? ORDER BY id DESC LIMIT 1",
            (workout_id,)
        )
        row = cursor.fetchone()
        if not row:
            return None

        last_ex = row[0]
        cursor.execute(
            "DELETE FROM sets WHERE workout_id = ? AND LOWER(TRIM(exercise_name)) = LOWER(TRIM(?))",
            (workout_id, last_ex)
        )
        return last_ex, cursor.rowcount


def delete_workout(user_id: int, workout_id: int) -> bool:
    """Elimina una sessione dell'utente e tutte le relative serie."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM sets WHERE workout_id IN (SELECT id FROM workouts WHERE id = ? AND user_id = ?)",
            (workout_id, user_id)
        )
        cursor.execute("DELETE FROM workouts WHERE id = ? AND user_id = ?", (workout_id, user_id))
        return cursor.rowcount > 0


def get_exercise_progression(user_id: int, exercise_name: str):
    """Restituisce data, 1RM stimato, volume totale e peso massimo sollevato."""
    with get_connection() as conn:
        cursor = conn.cursor()
        # Epley: a 1 ripetizione il massimale stimato coincide con il carico sollevato
        cursor.execute("""
            SELECT
                w.start_time,
                MAX(
                    CASE
                        WHEN s.duration_seconds IS NOT NULL THEN s.duration_seconds
                        WHEN s.weight > 0 AND s.reps <= 1 THEN s.weight
                        WHEN s.weight > 0 THEN ROUND(s.weight * (1.0 + s.reps / 30.0), 1)
                        ELSE s.reps
                    END
                ) as max_1rm,
                ROUND(SUM(s.weight * s.reps), 1) as total_volume,
                MAX(s.weight) as max_weight
            FROM sets s
            JOIN workouts w ON s.workout_id = w.id
            WHERE w.user_id = ? AND LOWER(TRIM(s.exercise_name)) = LOWER(TRIM(?))
            GROUP BY w.id
            ORDER BY w.start_time ASC
        """, (user_id, exercise_name.strip()))
        return cursor.fetchall()


def get_weekly_muscle_volume(user_id: int) -> dict[str, int]:
    """
    Serie completate negli ultimi 7 giorni per gruppo muscolare. Usa il gruppo scelto dall'utente
    nelle proprie schede; per gli esercizi liberi ricade sul riconoscimento dal nome.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.exercise_name, COUNT(s.id)
            FROM sets s
            JOIN workouts w ON s.workout_id = w.id
            WHERE w.user_id = ?
              AND w.start_time >= datetime('now', '-7 days')
              AND w.is_active = 0
            GROUP BY s.exercise_name
        """, (user_id,))
        rows = cursor.fetchall()

        cursor.execute("""
            SELECT re.exercise_name, re.muscle_group
            FROM routine_exercises re
            JOIN routines r ON r.id = re.routine_id
            WHERE r.user_id = ?
        """, (user_id,))
        own_groups = {name.strip().casefold(): group for name, group in cursor.fetchall()}

    summary = {group: 0 for group in MUSCLE_GROUPS}
    for ex_name, count in rows:
        group = own_groups.get(ex_name.strip().casefold()) or guess_muscle_group(ex_name)
        if group not in summary:
            group = "Altro"
        summary[group] += count
    return summary


def get_distinct_logged_exercises(user_id: int) -> list[str]:
    """Esercizi delle schede dell'utente + quelli registrati, senza doppioni per maiuscole."""
    exercises: dict[str, str] = {}

    with get_connection() as conn:
        cursor = conn.cursor()
        # 1. Esercizi delle schede (hanno la precedenza come ortografia)
        for name in _user_exercise_names(cursor, user_id):
            exercises.setdefault(name.strip().casefold(), name.strip())

        # 2. Esercizi registrati
        cursor.execute("""
            SELECT DISTINCT s.exercise_name
            FROM sets s
            JOIN workouts w ON w.id = s.workout_id
            WHERE w.user_id = ? AND s.exercise_name IS NOT NULL AND TRIM(s.exercise_name) != ''
        """, (user_id,))
        for (name,) in cursor.fetchall():
            exercises.setdefault(name.strip().casefold(), name.strip())

    return sorted(exercises.values(), key=str.casefold)


def get_last_exercise_performance(user_id: int, exercise_name: str) -> dict | None:
    """Serie dell'ultimo workout completato dell'utente in cui è presente questo esercizio."""
    with get_connection() as conn:
        cursor = conn.cursor()
        # Trova l'ultimo workout terminato (is_active = 0) contenente l'esercizio
        cursor.execute("""
            SELECT s.workout_id, w.start_time
            FROM sets s
            JOIN workouts w ON s.workout_id = w.id
            WHERE w.user_id = ?
              AND LOWER(TRIM(s.exercise_name)) = LOWER(TRIM(?))
              AND w.is_active = 0
            ORDER BY w.start_time DESC, s.id DESC
            LIMIT 1
        """, (user_id, exercise_name.strip()))
        row = cursor.fetchone()
        if not row:
            return None

        last_w_id, start_time = row
        cursor.execute("""
            SELECT weight, reps, duration_seconds
            FROM sets
            WHERE workout_id = ? AND LOWER(TRIM(exercise_name)) = LOWER(TRIM(?))
            ORDER BY id ASC
        """, (last_w_id, exercise_name.strip()))
        sets_data = cursor.fetchall()

        return {
            "date": start_time[:10],
            "sets": [{"weight": s[0], "reps": s[1], "duration": s[2]} for s in sets_data]
        }
