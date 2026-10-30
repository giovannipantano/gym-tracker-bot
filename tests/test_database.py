import sqlite3

from src.catalog import canonical_exercise_name
from src.database import (
    delete_last_exercise_sets,
    delete_workout,
    end_active_workout,
    get_active_workout,
    get_connection,
    get_distinct_logged_exercises,
    get_exercise_progression,
    get_last_exercise_performance,
    get_recent_workouts,
    get_weekly_muscle_volume,
    get_workout_details,
    get_workout_summary,
    init_db,
    log_sets_batch,
    start_new_workout,
)
from src import routines


def test_foreign_keys_enabled_on_every_connection():
    with get_connection() as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_start_closes_dangling_session_with_end_time(make_user):
    uid = make_user()
    first = start_new_workout(uid, "Push")
    second = start_new_workout(uid, "Pull")
    assert get_active_workout(uid)[0] == second
    with get_connection() as conn:
        is_active, end_time = conn.execute("SELECT is_active, end_time FROM workouts WHERE id = ?", (first,)).fetchone()
    assert is_active == 0 and end_time is not None


def test_log_and_read_sets(make_user):
    uid = make_user()
    w = start_new_workout(uid, "Push")
    assert log_sets_batch(uid, w, "Panca", [{"weight": 80, "reps": 8, "duration": None}, {"weight": 80, "reps": 6, "duration": None}])
    _, sets = get_workout_details(uid, w)
    assert [(s[0], s[2], s[3]) for s in sets] == [("Panca", 80, 8), ("Panca", 80, 6)]
    assert get_workout_summary(uid, w)[0][1] == 2


def test_timed_set_is_stored_as_duration(make_user):
    uid = make_user()
    w = start_new_workout(uid, "Core")
    log_sets_batch(uid, w, "Plank", [{"weight": 0, "reps": 0, "duration": 60}])
    _, sets = get_workout_details(uid, w)
    assert sets[0][4] == 60


def test_undo_last_exercise(make_user):
    uid = make_user()
    w = start_new_workout(uid, "Push")
    log_sets_batch(uid, w, "Panca", [{"weight": 80, "reps": 8, "duration": None}])
    log_sets_batch(uid, w, "Dip", [{"weight": 0, "reps": 10, "duration": None}])
    assert delete_last_exercise_sets(uid, w) == ("Dip", 1)
    assert get_distinct_logged_exercises(uid) == ["Panca"]


def test_end_and_history(make_user):
    uid = make_user()
    w = start_new_workout(uid, "Push")
    log_sets_batch(uid, w, "Panca", [{"weight": 100, "reps": 5, "duration": None}])
    assert end_active_workout(uid, w)
    assert get_active_workout(uid) is None
    history = get_recent_workouts(uid)
    assert len(history) == 1 and history[0][5] == 500


def test_last_performance_ignores_active_workout(make_user):
    uid = make_user()
    w1 = start_new_workout(uid, "Push")
    log_sets_batch(uid, w1, "Panca", [{"weight": 70, "reps": 8, "duration": None}])
    end_active_workout(uid, w1)
    w2 = start_new_workout(uid, "Push")
    log_sets_batch(uid, w2, "Panca", [{"weight": 90, "reps": 3, "duration": None}])
    last = get_last_exercise_performance(uid, "panca")
    assert last["sets"][0]["weight"] == 70


def test_progression_one_rep_is_weight(make_user):
    uid = make_user()
    w = start_new_workout(uid, "Push")
    log_sets_batch(uid, w, "Panca", [{"weight": 100, "reps": 1, "duration": None}])
    end_active_workout(uid, w)
    assert round(get_exercise_progression(uid, "Panca")[0][1], 1) == 100.0


def test_delete_workout_removes_sets(make_user):
    uid = make_user()
    w = start_new_workout(uid, "Push")
    log_sets_batch(uid, w, "Panca", [{"weight": 80, "reps": 8, "duration": None}])
    assert delete_workout(uid, w)
    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM sets").fetchone()[0] == 0


