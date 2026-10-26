import re

def parse_set_data_only(text: str) -> list[tuple[float, int]]:
    """
    Estrae le serie a partire dal solo testo dei carichi/ripetizioni:
    - Con sovraccarico: '80kg 8, 8, 6' o '80 8 8 6' -> [(80.0, 8), (80.0, 8), (80.0, 6)]
    - Corpo libero (solo reps): '12, 10, 8' -> [(0.0, 12), (0.0, 10), (0.0, 8)]
    - Esercizi a tempo: '60s, 45s' -> [(0.0, 60), (0.0, 45)]
    """
    text = text.strip().lower()
    if not text:
        return []

    # 1. Caso tempi (es. '60s, 45s' o '1m, 30s')
    if "s" in text or "m" in text:
        entries = []
        for part in re.split(r'[\s,]+', text):
            sec = 0
            m = re.search(r'(\d+)m', part)
            if m:
                sec += int(m.group(1)) * 60
            s = re.search(r'(\d+)s', part)
            if s:
                sec += int(s.group(1))
            elif part.isdigit():
                sec += int(part)
            if sec > 0:
                entries.append((0.0, sec))
        return entries

    # 2. Caso con peso esplicito (es. '80kg 8 8 6' o '80 8,8,6')
    weight_match = re.search(r'^(\d+(?:\.\d+)?)\s*(?:kg|x)?\s+(.+)$', text)
    if weight_match:
        weight = float(weight_match.group(1))
        reps = [int(r) for r in re.findall(r'\b\d+\b', weight_match.group(2))]
        return [(weight, r) for r in reps]

    # 3. Caso corpo libero: solo ripetizioni (es. '12, 10, 8')
    reps = [int(r) for r in re.findall(r'\b\d+\b', text)]
    if reps:
        return [(0.0, r) for r in reps]

    return []


def parse_set_message(text: str) -> tuple[str, list[tuple[float, int]]] | None:
    """
    Interpreta un messaggio completo contenente nome esercizio e serie:
    - 'Panca piana: 80kg 8, 8, 6'
    - 'Squat 100 5, 5, 5'
    - 'Trazioni 10, 8, 8'
    - 'Plank 60s, 45s'
    """
    text = text.strip()
    if not text:
        return None

    # Separazione tramite due punti (es. "Panca piana: 80 8, 8")
    if ":" in text:
        exercise_part, sets_part = text.split(":", 1)
        sets = parse_set_data_only(sets_part)
        if exercise_part.strip() and sets:
            return exercise_part.strip(), sets

    # Separazione prima del primo blocco numerico (es. "Squat 100 5 5 5")
    match = re.search(r'^(.*?)\s*(\d+.*)$', text)
    if match:
        exercise_part = match.group(1).strip()
        sets_part = match.group(2).strip()
        sets = parse_set_data_only(sets_part)
        if exercise_part and sets:
            return exercise_part, sets

    return None