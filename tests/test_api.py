"""Test degli endpoint HTTP. Richiedono fastapi e httpx (pip install -r requirements-dev.txt)."""
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from src import config, emailer, users  # noqa: E402
from src.api import ALL_LIMITERS, app  # noqa: E402


@pytest.fixture(autouse=True)
def reset_limiters():
    for limiter in ALL_LIMITERS:
        limiter.reset_all()
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def outbox(monkeypatch):
    """Cattura le email che l'app proverebbe a inviare."""
    sent = []
    monkeypatch.setattr(emailer, "send_email", lambda to, subject, body, headers=None: sent.append((to, subject, body)) or True)
    return sent


def register(client, email="mario@example.com", password="password-lunga-1", **extra):
    return client.post("/api/auth/register", json={"email": email, "password": password, **extra})


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def logged(client):
    data = register(client).json()
    return auth(data["token"])


def test_public_config(client):
    data = client.get("/api/public-config").json()
    assert data["invite_required"] is False and "Petto" in data["muscle_groups"]


def test_register_login_me_logout(client):
    r = register(client, "Mario@Example.com", marketing_opt_in=True)
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["email"] == "mario@example.com" and body["user"]["marketing_opt_in"] is True
    assert "password" not in str(body).lower()
    assert client.get("/api/auth/me", headers=auth(body["token"])).json()["email"] == "mario@example.com"
    login = client.post("/api/auth/login", json={"email": "mario@example.com", "password": "password-lunga-1"}).json()
    assert client.post("/api/auth/logout", headers=auth(login["token"])).status_code == 200
    assert client.get("/api/auth/me", headers=auth(login["token"])).status_code == 401


def test_register_validation_and_duplicates(client):
    assert register(client, "non-una-mail").status_code == 422
    assert register(client, password="corta").status_code == 422
    assert register(client).status_code == 200
    assert register(client).status_code == 409


def test_wrong_password_and_lockout(client):
    register(client)
    for _ in range(5):
        assert client.post("/api/auth/login", json={"email": "mario@example.com", "password": "sbagliata!"}).status_code == 401
    r = client.post("/api/auth/login", json={"email": "mario@example.com", "password": "password-lunga-1"})
    assert r.status_code == 429


def test_unknown_email_same_error(client):
    r = client.post("/api/auth/login", json={"email": "nessuno@example.com", "password": "password-lunga-1"})
    assert r.status_code == 401


def test_auth_required(client):
    assert client.get("/api/routines").status_code == 401
    assert client.get("/api/routines", headers=auth("finto")).status_code == 401
    assert client.get("/api/workout/active").status_code == 401


def test_invite_code(client, monkeypatch):
    monkeypatch.setattr(config, "REGISTRATION_INVITE_CODE", "famiglia")
    assert client.get("/api/public-config").json()["invite_required"] is True
    assert register(client).status_code == 403
    assert register(client, invite_code="sbagliato").status_code == 403
    assert register(client, invite_code="famiglia").status_code == 200


def test_verification_flow(client, outbox):
    register(client)
    assert "#verify=" in outbox[0][2]
    token = outbox[0][2].split("#verify=")[1].split()[0]
    assert client.post("/api/auth/verify-email", json={"token": "finto"}).status_code == 400
    assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 200
    assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 400  # monouso
    assert users.get_user_by_email("mario@example.com")["email_verified"] is True


def test_verification_required_blocks_login(client, outbox, monkeypatch):
    monkeypatch.setattr(config, "REQUIRE_EMAIL_VERIFICATION", True)
    assert register(client).json() == {"verification_required": True}
    r = client.post("/api/auth/login", json={"email": "mario@example.com", "password": "password-lunga-1"})
    assert r.status_code == 403


def test_forgot_and_reset_password(client, outbox):
    old = register(client).json()["token"]
    outbox.clear()
    assert client.post("/api/auth/forgot-password", json={"email": "nessuno@example.com"}).status_code == 200
    assert outbox == []  # nessuna rivelazione
    assert client.post("/api/auth/forgot-password", json={"email": "mario@example.com"}).status_code == 200
    token = outbox[0][2].split("#reset=")[1].split()[0]
    assert client.post("/api/auth/reset-password", json={"token": token, "password": "breve"}).status_code == 422
    assert client.post("/api/auth/reset-password", json={"token": token, "password": "nuova-password-2"}).status_code == 200
    assert client.post("/api/auth/reset-password", json={"token": token, "password": "altra-password-3"}).status_code == 400
    assert client.get("/api/auth/me", headers=auth(old)).status_code == 401  # sessioni chiuse
    assert client.post("/api/auth/login", json={"email": "mario@example.com", "password": "nuova-password-2"}).status_code == 200


