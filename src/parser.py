# src/parser.py
import re

def parse_set_data_only(text: str) -> list[tuple[float, int]] | None:
    """
    Riconosce solo la parte numerica quando l'esercizio è già selezionato:
    - "4x8 80" -> 4 serie da 8 rep con 80kg
    - "100 8,8,7" -> 3 serie a 100kg con 8, 8 e 7 rep
    - "80 8" -> 1 serie da 8 rep con 80kg
    """
    text = text.strip()

    # Formato NxR: "4x8 80"
    m_nxr = re.match(r"^(\d+)\s*[xX]\s*(\d+)\s+([\d\.]+)$", text)
    if m_nxr:
        sets_count, reps, weight = m_nxr.groups()
        return [(float(weight), int(reps))] * int(sets_count)

    # Formato carico fisso + rep: "100 8,8,7" o "80 8"
    m_var = re.match(r"^([\d\.]+)\s+([\d\s,]+)$", text)
    if m_var:
        weight, reps_str = m_var.groups()
        reps_tokens = re.findall(r"\d+", reps_str)
        if reps_tokens:
            return [(float(weight), int(r)) for r in reps_tokens]

    return None

def parse_set_message(text: str) -> tuple[str, list[tuple[float, int]]] | None:
    """Mantiene compatibilità se scrivi direttamente tutto assieme: 'panca 4x8 80'"""
    text = text.strip()
    
    pattern_nxr = re.match(r"^([a-zA-Z\s]+)\s+(\d+)\s*[xX]\s*(\d+)\s+([\d\.]+)$", text)
    if pattern_nxr:
        ex, sets_count, reps, weight = pattern_nxr.groups()
        return ex.strip().title(), [(float(weight), int(reps))] * int(sets_count)

    pattern_var = re.match(r"^([a-zA-Z\s]+)\s+([\d\.]+)\s+([\d\s,]+)$", text)
    if pattern_var:
        ex, weight, reps_str = pattern_var.groups()
        reps_tokens = re.findall(r"\d+", reps_str)
        if reps_tokens:
            return ex.strip().title(), [(float(weight), int(r)) for r in reps_tokens]

    return None