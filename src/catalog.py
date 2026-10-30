"""Cataloghi statici: gruppi muscolari, scheda di esempio e utilità sui nomi degli esercizi.

Le schede degli utenti NON sono più qui: vivono nel database (src/routines.py).
"""

MUSCLE_GROUPS = ["Petto", "Dorso", "Gambe", "Spalle", "Braccia", "Addome", "Altro"]

# Usata per proporre un gruppo muscolare quando l'utente non lo specifica.
# La corrispondenza usa il pattern più lungo contenuto nel nome dell'esercizio,
# quindi le voci specifiche ("curl su panca") vincono su quelle generiche ("panca", "curl").
EXERCISE_MUSCLE_MAP = {
    # Petto
    "panca": "Petto", "chest": "Petto", "croci": "Petto", "dip": "Petto", "push up": "Petto",
    # Dorso
    "trazioni": "Dorso", "lat machine": "Dorso", "pulley": "Dorso", "rematore": "Dorso", "row": "Dorso",
    "stacco": "Dorso", "iper": "Dorso",
    # Gambe
    "squat": "Gambe", "leg press": "Gambe", "leg extension": "Gambe", "leg curl": "Gambe", "affondi": "Gambe",
    "calf": "Gambe", "hip thrust": "Gambe",
    # Spalle
    "military": "Spalle", "shoulder": "Spalle", "lento": "Spalle", "alzate": "Spalle", "del posteriori": "Spalle",
    # Braccia
    "curl": "Braccia", "curl su panca": "Braccia", "french": "Braccia", "pushdown": "Braccia",
    "push down": "Braccia", "tricipiti": "Braccia",
    # Core
    "plank": "Addome", "crunch": "Addome", "leg raise": "Addome"
}


def guess_muscle_group(exercise_name: str) -> str:
    """Gruppo muscolare del pattern più lungo contenuto nel nome ('Altro' se nessuno)."""
    name = exercise_name.strip().lower()
    matches = [pattern for pattern in EXERCISE_MUSCLE_MAP if pattern in name]
    if not matches:
        return "Altro"
    return EXERCISE_MUSCLE_MAP[max(matches, key=len)]


def canonical_exercise_name(name: str, known_names=()) -> str:
    """
    Normalizza il nome di un esercizio: spazi ripuliti e, se coincide (senza distinzione tra
    maiuscole/minuscole) con uno dei nomi noti (gli esercizi delle schede dell'utente),
    usa quell'ortografia. Evita che "panca" e "Panca" diventino esercizi diversi.
    """
    cleaned = " ".join(name.split())
    key = cleaned.casefold()
    for known in known_names:
        if known.casefold() == key:
            return known
    return cleaned[:1].upper() + cleaned[1:]


# Scheda di esempio (Push / Pull / Legs / Upper / Lower) che ogni utente può importare
# con un tocco e poi modificare. (esercizio, nota)
_TEMPLATE_RAW = {
    "Push": [
        ("Panca", "6 rep + 2 back off"),
        ("Alzate laterali manubrio", "2xmax"),
        ("Panca 70", "8-10 rep + 2 back off"),
        ("Alzate laterali cavo", "2xmax"),
        ("Croci cavi", "3xmax"),
        ("Push down", "2xmax"),
    ],
    "Pull": [
        ("Trazioni zavorrate", "5 rep + 2 back off"),
        ("Pulley", "3xmax"),
        ("Rematore manubrio", "2xmax"),
        ("Del posteriori cavo", "3xmax"),
        ("Curl ez", "6-8 rep + 2 back off"),
        ("Curl martello", "2xmax"),
    ],
    "Legs": [
        ("Squat", "6 rep + 2 back off"),
        ("Leg extension", "3xmax"),
        ("Stacco rumeno", "8 rep + 2 back off"),
        ("Leg curl", "3xmax"),
        ("Calf", "2xmax"),
        ("Copenhagen plank", ""),
    ],
    "Upper": [
        ("Dips zavorrati", "6-8 rep + 2 back off"),
        ("Rematore bilanciere", "6-8 rep + 2 back off"),
        ("Croci panca inclinata", "3xmax"),
        ("Trazioni", "3xmax"),
        ("Alzate laterali", "2xmax"),
        ("Del posteriori", "2xmax"),
        ("Tricipiti overhead", "2xmax"),
        ("Curl su panca inclinata", "3xmax"),
    ],
    "Lower": [
        ("Leg press", "10 rep + 2 back off"),
        ("Affondi bulgari", "2xmax"),
        ("Hip thrust", "3xmax"),
        ("Iper estensioni", "2xmax"),
        ("Calf", "2xmax"),
        ("Copenhagen plank", ""),
    ],
}

DEFAULT_TEMPLATE = [
    {
        "name": routine_name,
        "notes": "",
        "exercises": [
            {"name": ex, "muscle_group": guess_muscle_group(ex), "note": note}
            for ex, note in exercises
        ],
    }
    for routine_name, exercises in _TEMPLATE_RAW.items()
]
