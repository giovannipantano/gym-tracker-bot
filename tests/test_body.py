from datetime import date, timedelta

import pytest

from src import body, users


def test_save_and_list_in_chronological_order(make_user):
    uid = make_user()
    today = date.today()
    body.save_weight(uid, 80.04, (today - timedelta(days=2)).isoformat())
    body.save_weight(uid, 79.5, (today - timedelta(days=5)).isoformat())
    body.save_weight(uid, 78.9)   # oggi
    data = body.list_weights(uid)
    assert [d["weight_kg"] for d in data] == [79.5, 80.0, 78.9]      # arrotondato a 0,1
    assert [d["date"] for d in data] == sorted(d["date"] for d in data)


def test_same_day_replaces_previous(make_user):
    uid = make_user()
    body.save_weight(uid, 80.0, "2026-01-10")
    body.save_weight(uid, 79.2, "2026-01-10")
    assert body.list_weights(uid) == [{"date": "2026-01-10", "weight_kg": 79.2}]


@pytest.mark.parametrize("weight", [0, 19.9, 400.1, -5])
def test_implausible_weight_rejected(make_user, weight):
    with pytest.raises(body.BodyWeightError):
        body.save_weight(make_user(), weight)


@pytest.mark.parametrize("day", ["ieri", "2026-13-40", "10/01/2026", "1999-12-31"])
def test_bad_dates_rejected(make_user, day):
    with pytest.raises(body.BodyWeightError):
        body.save_weight(make_user(), 80, day)


def test_future_date_rejected_but_tomorrow_allowed(make_user):
    uid = make_user()
    body.save_weight(uid, 80, (date.today() + timedelta(days=1)).isoformat())   # fuso orario avanti di UTC
    with pytest.raises(body.BodyWeightError):
        body.save_weight(uid, 80, (date.today() + timedelta(days=3)).isoformat())


def test_delete_and_isolation(make_user):
    a, b = make_user(), make_user()
    body.save_weight(a, 80, "2026-01-10")
    assert body.list_weights(b) == []
    assert body.delete_weight(b, "2026-01-10") is False
    assert body.delete_weight(a, "2026-01-10") is True
    assert body.delete_weight(a, "2026-01-10") is False
    assert body.list_weights(a) == []


def test_same_date_for_two_users_is_fine(make_user):
    a, b = make_user(), make_user()
    body.save_weight(a, 80, "2026-01-10")
    body.save_weight(b, 60, "2026-01-10")
    assert body.list_weights(a)[0]["weight_kg"] == 80 and body.list_weights(b)[0]["weight_kg"] == 60


def test_list_limit_keeps_the_most_recent(make_user):
    uid = make_user()
    for d in range(1, 6):
        body.save_weight(uid, 70 + d, f"2026-01-0{d}")
    assert [w["date"] for w in body.list_weights(uid, limit=2)] == ["2026-01-04", "2026-01-05"]


def test_delete_account_removes_weights_and_export_includes_them(make_user):
    a, b = make_user(), make_user()
    body.save_weight(a, 80, "2026-01-10")
    body.save_weight(b, 60, "2026-01-10")
    assert users.export_user_data(a)["body_weights"] == [{"date": "2026-01-10", "weight_kg": 80.0}]
    users.delete_user(a)
    assert body.list_weights(a) == [] and len(body.list_weights(b)) == 1