def test_change_password(client):
    token = register(client).json()["token"]
    other = client.post("/api/auth/login", json={"email": "mario@example.com", "password": "password-lunga-1"}).json()["token"]
    h = auth(token)
    assert client.post("/api/auth/change-password", headers=h, json={"current_password": "no", "new_password": "nuova-password-2"}).status_code == 403
    assert client.post("/api/auth/change-password", headers=h, json={"current_password": "password-lunga-1", "new_password": "nuova-password-2"}).status_code == 200
    assert client.get("/api/auth/me", headers=h).status_code == 200            # sessione corrente mantenuta
    assert client.get("/api/auth/me", headers=auth(other)).status_code == 401  # le altre chiuse


def test_marketing_toggle(client, logged):
    assert client.patch("/api/auth/me", headers=logged, json={"marketing_opt_in": True}).json()["marketing_opt_in"] is True
    assert client.patch("/api/auth/me", headers=logged, json={"marketing_opt_in": False}).json()["marketing_opt_in"] is False


def test_unsubscribe_get_is_harmless_and_post_works(client):
    token = register(client, marketing_opt_in=True).json()["user"]
    uid = token["id"]
    from src.auth import unsubscribe_signature
    sig = unsubscribe_signature(uid)
    assert client.get(f"/unsubscribe?u={uid}&t={sig}").status_code == 200
    assert users.get_user(uid)["marketing_opt_in"] is True  # la GET non cambia nulla
    assert client.post(f"/unsubscribe?u={uid}&t=falsa").status_code == 400
    assert client.get(f"/unsubscribe?u={uid}&t=falsa").status_code == 400
    assert client.post(f"/unsubscribe?u={uid}&t={sig}").status_code == 200
    assert users.get_user(uid)["marketing_opt_in"] is False


def test_delete_account(client):
    token = register(client).json()["token"]
    h = auth(token)
    assert client.post("/api/auth/delete-account", headers=h, json={"password": "sbagliata"}).status_code == 403
    assert client.post("/api/auth/delete-account", headers=h, json={"password": "password-lunga-1"}).status_code == 200
    assert client.get("/api/auth/me", headers=h).status_code == 401
    assert users.get_user_by_email("mario@example.com") is None
    assert register(client).status_code == 200  # l'email torna disponibile


def test_export(client, logged):
    data = client.get("/api/auth/export", headers=logged).json()
    assert data["account"]["email"] == "mario@example.com" and "workouts" in data


def test_routines_crud_and_import(client, logged):
    ex = [{"name": "Panca", "muscle_group": "Petto", "note": "3x8"}]
    r = client.post("/api/routines", headers=logged, json={"name": "Push", "notes": "", "exercises": ex})
    assert r.status_code == 200
    rid = r.json()["id"]
    assert client.post("/api/routines", headers=logged, json={"name": "push", "notes": "", "exercises": ex}).status_code == 409
    assert client.post("/api/routines", headers=logged, json={"name": "X", "notes": "", "exercises": []}).status_code == 422
    assert client.put(f"/api/routines/{rid}", headers=logged, json={"name": "Push B", "notes": "", "exercises": ex}).json()["name"] == "Push B"
    imp = client.post("/api/routines/import", headers=logged, json={"csv": "scheda,esercizio\nPull,Trazioni\n"}).json()
    assert imp["created"] == ["Pull"]
    assert client.post("/api/routines/import", headers=logged, json={"csv": "a,b\n1,2"}).status_code == 422
    # "Pull" esiste già (importata sopra): il modello aggiunge solo le altre 4 schede
    created = client.post("/api/routines/template", headers=logged).json()["created"]
    assert len(created) == 4 and "Pull" not in created
    assert client.delete(f"/api/routines/{rid}", headers=logged).status_code == 200
    assert client.delete(f"/api/routines/{rid}", headers=logged).status_code == 404


