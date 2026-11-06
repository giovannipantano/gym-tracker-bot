"""Backup: copia locale verificata, rotazione e caricamento esterno con rclone (simulato)."""
import importlib
import sqlite3

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


def _fake_rclone(monkeypatch, backup, exit_code):
    """Simula rclone senza eseguire nulla (funziona su qualsiasi sistema, anche Windows)."""
    import subprocess
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if exit_code:
            raise subprocess.CalledProcessError(exit_code, cmd)

    monkeypatch.setattr(backup.shutil, "which", lambda name: "/usr/bin/rclone")
    monkeypatch.setattr(backup.subprocess, "run", fake_run)
    return calls


def test_offsite_uploads_then_prunes(backup, monkeypatch):
    calls = _fake_rclone(monkeypatch, backup, 0)
    target = backup.run_backup()
    assert backup.upload_offsite(target, "remoto:gym") is True
    assert calls[0] == ["/usr/bin/rclone", "copy", str(target), "remoto:gym"]
    assert calls[1][:3] == ["/usr/bin/rclone", "delete", "remoto:gym"] and "30d" in calls[1]


def test_offsite_failure_is_reported(backup, monkeypatch, capsys):
    _fake_rclone(monkeypatch, backup, 1)
    assert backup.upload_offsite(backup.run_backup(), "remoto:gym") is False
    assert "Errore nella copia remota" in capsys.readouterr().out


def test_offsite_without_rclone_installed(backup, monkeypatch, capsys):
    monkeypatch.setattr(backup.shutil, "which", lambda name: None)
    assert backup.upload_offsite(backup.run_backup(), "remoto:gym") is False
    assert "rclone non è installato" in capsys.readouterr().out