def test_exercise_name_canonicalised_against_user_routine(make_user):
    uid = make_user()
    routines.create_routine(uid, "Push", "", [{"name": "Panca Piana", "muscle_group": "Petto", "note": ""}])
    w = start_new_workout(uid, "Push")
    log_sets_batch(uid, w, "  panca piana ", [{"weight": 60, "reps": 10, "duration": None}])
    assert get_distinct_logged_exercises(uid) == ["Panca Piana"]


def test_canonical_name_helper():
    assert canonical_exercise_name("panca", ["Panca", "Squat"]) == "Panca"
    assert canonical_exercise_name("  Nuovo  Esercizio ", []) == "Nuovo Esercizio"


def test_weekly_volume_uses_routine_muscle_group(make_user):
    uid = make_user()
    routines.create_routine(uid, "A", "", [{"name": "Esercizio strano", "muscle_group": "Spalle", "note": ""}])
    w = start_new_workout(uid, "A")
    log_sets_batch(uid, w, "Esercizio strano", [{"weight": 10, "reps": 10, "duration": None}] * 3)
    end_active_workout(uid, w)
    volume = get_weekly_muscle_volume(uid)
    assert volume["Spalle"] == 3
    assert set(volume) >= {"Petto", "Dorso", "Gambe", "Spalle", "Braccia", "Addome", "Altro"}


# --- Isolamento tra utenti --------------------------------------------------------

def test_users_cannot_see_or_touch_each_others_workouts(make_user):
    a, b = make_user(), make_user()
    w = start_new_workout(a, "Push")
    log_sets_batch(a, w, "Panca", [{"weight": 80, "reps": 8, "duration": None}])
    end_active_workout(a, w)

    assert get_recent_workouts(b) == []
    assert get_distinct_logged_exercises(b) == []
    assert get_last_exercise_performance(b, "Panca") is None
    assert get_workout_details(b, w)[1] == []
    assert log_sets_batch(b, w, "Panca", [{"weight": 1, "reps": 1, "duration": None}]) is False
    assert delete_workout(b, w) is False
    assert len(get_recent_workouts(a)) == 1


def test_each_user_has_own_active_workout(make_user):
    a, b = make_user(), make_user()
    start_new_workout(a, "Push")
    assert get_active_workout(b) is None
    start_new_workout(b, "Pull")
    assert get_active_workout(a)[1] == "Push"


# --- Migrazione dal vecchio database a utente singolo ----------------------------

def test_migration_from_old_schema(tmp_path, monkeypatch, make_user):
    from src import config, users

    old = tmp_path / "old.db"
    conn = sqlite3.connect(old)
    conn.executescript("""
        CREATE TABLE workouts (id INTEGER PRIMARY KEY AUTOINCREMENT, start_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            end_time DATETIME, split_name TEXT, is_active INTEGER DEFAULT 1);
        CREATE TABLE sets (id INTEGER PRIMARY KEY AUTOINCREMENT, workout_id INTEGER, exercise_name TEXT,
            set_order INTEGER, weight REAL, reps INTEGER, FOREIGN KEY (workout_id) REFERENCES workouts(id));
        INSERT INTO workouts (split_name, is_active, end_time) VALUES ('Push', 0, '2024-01-01 10:00:00');
        INSERT INTO sets (workout_id, exercise_name, set_order, weight, reps) VALUES (1, 'Panca', 1, 80, 8);
    """)
    conn.commit()
    conn.close()

    monkeypatch.setattr(config, "DATABASE_PATH", str(old))
    monkeypatch.setattr("src.database.DATABASE_PATH", str(old), raising=False)
    init_db()

    uid = make_user()
    assert get_recent_workouts(uid) == []          # invisibile finché non viene assegnato
    assert users.count_legacy_workouts() == 1
    assert users.claim_legacy_workouts(uid) == 1
    assert len(get_recent_workouts(uid)) == 1
    assert get_workout_details(uid, 1)[1][0][0] == "Panca"
