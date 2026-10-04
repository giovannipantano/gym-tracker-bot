import re

def parse_set_message(text: str) -> tuple[str, list[tuple[float, int]]] | None:
    """
    Riconosce formati tipo:
    - "panca 4x8 80" -> Panca: 4 serie da 8 a 80kg
    - "squat 100 8,8,7" -> Squat: 8@100kg, 8@100kg, 7@100kg
    - "stacco 140 5" -> Stacco: 1 serie da 5 a 140kg
    """
    text = text.strip()
    
    # 1. Formato standard NxR: " x "
    pattern_nxr = re.match(r"^([a-zA-Z\s]+)\s+(\d+)\s*[xX]\s*(\d+)\s+([\d\.]+)$", text)
    if pattern_nxr:
        ex, sets_count, reps, weight = pattern_nxr.groups()
        sets_count, reps, weight = int(sets_count), int(reps), float(weight)
        return ex.strip().title(), [(weight, reps)] * sets_count

    # 2. Formato variabile per reps: "  "
    pattern_var = re.match(r"^([a-zA-Z\s]+)\s+([\d\.]+)\s+([\d\s,]+)$", text)
    if pattern_var:
        ex, weight, reps_str = pattern_var.groups()
        weight = float(weight)
        reps_tokens = re.findall(r"\d+", reps_str)
        if reps_tokens:
            entries = [(weight, int(r)) for r in reps_tokens]
            return ex.strip().title(), entries

    return None