def test_full_workout_flow(client, logged):
    ex = [{"name": "Panca", "muscle_group": "Petto", "note": ""}]
    rid = client.post("/api/routines", headers=logged, json={"name": "Push", "notes": "", "exercises": ex}).json()["id"]
    assert client.get("/api/workout/active", headers=logged).json() == {"active": False}
    assert client.post("/api/workout/start", headers=logged, json={"routine_id": 9999}).status_code == 404
    assert client.post("/api/workout/start", headers=logged, json={"routine_id": rid}).status_code == 200
    assert client.post("/api/workout/start", headers=logged, json={"routine_id": rid}).status_code == 400
    sets = {"exercise": "panca", "sets": [{"weight": 80, "reps": 8}, {"weight": 80, "reps": 0, "duration": 30}]}
    assert client.post("/api/workout/sets", headers=logged, json=sets).status_code == 200
    active = client.get("/api/workout/active", headers=logged).json()
    assert active["split"] == "Push" and active["routine"]["exercises"][0]["name"] == "Panca"
    assert [s["exercise"] for s in active["sets"]] == ["Panca", "Panca"]
    assert client.delete("/api/workout/sets/last", headers=logged).status_code == 200
    assert client.post("/api/workout/sets", headers=logged, json={"exercise": "Panca", "sets": [{"weight": 85, "reps": 5}]}).status_code == 200
    assert client.post("/api/workout/end", headers=logged).status_code == 200
    hist = client.get("/api/workouts/history", headers=logged).json()["items"]
    assert len(hist) == 1 and hist[0]["split"] == "Push"
    assert client.get("/api/analytics/exercises", headers=logged).json() == ["Panca"]
    assert len(client.get("/api/analytics/Panca", headers=logged).json()) == 1
    assert client.get("/api/analytics/weekly-volume", headers=logged).json()["Petto"] == 1
    assert client.get("/api/exercises/Panca/last", headers=logged).json()["sets"][0]["weight"] == 85
    assert client.delete(f"/api/workouts/{hist[0]['id']}", headers=logged).status_code == 200


def test_free_workout(client, logged):
    r = client.post("/api/workout/start", headers=logged, json={"routine_id": None})
    assert r.json()["split"] == "Allenamento libero"


def test_invalid_set_payloads(client, logged):
    client.post("/api/workout/start", headers=logged, json={"routine_id": None})
    assert client.post("/api/workout/sets", headers=logged, json={"exercise": "", "sets": [{"weight": 1, "reps": 1}]}).status_code == 422
    assert client.post("/api/workout/sets", headers=logged, json={"exercise": "X", "sets": []}).status_code == 422
    assert client.post("/api/workout/sets", headers=logged, json={"exercise": "X", "sets": [{"weight": -5, "reps": 1}]}).status_code == 422


def test_two_users_are_isolated(client):
    a = auth(register(client, "a@example.com").json()["token"])
    b = auth(register(client, "b@example.com").json()["token"])
    rid = client.post("/api/routines", headers=a, json={"name": "Push", "notes": "", "exercises": [{"name": "Panca", "muscle_group": "Petto", "note": ""}]}).json()["id"]
    client.post("/api/workout/start", headers=a, json={"routine_id": rid})
    client.post("/api/workout/sets", headers=a, json={"exercise": "Panca", "sets": [{"weight": 80, "reps": 8}]})
    client.post("/api/workout/end", headers=a)
    wid = client.get("/api/workouts/history", headers=a).json()["items"][0]["id"]

    assert client.get("/api/routines", headers=b).json() == []
    assert client.get("/api/workouts/history", headers=b).json() == {"items": [], "has_more": False}
    assert client.get("/api/analytics/exercises", headers=b).json() == []
    assert client.delete(f"/api/workouts/{wid}", headers=b).status_code == 404
    assert client.put(f"/api/routines/{rid}", headers=b, json={"name": "H", "notes": "", "exercises": [{"name": "x", "muscle_group": None, "note": ""}]}).status_code == 404
    assert client.post("/api/workout/start", headers=b, json={"routine_id": rid}).status_code == 404
    assert len(client.get("/api/workouts/history", headers=a).json()["items"]) == 1


