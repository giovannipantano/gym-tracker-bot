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
    assert len(client.post("/api/routines/template", headers=logged).json()["created"]) == 5
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
    hist = client.get("/api/workouts/history", headers=logged).json()
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
    wid = client.get("/api/workouts/history", headers=a).json()[0]["id"]

    assert client.get("/api/routines", headers=b).json() == []
    assert client.get("/api/workouts/history", headers=b).json() == []
    assert client.get("/api/analytics/exercises", headers=b).json() == []
    assert client.delete(f"/api/workouts/{wid}", headers=b).status_code == 404
    assert client.put(f"/api/routines/{rid}", headers=b, json={"name": "H", "notes": "", "exercises": [{"name": "x", "muscle_group": None, "note": ""}]}).status_code == 404
    assert client.post("/api/workout/start", headers=b, json={"routine_id": rid}).status_code == 404
    assert len(client.get("/api/workouts/history", headers=a).json()) == 1


def test_static_pages(client):
    assert client.get("/").status_code == 200
    assert client.get("/privacy").status_code == 200
    sw = client.get("/sw.js")
    assert sw.status_code == 200 and "javascript" in sw.headers["content-type"]


def test_api_responses_not_cached(client, logged):
    assert "no-store" in client.get("/api/routines", headers=logged).headers.get("cache-control", "")
