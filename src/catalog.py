EXERCISE_CATALOG = {
    "Push": [
        "Panca Piana",
        "Panca Inclinata 70 Manubri",
        "Alzate Laterali Manubrio",
        "Pushdown",
        "Alzate Laterali Cavo",
        "Croci Cavi"
    ],
    "Pull": [
        "Trazioni Zavorrate",
        "Pulley",
        "Curl Bilanciere",
        "Hammer Curl",
        "Rematore Manubrio"
    ],
    "Legs": [
        "Squat",
        "Leg Extension",
        "Leg Curl",
        "Calf Raise",
        "Stacco Rumeno"
    ],
    "Upper": [
        "Dips Zavorrati",
        "Rematore con Bilanciere",
        "Croci Panca Inclinata",
        "Trazioni",
        "Alzate Laterali",
        "Del Posteriori",
        "Tricipiti Overhead",
        "Curl Panca Inclinata"
    ],
    "Lower": [
        "Leg Press",
        "Affondi Bulgari",
        "Calf Raise",
        "Hip Thrust",
        "Iperestensioni"
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