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
                weight REAL NOT NULL,
                reps INTEGER NOT NULL,
                rpe REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
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

def log_sets_batch(workout_id: int, exercise: str, entries: list[tuple[float, int]]):
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        # Ricava l'indice progressivo della serie per quell'esercizio
        cursor.execute(
            "SELECT COUNT(*) FROM sets WHERE workout_id = ? AND exercise_name = ?", 
            (workout_id, exercise)
        )
        current_count = cursor.fetchone()[0]
        
        to_insert = [
            (workout_id, exercise, current_count + i + 1, weight, reps)
            for i, (weight, reps) in enumerate(entries)
        ]
        cursor.executemany(
            "INSERT INTO sets (workout_id, exercise_name, set_order, weight, reps) VALUES (?, ?, ?, ?, ?)",
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
            SELECT exercise_name, set_order, weight, reps
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