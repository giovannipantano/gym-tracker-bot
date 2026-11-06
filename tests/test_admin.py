"""Statistiche per la pagina /admin: solo numeri aggregati, calcolati correttamente."""
import json

from src import admin, users
from src.database import end_active_workout, get_connection, log_sets_batch, start_new_workout


def test_empty_database(fresh_db):
    stats = admin.collect_stats()
    assert stats["users"]["total"] == 0
    assert stats["workouts"]["completed"] == 0
    assert len(stats["signups_daily"]) == admin.SERIES_DAYS
    assert all(d["count"] == 0 for d in stats["workouts_daily"])
    assert stats["system"]["backup"]["count"] == 0


def test_counts(make_user):
    a = make_user(verified=True, marketing=True)
    b = make_user()
    wid = start_new_workout(a, "Push")
    log_sets_batch(a, wid, "Panca", [(80, 8, None), (80, 7, None)])
    end_active_workout(a, wid)
    start_new_workout(b, "Legs")      # resta in corso

    stats = admin.collect_stats()
    assert stats["users"] == {**stats["users"], "total": 2, "verified": 1, "newsletter": 1, "new_7d": 2}
    assert stats["workouts"]["completed"] == 1 and stats["workouts"]["in_progress"] == 1
    assert stats["workouts"]["sets"] == 2 and stats["workouts"]["last_7d"] == 1
    assert stats["signups_daily"][-1]["count"] == 2        # oggi
    assert stats["workouts_daily"][-1]["count"] == 1


def test_active_users_use_session_activity(make_user):
    a = make_user()
    b = make_user()
    users.create_session(a)
    old = users.create_session(b)
    with get_connection() as conn:
        conn.execute("UPDATE sessions SET last_used_at = datetime('now', '-10 days') WHERE user_id = ?", (b,))
    u = admin.collect_stats()["users"]
    assert (u["active_1d"], u["active_7d"], u["active_30d"]) == (1, 1, 2)


def test_stats_contain_no_personal_data(make_user):
    make_user(email="segreto@example.com")
    assert "segreto" not in json.dumps(admin.collect_stats())


def test_backup_info(tmp_path, monkeypatch):
    from src import config
    monkeypatch.setattr(config, "BACKUP_DIR", str(tmp_path))
    assert admin.backup_info()["count"] == 0
    (tmp_path / "workout_tracker_20260101_000000.db").write_bytes(b"x")
    (tmp_path / "workout_tracker_20260102_000000.db").write_bytes(b"x")
    info = admin.backup_info()
    assert info["count"] == 2 and info["latest_age_hours"] < 1
