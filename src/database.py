import sqlite3
from datetime import datetime
from src.config import DATABASE_PATH
from src.catalog import WORKOUT_ROUTINES


def init_db():
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workouts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        
        # Migrazione automatica se la colonna duration_seconds manca
        cursor.execute("PRAGMA table_info(sets)")
        cols = [col[1] for col in cursor.fetchall()]
        if "duration_seconds" not in cols:
            cursor.execute("ALTER TABLE sets ADD COLUMN duration_seconds INTEGER")
            
        conn.commit()


def start_new_workout(split_name: str) -> int:
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        # Chiudi eventuali sessioni rimaste aperte
        cursor.execute("UPDATE workouts SET is_active = 0 WHERE is_active = 1")
        cursor.execute(
            "INSERT INTO workouts (split_name, is_active) VALUES (?, 1)", 
            (split_name,)
        )
        conn.commit()
        return cursor.lastrowid


def get_active_workout():
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, split_name, start_time FROM workouts WHERE is_active = 1")
        return cursor.fetchone()


def end_active_workout(workout_id: int):
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        # Usa lo stesso formato stringa di CURRENT_TIMESTAMP
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "UPDATE workouts SET is_active = 0, end_time = ? WHERE id = ?", 
            (now, workout_id)
        )
        conn.commit()


def log_sets_batch(workout_id: int, exercise: str, entries: list):
    """
    Supporta sia dizionari (PWA) che tuple (Telegram):
    - Dict: {"weight": 80.0, "reps": 8, "duration": None}
    - Tuple: (80.0, 8) oppure (0.0, 60)
    """
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM sets WHERE workout_id = ? AND exercise_name = ?", 
            (workout_id, exercise)
        )
        current_count = cursor.fetchone()[0]
        
        to_insert = []
        for i, e in enumerate(entries):
            if isinstance(e, dict):
                w = e.get("weight", 0.0) or 0.0
                r = e.get("reps", 0) or 0
                d = e.get("duration", None)
            elif isinstance(e, (list, tuple)):
                w = float(e[0]) if len(e) > 0 and e[0] is not None else 0.0
                r = int(e[1]) if len(e) > 1 and e[1] is not None else 0
                d = int(e[2]) if len(e) > 2 else None
            else:
                continue

            to_insert.append((workout_id, exercise, current_count + i + 1, w, r, d))

        cursor.executemany(
            """INSERT INTO sets (workout_id, exercise_name, set_order, weight, reps, duration_seconds) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            to_insert
        )
        conn.commit()


def get_workout_summary(workout_id: int):
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT exercise_name, COUNT(*), SUM(weight * reps), MAX(weight)
            FROM sets
            WHERE workout_id = ?
            GROUP BY exercise_name
        """, (workout_id,))
        return cursor.fetchall()


def get_exercise_history(exercise_query: str):
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        search_term = f"%{exercise_query.strip().lower()}%"
        cursor.execute("""
            SELECT w.start_time, s.weight, s.reps, s.exercise_name
            FROM sets s
            JOIN workouts w ON s.workout_id = w.id
            WHERE LOWER(s.exercise_name) LIKE ?
            ORDER BY w.start_time ASC
        """, (search_term,))
        return cursor.fetchall()


def get_recent_workouts(limit: int = 10):
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT w.id, w.start_time, w.split_name, 
                   COUNT(DISTINCT s.exercise_name) as num_exercises,
                   COUNT(s.id) as total_sets,
                   COALESCE(SUM(s.weight * s.reps), 0) as total_volume
            FROM workouts w
            LEFT JOIN sets s ON w.id = s.workout_id
            WHERE w.is_active = 0
            GROUP BY w.id
            ORDER BY w.start_time DESC
            LIMIT ?
        """, (limit,))
        return cursor.fetchall()


def get_workout_details(workout_id: int):
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT split_name, start_time, end_time FROM workouts WHERE id = ?", (workout_id,))
        meta = cursor.fetchone()
        if not meta:
            return None, []
        
        cursor.execute("""
            SELECT exercise_name, set_order, weight, reps, duration_seconds
            FROM sets
            WHERE workout_id = ?
            ORDER BY exercise_name, set_order ASC
        """, (workout_id,))
        sets_data = cursor.fetchall()
        return meta, sets_data


def delete_last_exercise_sets(workout_id: int) -> tuple[str, int] | None:
    """Elimina in modo deterministico tutte le serie dell'ultimo esercizio inserito."""
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        # Seleziona l'ultimo esercizio in base all'ID autoincrementale (evita problemi di granularità timestamp)
        cursor.execute("""
            SELECT exercise_name 
            FROM sets 
            WHERE workout_id = ? 
            ORDER BY id DESC 
            LIMIT 1
        """, (workout_id,))
        row = cursor.fetchone()
        if not row:
            return None
        
        last_ex = row[0]
        cursor.execute("DELETE FROM sets WHERE workout_id = ? AND exercise_name = ?", (workout_id, last_ex))
        deleted_count = cursor.rowcount
        conn.commit()
        return last_ex, deleted_count


