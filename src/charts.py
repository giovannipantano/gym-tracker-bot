import io
import matplotlib
matplotlib.use("Agg")  # Backend non interattivo (headless)
import matplotlib.pyplot as plt
from datetime import datetime

def generate_progression_chart(exercise_name: str, records: list) -> io.BytesIO | None:
    if not records:
        return None

    # Calcolo massimale stimato (Epley: peso * (1 + reps/30))
    daily_best = {}
    for date_str, weight, reps in records:
        day = date_str[:10]  # YYYY-MM-DD
        est_1rm = weight * (1 + (reps / 30.0)) if reps > 1 else weight
        if day not in daily_best or est_1rm > daily_best[day]:
            daily_best[day] = est_1rm

    days = list(daily_best.keys())
    values = list(daily_best.values())

    plt.figure(figsize=(8, 4.5), dpi=130)
    plt.plot(days, values, marker="o", color="#2a75d3", linewidth=2, markersize=6)
    plt.title(f"Progressione 1RM Stimato: {exercise_name.title()}", fontsize=13, pad=12)
    plt.xlabel("Data", fontsize=10)
    plt.ylabel("1RM Stimato (kg)", fontsize=10)
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.xticks(rotation=35, ha="right", fontsize=9)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close()
    buf.seek(0)
    return buf