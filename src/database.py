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

def get_exercise_history(exercise_name: str):
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT w.start_time, s.weight, s.reps
            FROM sets s
            JOIN workouts w ON s.workout_id = w.id
            WHERE LOWER(s.exercise_name) = LOWER(?)
            ORDER BY w.start_time ASC
        """, (exercise_name,))
        return cursor.fetchall()