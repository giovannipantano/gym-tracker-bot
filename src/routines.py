"""Schede di allenamento dell'utente: creazione, modifica, eliminazione e importazione da CSV."""
import csv
import io
import sqlite3

from src.catalog import MUSCLE_GROUPS, DEFAULT_TEMPLATE, guess_muscle_group
from src.database import get_connection

MAX_ROUTINES = 30
MAX_EXERCISES = 40
MAX_CSV_CHARS = 200_000
MAX_CSV_ROWS = 2000


class RoutineError(ValueError):
    """Errore di validazione: il messaggio (in italiano) è pensato per essere mostrato all'utente."""


class DuplicateRoutine(RoutineError):
    """Esiste già una scheda con lo stesso nome."""


# Sinonimi accettati per il gruppo muscolare (oltre ai nomi italiani esatti)
_GROUP_SYNONYMS = {
    "chest": "Petto", "pecs": "Petto",
    "back": "Dorso", "lats": "Dorso", "schiena": "Dorso",
    "legs": "Gambe", "leg": "Gambe", "glutei": "Gambe", "quadricipiti": "Gambe",
    "shoulders": "Spalle", "shoulder": "Spalle", "deltoidi": "Spalle",
    "arms": "Braccia", "biceps": "Braccia", "triceps": "Braccia", "bicipiti": "Braccia", "tricipiti": "Braccia",
    "abs": "Addome", "core": "Addome", "addominali": "Addome",
    "other": "Altro",
}
_GROUPS_BY_LOWER = {g.lower(): g for g in MUSCLE_GROUPS}

_CSV_ALIASES = {
    "routine": {"scheda", "routine", "workout", "split", "giorno"},
    "exercise": {"esercizio", "exercise", "nome"},
    "group": {"gruppo", "gruppo_muscolare", "muscle_group", "muscle", "muscolo"},
    "note": {"note", "notes", "nota", "serie", "target"},
}


def _clean_text(value, max_len: int) -> str:
    return " ".join(str(value or "").split())[:max_len]


def _require_text(value, label: str, max_len: int) -> str:
    cleaned = " ".join(str(value or "").split())
    if not cleaned:
        raise RoutineError(f"{label} è obbligatorio")
    if len(cleaned) > max_len:
        raise RoutineError(f"{label} può avere al massimo {max_len} caratteri")
    return cleaned


def normalize_group(value) -> str | None:
    """Nome canonico del gruppo muscolare, o None se non riconosciuto."""
    key = str(value or "").strip().lower()
    return _GROUPS_BY_LOWER.get(key) or _GROUP_SYNONYMS.get(key)


def _clean_exercises(exercises) -> list[dict]:
    if not exercises:
        raise RoutineError("Aggiungi almeno un esercizio")
    if len(exercises) > MAX_EXERCISES:
        raise RoutineError(f"Una scheda può avere al massimo {MAX_EXERCISES} esercizi")

    cleaned, seen = [], set()
    for ex in exercises:
        name = _require_text(ex.get("name"), "Il nome dell'esercizio", 60)
        if name.casefold() in seen:
            raise RoutineError(f"Esercizio ripetuto nella scheda: {name}")
        seen.add(name.casefold())
        cleaned.append({
            "name": name,
            "muscle_group": normalize_group(ex.get("muscle_group")) or guess_muscle_group(name),
            "note": _clean_text(ex.get("note"), 120),
        })
    return cleaned


def _insert_routine(cursor, user_id: int, name: str, notes: str, exercises: list[dict]) -> int:
    cursor.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM routines WHERE user_id = ?", (user_id,))
    position = cursor.fetchone()[0]
    try:
        cursor.execute(
            "INSERT INTO routines (user_id, name, notes, position) VALUES (?, ?, ?, ?)",
            (user_id, name, notes, position)
        )
    except sqlite3.IntegrityError as e:
        raise DuplicateRoutine(f"Esiste già una scheda chiamata «{name}»") from e
    routine_id = cursor.lastrowid
    _replace_exercises(cursor, routine_id, exercises)
    return routine_id


