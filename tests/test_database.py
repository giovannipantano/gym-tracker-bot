import sqlite3

from src.catalog import canonical_exercise_name
from src.database import (
    delete_last_exercise_sets,
    delete_set,
    delete_workout,
    end_active_workout,
    get_active_workout,
    get_connection,
    get_distinct_logged_exercises,
    get_exercise_progression,
    get_muscle_volume,
    get_period_summary,
    get_last_exercise_performance,
    get_recent_workouts,
    get_weekly_muscle_volume,
    get_workout_details,
    get_workout_summary,
    init_db,
    log_sets_batch,
    set_workout_notes,
    start_new_workout,
    update_set,
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

    with get_connection() as check:
        assert "notes" in [c[1] for c in check.execute("PRAGMA table_info(workouts)")]   # colonna aggiunta
    uid = make_user()
    assert get_recent_workouts(uid) == []          # invisibile finché non viene assegnato
    assert users.count_legacy_workouts() == 1
    assert users.claim_legacy_workouts(uid) == 1
    assert len(get_recent_workouts(uid)) == 1
    assert get_workout_details(uid, 1)[1][0][0] == "Panca"


def test_recent_workouts_paging_is_stable(make_user):
    uid = make_user()
    ids = []
    for _ in range(5):
        w = start_new_workout(uid, "Push")
        log_sets_batch(uid, w, "Panca", [{"weight": 10, "reps": 5, "duration": None}])
        end_active_workout(uid, w)
        ids.append(w)
    seen = [r[0] for off in (0, 2, 4) for r in get_recent_workouts(uid, limit=2, offset=off)]
    assert seen == sorted(ids, reverse=True)   # stesso secondo di start_time: decide l'id


# --- Modifica di singole serie, note e durata -------------------------------------

def _one_set_workout(uid, weight=80, reps=8):
    w = start_new_workout(uid, "Push")
    log_sets_batch(uid, w, "Panca", [{"weight": weight, "reps": reps, "duration": None}])
    _, sets = get_workout_details(uid, w)
    return w, sets[0][5]   # id della serie (6a colonna)


def test_update_set(make_user):
    uid = make_user()
    w, set_id = _one_set_workout(uid)
    assert update_set(uid, set_id, 82.5, 6, None)
    _, sets = get_workout_details(uid, w)
    assert (sets[0][2], sets[0][3], sets[0][4]) == (82.5, 6, None)
    assert update_set(uid, set_id, 0, 0, 45)           # diventa una serie a tempo
    assert get_workout_details(uid, w)[1][0][4] == 45
    assert update_set(uid, 99999, 1, 1, None) is False


def test_delete_single_set_keeps_the_others(make_user):
    uid = make_user()
    w = start_new_workout(uid, "Push")
    log_sets_batch(uid, w, "Panca", [{"weight": 80, "reps": r, "duration": None} for r in (8, 7, 6)])
    ids = [s[5] for s in get_workout_details(uid, w)[1]]
    assert delete_set(uid, ids[1])
    assert [s[3] for s in get_workout_details(uid, w)[1]] == [8, 6]
    assert delete_set(uid, ids[1]) is False            # già eliminata


def test_set_order_never_repeats_after_deleting_a_middle_set(make_user):
    uid = make_user()
    w = start_new_workout(uid, "Push")
    log_sets_batch(uid, w, "Panca", [{"weight": 80, "reps": 8, "duration": None}] * 3)
    delete_set(uid, get_workout_details(uid, w)[1][1][5])
    log_sets_batch(uid, w, "Panca", [{"weight": 80, "reps": 5, "duration": None}])
    orders = [s[1] for s in get_workout_details(uid, w)[1]]
    assert len(orders) == len(set(orders)) == 3


def test_users_cannot_edit_or_delete_each_others_sets(make_user):
    a, b = make_user(), make_user()
    w, set_id = _one_set_workout(a)
    assert update_set(b, set_id, 1, 1, None) is False
    assert delete_set(b, set_id) is False
    assert set_workout_notes(b, w, "hack") is False
    _, sets = get_workout_details(a, w)
    assert sets[0][2] == 80 and sets[0][3] == 8
    assert get_workout_details(a, w)[0][3] == ""


def test_workout_notes(make_user):
    uid = make_user()
    w, _ = _one_set_workout(uid)
    assert get_workout_details(uid, w)[0][3] == ""
    assert set_workout_notes(uid, w, "Dormito poco, spalla dolorante")
    end_active_workout(uid, w)
    assert get_workout_details(uid, w)[0][3] == "Dormito poco, spalla dolorante"
    assert get_recent_workouts(uid)[0][6] == "Dormito poco, spalla dolorante"


def test_duration_in_seconds(make_user):
    uid = make_user()
    w, _ = _one_set_workout(uid)
    with get_connection() as conn:
        conn.execute("UPDATE workouts SET start_time = datetime('now', '-45 minutes') WHERE id = ?", (w,))
    elapsed = get_workout_details(uid, w)[0][4]          # in corso: fino ad ora
    assert 45 * 60 - 5 <= elapsed <= 45 * 60 + 5
    with get_connection() as conn:
        conn.execute("UPDATE workouts SET start_time = '2025-01-01 10:00:00', end_time = '2025-01-01 10:52:30' WHERE id = ?", (w,))
        conn.execute("UPDATE workouts SET is_active = 0 WHERE id = ?", (w,))
    assert get_workout_details(uid, w)[0][4] == 52 * 60 + 30
    assert get_recent_workouts(uid)[0][7] == 52 * 60 + 30


def test_duration_unknown_for_unfinished_in_history_query(make_user):
    uid = make_user()
    w, _ = _one_set_workout(uid)
    with get_connection() as conn:
        conn.execute("UPDATE workouts SET is_active = 0 WHERE id = ?", (w,))   # chiuso senza orario di fine
    assert get_recent_workouts(uid)[0][7] is None


# --- Periodi: equilibrio muscolare e confronti ------------------------------------

def _finished_days_ago(uid, days_ago, exercise="Panca", sets=3, weight=100, reps=5, minutes=60):
    w = start_new_workout(uid, "Push")
    log_sets_batch(uid, w, exercise, [{"weight": weight, "reps": reps, "duration": None}] * sets)
    end_active_workout(uid, w)
    with get_connection() as conn:
        conn.execute(
            "UPDATE workouts SET start_time = datetime('now', ?), end_time = datetime('now', ?) WHERE id = ?",
            (f"-{days_ago} days", f"-{days_ago} days", w)
        )
        conn.execute("UPDATE workouts SET end_time = datetime(start_time, ?) WHERE id = ?", (f"+{minutes} minutes", w))
    return w


def test_muscle_volume_windows(make_user):
    uid = make_user()
    _finished_days_ago(uid, 2)      # dentro 7 giorni
    _finished_days_ago(uid, 10)     # dentro 30, non dentro 7
    _finished_days_ago(uid, 40)     # dentro 90
    assert get_muscle_volume(uid, 7)["Petto"] == 3
    assert get_muscle_volume(uid, 30)["Petto"] == 6
    assert get_muscle_volume(uid, 90)["Petto"] == 9
    assert get_muscle_volume(uid, 7, offset_days=7)["Petto"] == 3    # 7-14 giorni fa: il workout di 10 giorni fa
    assert set(get_muscle_volume(uid, 7)) >= {"Petto", "Dorso", "Gambe", "Spalle", "Braccia", "Addome", "Altro"}


def test_active_workouts_not_counted_in_period_stats(make_user):
    uid = make_user()
    w = start_new_workout(uid, "Push")
    log_sets_batch(uid, w, "Panca", [{"weight": 100, "reps": 5, "duration": None}])
    assert get_muscle_volume(uid, 7)["Petto"] == 0
    assert get_period_summary(uid, 7)["workouts"] == 0


def test_period_summary_values(make_user):
    uid = make_user()
    _finished_days_ago(uid, 1, sets=3, weight=100, reps=5, minutes=60)    # volume 1500, 3 serie
    _finished_days_ago(uid, 3, sets=2, weight=50, reps=10, minutes=30)    # volume 1000, 2 serie
    summary = get_period_summary(uid, 7)
    assert summary == {"workouts": 2, "training_days": 2, "duration_seconds": 5400, "sets": 5, "volume": 2500.0}


def test_period_summary_previous_window_and_isolation(make_user):
    a, b = make_user(), make_user()
    _finished_days_ago(a, 2)
    _finished_days_ago(a, 9)
    _finished_days_ago(b, 2)
    assert get_period_summary(a, 7)["workouts"] == 1
    assert get_period_summary(a, 7, offset_days=7)["workouts"] == 1
    assert get_period_summary(a, 14)["workouts"] == 2
    assert get_period_summary(b, 7)["workouts"] == 1


def test_forgotten_open_workout_does_not_inflate_duration(make_user):
    uid = make_user()
    _finished_days_ago(uid, 1, minutes=45)
    _finished_days_ago(uid, 2, minutes=60 * 30)      # 30 ore: chiuso automaticamente dal successivo
    assert get_period_summary(uid, 7)["duration_seconds"] == 45 * 60
