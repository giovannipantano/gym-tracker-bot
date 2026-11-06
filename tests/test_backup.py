"""Backup: copia locale verificata, rotazione e caricamento esterno con rclone (simulato)."""
import importlib
import os
import sqlite3
import stat

import pytest


@pytest.fixture
def backup(tmp_path, monkeypatch):
    db = tmp_path / "src.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE t (x)")
    conn.execute("INSERT INTO t VALUES (1)")
    conn.commit()
    conn.close()
    monkeypatch.setenv("DATABASE_PATH", str(db))
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "bk"))
    monkeypatch.setenv("BACKUP_KEEP", "2")
    monkeypatch.setenv("BACKUP_REMOTE", "")
    import scripts.backup_db as mod
    return importlib.reload(mod)


def test_local_backup_is_valid_and_rotated(backup):
    import time
    for _ in range(3):
        created = backup.run_backup()
        assert created is not None
        time.sleep(1.1)
    files = sorted(backup.BACKUP_DIR.glob("workout_tracker_*.db"))
    assert len(files) == 2
    assert sqlite3.connect(files[-1]).execute("SELECT x FROM t").fetchone() == (1,)


def test_missing_database(backup, tmp_path):
    backup.DB_PATH = tmp_path / "nope.db"
    assert backup.run_backup() is None


def test_offsite_noop_without_remote(backup):
    assert backup.upload_offsite(backup.run_backup()) is True


def _fake_rclone(tmp_path, monkeypatch, exit_code):
    log = tmp_path / "rclone.log"
    script = tmp_path / "bin" / "rclone"
    script.parent.mkdir()
    script.write_text(f'#!/bin/sh\necho "$@" >> {log}\nexit {exit_code}\n')
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{script.parent}{os.pathsep}{os.environ['PATH']}")
    return log


def test_offsite_uploads_then_prunes(backup, tmp_path, monkeypatch):
    log = _fake_rclone(tmp_path, monkeypatch, 0)
    target = backup.run_backup()
    assert backup.upload_offsite(target, "remoto:gym") is True
    lines = log.read_text().splitlines()
    assert lines[0] == f"copy {target} remoto:gym"
    assert lines[1].startswith("delete remoto:gym --min-age 30d")


def test_offsite_failure_is_reported(backup, tmp_path, monkeypatch, capsys):
    _fake_rclone(tmp_path, monkeypatch, 1)
    assert backup.upload_offsite(backup.run_backup(), "remoto:gym") is False
    assert "Errore nella copia remota" in capsys.readouterr().out


def test_offsite_without_rclone_installed(backup, monkeypatch, capsys):
    monkeypatch.setenv("PATH", "/nonexistent")
    assert backup.upload_offsite(backup.run_backup(), "remoto:gym") is False
    assert "rclone non è installato" in capsys.readouterr().out