def delete_workout(workout_id: int) -> bool:
    """Elimina una sessione e tutte le relative serie collegate."""
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sets WHERE workout_id = ?", (workout_id,))
        cursor.execute("DELETE FROM workouts WHERE id = ?", (workout_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_exercise_progression(exercise_name: str):
    """Restituisce data, 1RM stimato, volume totale e peso massimo sollevato."""
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                w.start_time,
                MAX(
                    CASE 
                        WHEN s.duration_seconds IS NOT NULL THEN s.duration_seconds
                        WHEN s.weight > 0 THEN ROUND(s.weight * (1.0 + s.reps / 30.0), 1)
                        ELSE s.reps
                    END
                ) as max_1rm,
                ROUND(SUM(s.weight * s.reps), 1) as total_volume,
                MAX(s.weight) as max_weight
            FROM sets s
            JOIN workouts w ON s.workout_id = w.id
            WHERE LOWER(TRIM(s.exercise_name)) = LOWER(TRIM(?))
            GROUP BY w.id
            ORDER BY w.start_time ASC
        """, (exercise_name.strip(),))
        return cursor.fetchall()

def get_weekly_muscle_volume(exercise_map: dict) -> dict[str, int]:
    """Conta il numero di serie completate negli ultimi 7 giorni per distretto muscolare."""
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.exercise_name, COUNT(s.id)
            FROM sets s
            JOIN workouts w ON s.workout_id = w.id
            WHERE w.start_time >= datetime('now', '-7 days')
              AND w.is_active = 0
            GROUP BY s.exercise_name
        """)
        rows = cursor.fetchall()
        
        summary = {"Petto": 0, "Dorso": 0, "Gambe": 0, "Spalle": 0, "Braccia": 0, "Addome": 0}
        for ex_name, count in rows:
            matched = "Altro"
            name_lower = ex_name.strip().lower()
            for pattern, group in exercise_map.items():
                if pattern in name_lower:
                    matched = group
                    break
            summary[matched] = summary.get(matched, 0) + count
        return summary


def get_distinct_logged_exercises() -> list[str]:
    """Restituisce tutti gli esercizi (da schede predefinite + registrati nel DB)."""
    exercises = set()
    
    # 1. Carica gli esercizi dal catalogo schede
    for split_data in WORKOUT_ROUTINES.values():
        for ex in split_data.get("exercises", []):
            exercises.add(ex.strip())
            
    # 2. Carica gli esercizi registrati a DB
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT exercise_name 
            FROM sets 
            WHERE exercise_name IS NOT NULL AND TRIM(exercise_name) != ''
        """)
        for row in cursor.fetchall():
            exercises.add(row[0].strip())
            
    return sorted(list(exercises), key=str.casefold)

def get_last_exercise_performance(exercise_name: str) -> dict | None:
    """Restituisce le serie dell'ultimo workout completato in cui è presente questo esercizio."""
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        # Trova l'ultimo workout terminato (is_active = 0) contenente l'esercizio
        cursor.execute("""
            SELECT s.workout_id, w.start_time
            FROM sets s
            JOIN workouts w ON s.workout_id = w.id
            WHERE LOWER(TRIM(s.exercise_name)) = LOWER(TRIM(?))
              AND w.is_active = 0
            ORDER BY w.start_time DESC, s.id DESC
            LIMIT 1
        """, (exercise_name.strip(),))
        row = cursor.fetchone()
        if not row:
            return None
        
        last_w_id, start_time = row
        cursor.execute("""
            SELECT weight, reps, duration_seconds
            FROM sets
            WHERE workout_id = ? AND LOWER(TRIM(exercise_name)) = LOWER(TRIM(?))
            ORDER BY set_order ASC
        """, (last_w_id, exercise_name.strip()))
        sets_data = cursor.fetchall()
        
        return {
            "date": start_time[:10],
            "sets": [{"weight": s[0], "reps": s[1], "duration": s[2]} for s in sets_data]
        }