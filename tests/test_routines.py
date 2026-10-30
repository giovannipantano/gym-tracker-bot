import pytest

from src import routines
from src.database import get_active_workout, start_new_workout

EX = lambda name, group="Petto", note="": {"name": name, "muscle_group": group, "note": note}


def test_create_list_update_delete(make_user):
    uid = make_user()
    r = routines.create_routine(uid, "Push", "note", [EX("Panca"), EX("Dip", "Braccia")])
    assert [e["name"] for e in routines.list_routines(uid)[0]["exercises"]] == ["Panca", "Dip"]
    updated = routines.update_routine(uid, r["id"], "Push 2", "", [EX("Croci")])
    assert updated["name"] == "Push 2" and len(updated["exercises"]) == 1
    assert routines.delete_routine(uid, r["id"]) is True
    assert routines.list_routines(uid) == []


def test_duplicate_name_case_insensitive(make_user):
    uid = make_user()
    routines.create_routine(uid, "Push", "", [EX("Panca")])
    with pytest.raises(routines.DuplicateRoutine):
        routines.create_routine(uid, "push", "", [EX("Panca")])


def test_validation(make_user):
    uid = make_user()
    with pytest.raises(routines.RoutineError):
        routines.create_routine(uid, "  ", "", [EX("Panca")])
    with pytest.raises(routines.RoutineError):
        routines.create_routine(uid, "Vuota", "", [])
    with pytest.raises(routines.RoutineError):
        routines.create_routine(uid, "Troppi", "", [EX(f"E{i}") for i in range(routines.MAX_EXERCISES + 1)])


def test_isolation_between_users(make_user):
    a, b = make_user(), make_user()
    r = routines.create_routine(a, "Push", "", [EX("Panca")])
    assert routines.list_routines(b) == []
    assert routines.get_routine(b, r["id"]) is None
    assert routines.update_routine(b, r["id"], "Hack", "", [EX("X")]) is None
    assert routines.delete_routine(b, r["id"]) is False
    routines.create_routine(b, "Push", "", [EX("Panca")])  # stesso nome, utente diverso: ok


def test_delete_routine_keeps_workouts(make_user):
    uid = make_user()
    r = routines.create_routine(uid, "Push", "", [EX("Panca")])
    start_new_workout(uid, "Push", r["id"])
    routines.delete_routine(uid, r["id"])
    active = get_active_workout(uid)
    assert active is not None and active[3] is None


def test_seed_template_idempotent(make_user):
    uid = make_user()
    first = routines.seed_template(uid)
    assert len(first) == 5
    assert routines.seed_template(uid) == []
    assert len(routines.list_routines(uid)) == 5


def test_csv_import_comma_and_semicolon(make_user):
    uid = make_user()
    res = routines.import_routines_csv(uid, "scheda,esercizio,gruppo,note\nA,Panca,Petto,3x8\nA,Squat,Gambe,\nB,Curl,Braccia,\n")
    assert res == {"created": ["A", "B"], "updated": []}
    res = routines.import_routines_csv(uid, "Scheda;Esercizio\nA;Rematore\n")
    assert res == {"created": [], "updated": ["A"]}
    a = next(r for r in routines.list_routines(uid) if r["name"] == "A")
    assert [e["name"] for e in a["exercises"]] == ["Rematore"]


def test_csv_guesses_missing_group(make_user):
    uid = make_user()
    routines.import_routines_csv(uid, "scheda,esercizio\nA,Squat\n")
    assert routines.list_routines(uid)[0]["exercises"][0]["muscle_group"] == "Gambe"


def test_csv_errors_are_atomic(make_user):
    uid = make_user()
    with pytest.raises(routines.RoutineError):
        routines.import_routines_csv(uid, "colonna,altra\n1,2\n")
    with pytest.raises(routines.RoutineError):
        routines.import_routines_csv(uid, "x" * (routines.MAX_CSV_CHARS + 1))
    assert routines.list_routines(uid) == []


def test_routine_limit(make_user, monkeypatch):
    uid = make_user()
    monkeypatch.setattr(routines, "MAX_ROUTINES", 2)
    routines.create_routine(uid, "A", "", [EX("x")])
    routines.create_routine(uid, "B", "", [EX("x")])
    with pytest.raises(routines.RoutineError):
        routines.create_routine(uid, "C", "", [EX("x")])