def test_static_pages(client):
    assert client.get("/").status_code == 200
    assert client.get("/privacy").status_code == 200
    sw = client.get("/sw.js")
    assert sw.status_code == 200 and "javascript" in sw.headers["content-type"]


def test_api_responses_not_cached(client, logged):
    assert "no-store" in client.get("/api/routines", headers=logged).headers.get("cache-control", "")


def test_history_paging(client, logged):
    for i in range(5):
        client.post("/api/workout/start", headers=logged, json={"routine_id": None})
        client.post("/api/workout/sets", headers=logged, json={"exercise": f"Es{i}", "sets": [{"weight": 10, "reps": 5}]})
        client.post("/api/workout/end", headers=logged)
    page1 = client.get("/api/workouts/history?limit=2", headers=logged).json()
    page2 = client.get("/api/workouts/history?limit=2&offset=2", headers=logged).json()
    page3 = client.get("/api/workouts/history?limit=2&offset=4", headers=logged).json()
    assert [len(p["items"]) for p in (page1, page2, page3)] == [2, 2, 1]
    assert [p["has_more"] for p in (page1, page2, page3)] == [True, True, False]
    ids = [w["id"] for p in (page1, page2, page3) for w in p["items"]]
    assert ids == sorted(ids, reverse=True) and len(set(ids)) == 5   # nessun doppione, dal più recente
    assert client.get("/api/workouts/history?limit=0", headers=logged).status_code == 422
    assert client.get("/api/workouts/history?offset=-1", headers=logged).status_code == 422


def _workout_with_set(client, h, reps=8):
    client.post("/api/workout/start", headers=h, json={"routine_id": None})
    client.post("/api/workout/sets", headers=h, json={"exercise": "Panca", "sets": [{"weight": 80, "reps": reps}]})


def test_active_workout_exposes_set_ids_notes_and_elapsed(client, logged):
    _workout_with_set(client, logged)
    active = client.get("/api/workout/active", headers=logged).json()
    assert active["notes"] == "" and active["elapsed_seconds"] >= 0
    assert isinstance(active["sets"][0]["id"], int)


def test_edit_and_delete_single_set(client, logged):
    _workout_with_set(client, logged)
    set_id = client.get("/api/workout/active", headers=logged).json()["sets"][0]["id"]
    assert client.patch(f"/api/sets/{set_id}", headers=logged, json={"weight": 82.5, "reps": 6}).status_code == 200
    s = client.get("/api/workout/active", headers=logged).json()["sets"][0]
    assert (s["weight"], s["reps"], s["duration"]) == (82.5, 6, None)
    # serie a tempo: le ripetizioni vengono azzerate
    assert client.patch(f"/api/sets/{set_id}", headers=logged, json={"weight": 0, "reps": 9, "duration": 60}).status_code == 200
    s = client.get("/api/workout/active", headers=logged).json()["sets"][0]
    assert (s["reps"], s["duration"]) == (0, 60)
    assert client.patch(f"/api/sets/{set_id}", headers=logged, json={"weight": 5}).status_code == 422   # né reps né durata
    assert client.patch(f"/api/sets/{set_id}", headers=logged, json={"weight": -1, "reps": 5}).status_code == 422
    assert client.delete(f"/api/sets/{set_id}", headers=logged).status_code == 200
    assert client.delete(f"/api/sets/{set_id}", headers=logged).status_code == 404
    assert client.patch(f"/api/sets/{set_id}", headers=logged, json={"reps": 5}).status_code == 404
    assert client.get("/api/workout/active", headers=logged).json()["sets"] == []


def test_edit_set_in_workout_with_set(client, logged):
    _workout_with_set(client, logged)
    client.post("/api/workout/end", headers=logged)
    item = client.get("/api/workouts/history", headers=logged).json()["items"][0]
    assert client.patch(f"/api/sets/{item['sets'][0]['id']}", headers=logged, json={"weight": 90, "reps": 5}).status_code == 200
    assert client.get("/api/workouts/history", headers=logged).json()["items"][0]["sets"][0]["weight"] == 90


