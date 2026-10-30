import pytest

from src import routines, users
from src.database import end_active_workout, get_connection, log_sets_batch, start_new_workout


def test_duplicate_email_rejected(make_user):
    make_user("a@example.com")
    with pytest.raises(users.EmailTaken):
        users.create_user("a@example.com", "x")


def test_public_user_hides_hash(make_user):
    uid = make_user()
    assert "password_hash" not in users.public_user(users.get_user(uid))


def test_session_lifecycle(make_user):
    uid = make_user()
    token = users.create_session(uid)
    assert users.get_user_by_session(token)["id"] == uid
    with get_connection() as conn:  # il token grezzo non è mai nel database
        assert conn.execute("SELECT COUNT(*) FROM sessions WHERE token_hash = ?", (token,)).fetchone()[0] == 0
    users.delete_session(token)
    assert users.get_user_by_session(token) is None
    assert users.get_user_by_session("inventato") is None


def test_expired_session_rejected_and_purged(make_user):
    uid = make_user()
    token = users.create_session(uid, days=-1)
    assert users.get_user_by_session(token) is None
    users.purge_expired()
    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0


def test_delete_user_sessions_keeps_current(make_user):
    uid = make_user()
    keep, other = users.create_session(uid), users.create_session(uid)
    users.delete_user_sessions(uid, keep_raw_token=keep)
    assert users.get_user_by_session(keep) is not None
    assert users.get_user_by_session(other) is None


def test_email_token_single_use_and_purpose(make_user):
    uid = make_user()
    t = users.create_email_token(uid, "reset", 1)
    assert users.consume_email_token(t, "verify") is None
    assert users.consume_email_token(t, "reset") == uid
    assert users.consume_email_token(t, "reset") is None


def test_new_token_invalidates_previous(make_user):
    uid = make_user()
    old = users.create_email_token(uid, "verify", 48)
    new = users.create_email_token(uid, "verify", 48)
    assert users.consume_email_token(old, "verify") is None
    assert users.consume_email_token(new, "verify") == uid


def test_expired_email_token(make_user):
    uid = make_user()
    t = users.create_email_token(uid, "verify", -1)
    assert users.consume_email_token(t, "verify") is None


def test_newsletter_requires_verified_and_opt_in(make_user):
    make_user("no-consenso@example.com", marketing=False, verified=True)
    make_user("non-verificato@example.com", marketing=True, verified=False)
    ok = make_user("ok@example.com", marketing=True, verified=True)
    assert [r["email"] for r in users.list_newsletter_recipients()] == ["ok@example.com"]
    users.set_marketing_opt_in(ok, False)
    assert users.list_newsletter_recipients() == []
    users.set_marketing_opt_in(ok, True)
    assert len(users.list_newsletter_recipients()) == 1


def test_consent_timestamp_recorded_and_cleared(make_user):
    uid = make_user(marketing=False)
    def stamp():
        with get_connection() as conn:
            return conn.execute("SELECT marketing_consent_at FROM users WHERE id = ?", (uid,)).fetchone()[0]
    assert stamp() is None
    users.set_marketing_opt_in(uid, True)
    assert stamp() is not None
    users.set_marketing_opt_in(uid, False)
    assert stamp() is None


def test_delete_user_removes_everything_and_spares_others(make_user):
    a, b = make_user(), make_user()
    for uid in (a, b):
        routines.create_routine(uid, "Push", "", [{"name": "Panca", "muscle_group": "Petto", "note": ""}])
        w = start_new_workout(uid, "Push")
        log_sets_batch(uid, w, "Panca", [{"weight": 50, "reps": 5, "duration": None}])
        end_active_workout(uid, w)
        users.create_session(uid)
        users.create_email_token(uid, "verify", 1)
    assert users.delete_user(a)
    assert users.get_user(a) is None
    with get_connection() as conn:
        for table, col in (("workouts", "user_id"), ("routines", "user_id"), ("sessions", "user_id"), ("email_tokens", "user_id")):
            assert conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} = ?", (a,)).fetchone()[0] == 0
            assert conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} = ?", (b,)).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM sets").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM routine_exercises").fetchone()[0] == 1


def test_export_contains_user_data_only(make_user):
    a, b = make_user("a@example.com"), make_user("b@example.com")
    w = start_new_workout(a, "Push")
    log_sets_batch(a, w, "Panca", [{"weight": 50, "reps": 5, "duration": None}])
    data = users.export_user_data(a)
    assert data["account"]["email"] == "a@example.com"
    assert len(data["workouts"]) == 1
    assert users.export_user_data(b)["workouts"] == []
    assert "password" not in str(data).lower()
