import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("send_newsletter", Path(__file__).resolve().parent.parent / "scripts" / "send_newsletter.py")
newsletter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(newsletter)


def test_sends_only_to_consenting_verified(make_user):
    make_user("no@example.com", marketing=False, verified=True)
    make_user("si@example.com", marketing=True, verified=True)
    calls = []
    sent, failed = newsletter.run("Ogg", "Corpo", delay=0, send=lambda *a: calls.append(a) or True, out=lambda *_: None)
    assert (sent, failed) == (1, 0)
    assert calls[0][0] == "si@example.com"


def test_dry_run_sends_nothing(make_user):
    make_user("si@example.com", marketing=True, verified=True)
    calls = []
    assert newsletter.run("O", "C", dry_run=True, send=lambda *a: calls.append(a), out=lambda *_: None) == (0, 0)
    assert calls == []


def test_failures_counted_and_delay_between_sends(make_user):
    for i in range(3):
        make_user(f"u{i}@example.com", marketing=True, verified=True)
    sleeps = []
    results = iter([True, False, True])
    sent, failed = newsletter.run("O", "C", delay=2, send=lambda *a: next(results), sleep=sleeps.append, out=lambda *_: None)
    assert (sent, failed) == (2, 1)
    assert sleeps == [2, 2]


def test_test_to_targets_one_user_even_without_consent(make_user):
    make_user("admin@example.com", marketing=False, verified=False)
    calls = []
    newsletter.run("O", "C", delay=0, test_to="Admin@example.com", send=lambda *a: calls.append(a) or True, out=lambda *_: None)
    assert [c[0] for c in calls] == ["admin@example.com"]


def test_unknown_test_to_exits(make_user):
    with pytest.raises(SystemExit):
        newsletter.run("O", "C", test_to="nessuno@example.com", out=lambda *_: None)