def test_workout_notes_roundtrip(client, logged):
    _workout_with_set(client, logged)
    wid = client.get("/api/workout/active", headers=logged).json()["id"]
    assert client.put(f"/api/workouts/{wid}/notes", headers=logged, json={"notes": "  Dormito poco  "}).status_code == 200
    assert client.get("/api/workout/active", headers=logged).json()["notes"] == "Dormito poco"
    client.post("/api/workout/end", headers=logged)
    assert client.get("/api/workouts/history", headers=logged).json()["items"][0]["notes"] == "Dormito poco"
    assert client.put(f"/api/workouts/{wid}/notes", headers=logged, json={"notes": "x" * 1001}).status_code == 422
    assert client.put("/api/workouts/9999/notes", headers=logged, json={"notes": "a"}).status_code == 404
    assert client.put(f"/api/workouts/{wid}/notes", headers=logged, json={"notes": ""}).status_code == 200   # si può svuotare


def test_history_duration(client, logged):
    from src.database import get_connection
    _workout_with_set(client, logged)
    client.post("/api/workout/end", headers=logged)
    wid = client.get("/api/workouts/history", headers=logged).json()["items"][0]["id"]
    with get_connection() as conn:
        conn.execute("UPDATE workouts SET start_time = '2025-01-01 10:00:00', end_time = '2025-01-01 10:52:30' WHERE id = ?", (wid,))
    assert client.get("/api/workouts/history", headers=logged).json()["items"][0]["duration_seconds"] == 3150
    with get_connection() as conn:   # allenamento dimenticato aperto per un giorno intero
        conn.execute("UPDATE workouts SET end_time = '2025-01-02 10:00:00' WHERE id = ?", (wid,))
    assert client.get("/api/workouts/history", headers=logged).json()["items"][0]["duration_seconds"] is None


def test_other_user_cannot_touch_my_sets_or_notes(client):
    a = auth(register(client, "a@example.com").json()["token"])
    b = auth(register(client, "b@example.com").json()["token"])
    _workout_with_set(client, a)
    active = client.get("/api/workout/active", headers=a).json()
    set_id, wid = active["sets"][0]["id"], active["id"]
    assert client.patch(f"/api/sets/{set_id}", headers=b, json={"reps": 1}).status_code == 404
    assert client.delete(f"/api/sets/{set_id}", headers=b).status_code == 404
    assert client.put(f"/api/workouts/{wid}/notes", headers=b, json={"notes": "x"}).status_code == 404
    assert client.get("/api/workout/active", headers=a).json()["sets"][0]["reps"] == 8


def test_body_weight_endpoints(client, logged):
    assert client.get("/api/body-weight", headers=logged).json() == []
    assert client.post("/api/body-weight", headers=logged, json={"weight_kg": 80.26, "date": "2026-01-10"}).json() == {"date": "2026-01-10", "weight_kg": 80.3}
    assert client.post("/api/body-weight", headers=logged, json={"weight_kg": 79.0, "date": "2026-01-10"}).status_code == 200   # sostituisce
    assert client.post("/api/body-weight", headers=logged, json={"weight_kg": 78.0}).status_code == 200                           # oggi
    data = client.get("/api/body-weight", headers=logged).json()
    assert [d["weight_kg"] for d in data] == [79.0, 78.0]
    assert client.post("/api/body-weight", headers=logged, json={"weight_kg": 5}).status_code == 422
    assert client.post("/api/body-weight", headers=logged, json={"weight_kg": 80, "date": "ieri"}).status_code == 422
    assert client.post("/api/body-weight", headers=logged, json={"weight_kg": 80, "date": "2999-01-01"}).status_code == 422
    assert client.delete("/api/body-weight/2026-01-10", headers=logged).status_code == 200
    assert client.delete("/api/body-weight/2026-01-10", headers=logged).status_code == 404


def test_body_weight_is_private_and_needs_login(client):
    a = auth(register(client, "a@example.com").json()["token"])
    b = auth(register(client, "b@example.com").json()["token"])
    client.post("/api/body-weight", headers=a, json={"weight_kg": 80, "date": "2026-01-10"})
    assert client.get("/api/body-weight", headers=b).json() == []
    assert client.delete("/api/body-weight/2026-01-10", headers=b).status_code == 404
    assert client.get("/api/body-weight").status_code == 401
    assert client.post("/api/body-weight", json={"weight_kg": 80}).status_code == 401