def _replace_exercises(cursor, routine_id: int, exercises: list[dict]):
    cursor.execute("DELETE FROM routine_exercises WHERE routine_id = ?", (routine_id,))
    cursor.executemany(
        """INSERT INTO routine_exercises (routine_id, position, exercise_name, muscle_group, note)
           VALUES (?, ?, ?, ?, ?)""",
        [(routine_id, i, ex["name"], ex["muscle_group"], ex["note"]) for i, ex in enumerate(exercises)]
    )


def _count_routines(cursor, user_id: int) -> int:
    cursor.execute("SELECT COUNT(*) FROM routines WHERE user_id = ?", (user_id,))
    return cursor.fetchone()[0]


def list_routines(user_id: int) -> list[dict]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, notes, position FROM routines WHERE user_id = ? ORDER BY position, id",
            (user_id,)
        )
        routines = [
            {"id": r[0], "name": r[1], "notes": r[2], "position": r[3], "exercises": []}
            for r in cursor.fetchall()
        ]
        by_id = {r["id"]: r for r in routines}

        cursor.execute("""
            SELECT re.routine_id, re.exercise_name, re.muscle_group, re.note
            FROM routine_exercises re
            JOIN routines r ON r.id = re.routine_id
            WHERE r.user_id = ?
            ORDER BY re.routine_id, re.position, re.id
        """, (user_id,))
        for routine_id, name, group, note in cursor.fetchall():
            by_id[routine_id]["exercises"].append({"name": name, "muscle_group": group, "note": note})
    return routines


def get_routine(user_id: int, routine_id: int) -> dict | None:
    return next((r for r in list_routines(user_id) if r["id"] == routine_id), None)


def create_routine(user_id: int, name: str, notes: str, exercises: list[dict]) -> dict:
    name = _require_text(name, "Il nome della scheda", 50)
    notes = _clean_text(notes, 300)
    exercises = _clean_exercises(exercises)
    with get_connection() as conn:
        cursor = conn.cursor()
        if _count_routines(cursor, user_id) >= MAX_ROUTINES:
            raise RoutineError(f"Puoi avere al massimo {MAX_ROUTINES} schede")
        routine_id = _insert_routine(cursor, user_id, name, notes, exercises)
    return get_routine(user_id, routine_id)


def update_routine(user_id: int, routine_id: int, name: str, notes: str, exercises: list[dict]) -> dict | None:
    name = _require_text(name, "Il nome della scheda", 50)
    notes = _clean_text(notes, 300)
    exercises = _clean_exercises(exercises)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM routines WHERE id = ? AND user_id = ?", (routine_id, user_id))
        if cursor.fetchone() is None:
            return None
        try:
            cursor.execute("UPDATE routines SET name = ?, notes = ? WHERE id = ?", (name, notes, routine_id))
        except sqlite3.IntegrityError as e:
            raise DuplicateRoutine(f"Esiste già una scheda chiamata «{name}»") from e
        _replace_exercises(cursor, routine_id, exercises)
    return get_routine(user_id, routine_id)


def delete_routine(user_id: int, routine_id: int) -> bool:
    """Gli allenamenti già registrati restano nello storico (routine_id diventa NULL)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM routine_exercises WHERE routine_id IN (SELECT id FROM routines WHERE id = ? AND user_id = ?)",
            (routine_id, user_id)
        )
        cursor.execute(
            "UPDATE workouts SET routine_id = NULL WHERE routine_id = ? AND user_id = ?",
            (routine_id, user_id)
        )
        cursor.execute("DELETE FROM routines WHERE id = ? AND user_id = ?", (routine_id, user_id))
        return cursor.rowcount > 0


def seed_template(user_id: int) -> list[str]:
    """Aggiunge le schede di esempio che l'utente non ha già. Restituisce i nomi creati."""
    created = []
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM routines WHERE user_id = ?", (user_id,))
        existing = {row[0].casefold() for row in cursor.fetchall()}
        to_add = [r for r in DEFAULT_TEMPLATE if r["name"].casefold() not in existing]
        if len(existing) + len(to_add) > MAX_ROUTINES:
            raise RoutineError(f"Puoi avere al massimo {MAX_ROUTINES} schede")
        for routine in to_add:
            _insert_routine(cursor, user_id, routine["name"], routine["notes"], _clean_exercises(routine["exercises"]))
            created.append(routine["name"])
    return created


