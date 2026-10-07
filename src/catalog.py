EXERCISE_CATALOG = {
    "Push": [
        "Panca Piana Bilanciere",
        "Panca Inclinata Manubri",
        "Military Press",
        "Dips Zavorrati",
        "Alzate Laterali",
        "Pushdown",
        "French Press",
        "Alzate Laterali Cavo",
        "Croci Cavi",
        "Croci Panca Inclinata",
        "Tricipiti Overhead"
    ],
    "Pull": [
        "Stacco da Terra",
        "Trazioni Zavorrate",
        "Rematore con Bilanciere",
        "Pulley Basso",
        "Lat Machine",
        "Curl Bilanciere",
        "Hammer Curl",
        "Face Pull"
    ],
    "Legs": [
        "Squat con Bilanciere",
        "Leg Press",
        "Affondi con Manubri",
        "Leg Extension",
        "Leg Curl",
        "Calf Raise",
        "Hip Thrust",
        "Stacco Rumeno",
        "Iperestensioni"
    ],
    "Upper": [
        "Panca Piana Bilanciere",
        "Rematore con Bilanciere",
        "Military Press",
        "Trazioni alla Sbarra",
        "Dip alle Parallele",
        "Curl Manubri"
    ],
    "Lower": [
        "Squat con Bilanciere",
        "Stacco Rumeno",
        "Leg Press",
        "Leg Curl",
        "Calf Raise"
    ],
    "Full Body": [
        "Squat con Bilanciere",
        "Panca Piana Bilanciere",
        "Stacco da Terra",
        "Trazioni alla Sbarra",
        "Military Press"
    ]
}

def get_exercises_for_split(split_name: str) -> list[str]:
    return EXERCISE_CATALOG.get(split_name, EXERCISE_CATALOG["Full Body"])