def _done_workout(client, h, exercise="Panca", reps=5):
    client.post("/api/workout/start", headers=h, json={"routine_id": None})
    client.post("/api/workout/sets", headers=h, json={"exercise": exercise, "sets": [{"weight": 100, "reps": reps}] * 3})
    client.post("/api/workout/end", headers=h)


def test_muscle_volume_endpoint(client, logged):
    _done_workout(client, logged)
    data = client.get("/api/analytics/muscle-volume?days=30", headers=logged).json()
    assert data["days"] == 30 and data["sets"]["Petto"] == 3 and data["sets"]["Gambe"] == 0
    assert client.get("/api/analytics/muscle-volume", headers=logged).json()["days"] == 30      # default
    assert client.get("/api/analytics/muscle-volume?days=0", headers=logged).status_code == 422
    assert client.get("/api/analytics/muscle-volume?days=1000", headers=logged).status_code == 422


def test_compare_endpoint(client, logged):
    from src.database import get_connection
    _done_workout(client, logged)                      # oggi: periodo corrente
    _done_workout(client, logged, "Squat", reps=8)     # lo spostiamo nel periodo precedente
    with get_connection() as conn:
        wid = conn.execute("SELECT MAX(id) FROM workouts").fetchone()[0]
        conn.execute("UPDATE workouts SET start_time = datetime('now', '-10 days'), end_time = datetime('now', '-10 days', '+1 hour') WHERE id = ?", (wid,))
    data = client.get("/api/analytics/compare?days=7", headers=logged).json()
    assert data["days"] == 7
    assert data["current"]["workouts"] == 1 and data["previous"]["workouts"] == 1
    assert data["current"]["sets"] == 3 and data["current"]["volume"] == 1500.0
    assert data["previous"]["volume"] == 2400.0 and data["previous"]["duration_seconds"] == 3600
    assert data["current"]["muscles"]["Petto"] == 3 and data["previous"]["muscles"]["Gambe"] == 3
    assert client.get("/api/analytics/compare?days=0", headers=logged).status_code == 422


def test_compare_is_private(client):
    a = auth(register(client, "a@example.com").json()["token"])
    b = auth(register(client, "b@example.com").json()["token"])
    _done_workout(client, a)
    data = client.get("/api/analytics/compare?days=7", headers=b).json()
    assert data["current"]["workouts"] == 0 and data["current"]["muscles"]["Petto"] == 0


# --- Amministrazione e log degli accessi --------------------------------------------
def test_admin_stats_requires_admin(client, logged, monkeypatch):
    assert client.get("/api/admin/stats").status_code == 401
    assert client.get("/api/admin/stats", headers=logged).status_code == 403
    assert client.get("/api/auth/me", headers=logged).json()["is_admin"] is False

    monkeypatch.setattr(config, "ADMIN_EMAILS", {"mario@example.com"})
    assert client.get("/api/auth/me", headers=logged).json()["is_admin"] is True
    res = client.get("/api/admin/stats", headers=logged)
    assert res.status_code == 200
    data = res.json()
    assert data["users"]["total"] == 1 and "mario@example.com" not in res.text


def test_admin_needs_verified_email_when_smtp_is_on(client, logged, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_EMAILS", {"mario@example.com"})
    monkeypatch.setattr(config, "SMTP_ENABLED", True)
    assert client.get("/api/admin/stats", headers=logged).status_code == 403


def test_admin_page_is_served(client):
    assert client.get("/admin").status_code == 200


def test_access_log_records_user_id_but_no_secrets(client, caplog):
    import logging
    token = register(client).json()["token"]
    uid = client.get("/api/auth/me", headers=auth(token)).json()["id"]
    with caplog.at_level(logging.INFO, logger="gymbot.access"):
        client.get("/api/routines", headers=auth(token))
        client.get("/api/routines")                                   # senza accesso
    lines = [r.getMessage() for r in caplog.records]
    assert any(f"GET /api/routines -> 200" in l and f"uid={uid}" in l for l in lines)
    assert any("GET /api/routines -> 401" in l and "uid=-" in l for l in lines)
    assert not any(token in l or "mario@example.com" in l for l in lines)