def _find_columns(header: list[str]) -> dict[str, int]:
    names = [h.strip().lower().lstrip("﻿") for h in header]
    columns = {}
    for field, aliases in _CSV_ALIASES.items():
        for i, name in enumerate(names):
            if name in aliases:
                columns[field] = i
                break
    return columns


def parse_routines_csv(text: str) -> dict[str, tuple[str, list[dict]]]:
    """
    Legge un CSV con colonne  scheda, esercizio  e (facoltative)  gruppo, note.
    Accetta virgola o punto e virgola come separatore (Excel italiano usa ';').
    Restituisce {nome_scheda_in_minuscolo: (nome_scheda, esercizi)} nell'ordine del file.
    """
    if len(text) > MAX_CSV_CHARS:
        raise RoutineError("Il file è troppo grande")
    text = text.lstrip("﻿").strip()
    if not text:
        raise RoutineError("Il CSV è vuoto")

    first_line = text.splitlines()[0]
    delimiter = ";" if first_line.count(";") > first_line.count(",") else ","
    try:
        rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    except csv.Error as e:
        raise RoutineError("CSV non valido") from e
    if len(rows) > MAX_CSV_ROWS:
        raise RoutineError("Il file ha troppe righe")

    columns = _find_columns(rows[0])
    if "routine" not in columns or "exercise" not in columns:
        raise RoutineError("Il CSV deve avere le colonne «scheda» ed «esercizio» (facoltative: «gruppo», «note»)")

    def cell(row, field):
        i = columns.get(field)
        return row[i] if i is not None and i < len(row) else ""

    grouped: dict[str, tuple[str, list[dict]]] = {}
    for line_no, row in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in row):
            continue
        routine_name = _clean_text(cell(row, "routine"), 50)
        if not routine_name:
            raise RoutineError(f"Riga {line_no}: manca il nome della scheda")
        key = routine_name.casefold()
        grouped.setdefault(key, (routine_name, []))[1].append({
            "name": cell(row, "exercise"),
            "muscle_group": cell(row, "group"),
            "note": cell(row, "note"),
        })

    if not grouped:
        raise RoutineError("Il CSV non contiene esercizi")
    return {key: (name, _clean_exercises(exs)) for key, (name, exs) in grouped.items()}


def import_routines_csv(user_id: int, text: str) -> dict[str, list[str]]:
    """
    Importa schede da CSV. Una scheda con lo stesso nome (senza distinguere maiuscole)
    viene aggiornata: i suoi esercizi sono sostituiti. Tutto o niente: se c'è un errore non cambia nulla.
    """
    parsed = parse_routines_csv(text)
    created, updated = [], []
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM routines WHERE user_id = ?", (user_id,))
        existing = {name.casefold(): routine_id for routine_id, name in cursor.fetchall()}
        if len(existing) + sum(1 for key in parsed if key not in existing) > MAX_ROUTINES:
            raise RoutineError(f"Puoi avere al massimo {MAX_ROUTINES} schede")
        for key, (name, exercises) in parsed.items():
            if key in existing:
                _replace_exercises(cursor, existing[key], exercises)
                updated.append(name)
            else:
                _insert_routine(cursor, user_id, name, "", exercises)
                created.append(name)
    return {"created": created, "updated": updated}
