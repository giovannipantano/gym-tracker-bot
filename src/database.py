import sqlite3
from datetime import datetime
from src.config import DATABASE_PATH

def init_db():
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
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
        
        # Migrazione automatica se la colonna duration_seconds manca nelle installazioni esistenti
        cursor.execute("PRAGMA table_info(sets)")
        cols = [col[1] for col in cursor.fetchall()]
        if "duration_seconds" not in cols:
            cursor.execute("ALTER TABLE sets ADD COLUMN duration_seconds INTEGER")
            
        conn.commit()

def start_new_workout(split_name: str) -> int:
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        # Chiudi eventuali sessioni rimaste appese
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
        now = datetime.now().isoformat()
        cursor.execute(
            "UPDATE workouts SET is_active = 0, end_time = ? WHERE id = ?", 
            (now, workout_id)
        )
        conn.commit()

def log_sets_batch(workout_id: int, exercise: str, entries: list[dict]):
    """
    entries: lista di dizionari, es:
    [
        {"weight": 80.0, "reps": 8, "duration": None},
        {"weight": 0.0, "reps": 12, "duration": None},  # corpo libero
        {"weight": 0.0, "reps": 0, "duration": 60}      # 60 secondi
    ]
    """
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM sets WHERE workout_id = ? AND exercise_name = ?", 
            (workout_id, exercise)
        )
        current_count = cursor.fetchone()[0]
        
        to_insert = [
            (
                workout_id, 
                exercise, 
                current_count + i + 1, 
                e.get("weight", 0.0) or 0.0, 
                e.get("reps", 0) or 0, 
                e.get("duration", None)
            )
            for i, e in enumerate(entries)
        ]
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
    """Elimina tutte le serie dell'ultimo esercizio inserito nella sessione attiva."""
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT exercise_name, MAX(created_at)
            FROM sets
            WHERE workout_id = ?
            GROUP BY exercise_name
            ORDER BY MAX(created_at) DESC
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
    """Elimina una sessione e tutte le sue serie correlate."""
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sets WHERE workout_id = ?", (workout_id,))
        cursor.execute("DELETE FROM workouts WHERE id = ?", (workout_id,))
        conn.commit()
        return cursor.rowcount > 0

def get_exercise_progression(exercise_name: str):
    """Calcola la progressione esatta per l'esercizio selezionato."""
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
                ) as metric_value,
                MAX(s.weight) as max_weight,
                MAX(s.reps) as max_reps,
                MAX(s.duration_seconds) as max_duration
            FROM sets s
            JOIN workouts w ON s.workout_id = w.id
            WHERE LOWER(TRIM(s.exercise_name)) = LOWER(TRIM(?))
            GROUP BY w.id
            ORDER BY w.start_time ASC
        """, (exercise_name.strip(),))
        return cursor.fetchall()

def get_distinct_logged_exercises() -> list[str]:
    """Restituisce la lista ordinata di tutti gli esercizi registrati nel DB."""
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT exercise_name 
            FROM sets 
            WHERE exercise_name IS NOT NULL AND TRIM(exercise_name) != ''
            ORDER BY exercise_name COLLATE NOCASE ASC
        """)
        return [row[0] for row in cursor.fetchall()]