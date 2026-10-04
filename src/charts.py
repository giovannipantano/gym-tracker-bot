import io
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

def generate_progression_chart(exercise_name: str, records: list) -> io.BytesIO | None:
    if not records:
        return None

    # Calcolo massimale stimato giornaliero (formula di Epley)
    daily_best = {}
    for record in records:
        date_str, weight, reps = record[0], record[1], record[2]
        day = date_str[:10]  # Formato YYYY-MM-DD
        est_1rm = weight * (1.0 + (reps / 30.0)) if reps > 1 else weight
        if day not in daily_best or est_1rm > daily_best[day]:
            daily_best[day] = round(est_1rm, 1)

    days = list(daily_best.keys())
    values = list(daily_best.values())

    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=130)
    ax.plot(days, values, marker="o", color="#2a75d3", linewidth=2.5, markersize=8, label="1RM Stimato")
    
    # Valori numerici sopra i marker
    for x, y in zip(days, values):
        ax.annotate(f"{y} kg", (x, y), textcoords="offset points", xytext=(0, 9), ha="center", fontsize=9, weight="bold")

    ax.set_title(f"Progressione: {exercise_name.title()}", fontsize=13, pad=14, weight="bold")
    ax.set_xlabel("Data", fontsize=10, labelpad=8)
    ax.set_ylabel("1RM Stimato (kg)", fontsize=10, labelpad=8)
    ax.grid(True, linestyle="--", alpha=0.5)

    if len(days) == 1:
        # Assicura margini adeguati se è presente una sola misurazione
        ax.set_xlim(-0.5, 0.5)
        ax.set_ylim(values[0] * 0.9, values[0] * 1.1)
    else:
        plt.xticks(rotation=30, ha="right", fontsize=9)

    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf