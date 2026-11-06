"""Peso corporeo: una misurazione al giorno per utente (una nuova nello stesso giorno sostituisce la precedente)."""
from datetime import date, datetime, timedelta, timezone

from src.database import get_connection

MIN_WEIGHT_KG = 20.0
MAX_WEIGHT_KG = 400.0
EARLIEST_DATE = date(2000, 1, 1)


class BodyWeightError(ValueError):
    """Dati non validi (messaggio in italiano, pronto da mostrare all'utente)."""


def _parse_date(value: str | None) -> date:
    today = datetime.now(timezone.utc).date()
    if not value:
        return today
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise BodyWeightError("Data non valida")
    # Un giorno di margine: nei fusi orari davanti a UTC la data locale può essere già "domani"
    if parsed > today + timedelta(days=1):
        raise BodyWeightError("La data non può essere nel futuro")
    if parsed < EARLIEST_DATE:
        raise BodyWeightError("Data troppo lontana nel tempo")
    return parsed


def save_weight(user_id: int, weight_kg: float, measured_on: str | None = None) -> dict:
    if not (MIN_WEIGHT_KG <= weight_kg <= MAX_WEIGHT_KG):
        raise BodyWeightError(f"Il peso deve essere tra {MIN_WEIGHT_KG:.0f} e {MAX_WEIGHT_KG:.0f} kg")
    day = _parse_date(measured_on).isoformat()
    weight = round(float(weight_kg), 1)
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO body_weights (user_id, measured_on, weight_kg) VALUES (?, ?, ?)
               ON CONFLICT (user_id, measured_on) DO UPDATE SET weight_kg = excluded.weight_kg""",
            (user_id, day, weight)
        )
    return {"date": day, "weight_kg": weight}


def list_weights(user_id: int, limit: int = 400) -> list[dict]:
    """Le misurazioni più recenti, in ordine cronologico (dalla più vecchia alla più recente)."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT measured_on, weight_kg FROM (
                   SELECT measured_on, weight_kg FROM body_weights
                   WHERE user_id = ? ORDER BY measured_on DESC LIMIT ?
               ) ORDER BY measured_on ASC""",
            (user_id, limit)
        ).fetchall()
    return [{"date": r[0], "weight_kg": r[1]} for r in rows]


def delete_weight(user_id: int, measured_on: str) -> bool:
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM body_weights WHERE user_id = ? AND measured_on = ?", (user_id, measured_on)
        )
        return cursor.rowcount > 0
