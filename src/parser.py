import re

def parse_set_data_only(text: str) -> list[dict]:
    text = text.strip().lower()
    entries = []
    
    # Caso 1: Esercizio a tempo (es. "60s, 45s", "1m, 30s")
    if "s" in text or "m" in text:
        parts = re.split(r'[\s,]+', text)
        for part in parts:
            if not part:
                continue
            sec = 0
            if "m" in part:
                m_match = re.search(r'(\d+)m', part)
                if m_match:
                    sec += int(m_match.group(1)) * 60
            if "s" in part:
                s_match = re.search(r'(\d+)s', part)
                if s_match:
                    sec += int(s_match.group(1))
            elif part.isdigit():
                sec += int(part)
            if sec > 0:
                entries.append({"weight": 0.0, "reps": 0, "duration": sec})
        return entries

    # Caso 2: Con peso specificato (es. "80kg 8,8,6" oppure "80 x 8, 8")
    weight_match = re.search(r'^(\d+(?:\.\d+)?)\s*(?:kg|x)?\s+(.+)$', text)
    if weight_match:
        weight = float(weight_match.group(1))
        reps_str = weight_match.group(2)
        reps_list = [int(r) for r in re.findall(r'\b\d+\b', reps_str)]
        return [{"weight": weight, "reps": r, "duration": None} for r in reps_list]

    # Caso 3: Solo ripetizioni (es. "10, 10, 8")
    reps_list = [int(r) for r in re.findall(r'\b\d+\b', text)]
    if reps_list:
        return [{"weight": 0.0, "reps": r, "duration": None} for r in reps_list]

    return []