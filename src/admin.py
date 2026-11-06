"""Statistiche d'uso per la pagina /admin: solo conteggi aggregati, mai dati personali."""
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src import config
from src.database import get_connection

SERIES_DAYS = 30


def _backup_dir() -> Path:
    return Path(config.BACKUP_DIR)


def _scalar(conn, sql: str, params=()) -> int:
    return conn.execute(sql, params).fetchone()[0] or 0


def _daily_series(conn, sql: str, days: int) -> list[dict]:
    """Conteggi per giorno degli ultimi `days` giorni (UTC), con 0 nei giorni vuoti."""
    counts = {row[0]: row[1] for row in conn.execute(sql, (f"-{days - 1} days",))}
    today = datetime.now(timezone.utc).date()
    out = []
    for i in range(days - 1, -1, -1):
        day = (today - timedelta(days=i)).isoformat()
        out.append({"date": day, "count": counts.get(day, 0)})
    return out


def backup_info() -> dict:
    files = sorted(_backup_dir().glob("workout_tracker_*.db")) if _backup_dir().exists() else []
    if not files:
        return {"count": 0, "latest": None, "latest_age_hours": None}
    newest = files[-1]
    mtime = datetime.fromtimestamp(newest.stat().st_mtime, tz=timezone.utc)
    age = (datetime.now(timezone.utc) - mtime).total_seconds() / 3600
    return {"count": len(files), "latest": mtime.strftime("%Y-%m-%d %H:%M UTC"), "latest_age_hours": round(age, 1)}


def collect_stats() -> dict:
    with get_connection() as conn:
        users = {
            "total": _scalar(conn, "SELECT COUNT(*) FROM users"),
            "verified": _scalar(conn, "SELECT COUNT(*) FROM users WHERE email_verified_at IS NOT NULL"),
            "newsletter": _scalar(conn, "SELECT COUNT(*) FROM users WHERE marketing_opt_in = 1"),
            "new_7d": _scalar(conn, "SELECT COUNT(*) FROM users WHERE created_at >= datetime('now', '-7 days')"),
            "new_30d": _scalar(conn, "SELECT COUNT(*) FROM users WHERE created_at >= datetime('now', '-30 days')"),
            # last_used_at si aggiorna al massimo una volta all'ora: va bene per "attivi" su base giornaliera
            "active_1d": _scalar(conn, "SELECT COUNT(DISTINCT user_id) FROM sessions WHERE last_used_at >= datetime('now', '-1 day')"),
            "active_7d": _scalar(conn, "SELECT COUNT(DISTINCT user_id) FROM sessions WHERE last_used_at >= datetime('now', '-7 days')"),
            "active_30d": _scalar(conn, "SELECT COUNT(DISTINCT user_id) FROM sessions WHERE last_used_at >= datetime('now', '-30 days')"),
        }
        workouts = {
            "completed": _scalar(conn, "SELECT COUNT(*) FROM workouts WHERE is_active = 0"),
            "in_progress": _scalar(conn, "SELECT COUNT(*) FROM workouts WHERE is_active = 1"),
            "last_7d": _scalar(conn, "SELECT COUNT(*) FROM workouts WHERE is_active = 0 AND start_time >= datetime('now', '-7 days')"),
            "last_30d": _scalar(conn, "SELECT COUNT(*) FROM workouts WHERE is_active = 0 AND start_time >= datetime('now', '-30 days')"),
            "sets": _scalar(conn, "SELECT COUNT(*) FROM sets"),
            "routines": _scalar(conn, "SELECT COUNT(*) FROM routines"),
            "body_weights": _scalar(conn, "SELECT COUNT(*) FROM body_weights"),
        }
        signups = _daily_series(
            conn, "SELECT date(created_at), COUNT(*) FROM users WHERE created_at >= datetime('now', ?) GROUP BY 1", SERIES_DAYS)
        workouts_daily = _daily_series(
            conn, "SELECT date(start_time), COUNT(*) FROM workouts WHERE is_active = 0 AND start_time >= datetime('now', ?) GROUP BY 1", SERIES_DAYS)

    db_path = Path(config.DATABASE_PATH)
    disk = shutil.disk_usage(db_path.parent)
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "users": users,
        "workouts": workouts,
        "signups_daily": signups,
        "workouts_daily": workouts_daily,
        "system": {
            "db_size_mb": round(db_path.stat().st_size / 1e6, 2) if db_path.exists() else 0,
            "disk_free_gb": round(disk.free / 1e9, 1),
            "disk_used_pct": round(disk.used / disk.total * 100),
            "smtp_enabled": config.SMTP_ENABLED,
            "backup": backup_info(),
        },
    }
