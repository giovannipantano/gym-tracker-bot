WORKOUT_ROUTINES = {
    "Push": {
        "text": (
            "📋 <b>Scheda PUSH</b>\n\n"
            "• Panca: 6 rep + 2 back off\n"
            "• Alzate laterali manubrio: 2xmax\n"
            "• Panca 70: 8-10 rep + 2 back off\n"
            "• Alzate laterali cavo: 2xmax\n"
            "• Croci cavi: 3xmax\n"
            "• Push down: 2xmax"
        ),
        "exercises": [
            "Panca",
            "Alzate laterali manubrio",
            "Panca 70",
            "Alzate laterali cavo",
            "Croci cavi",
            "Push down"
        ]
    },
    "Pull": {
        "text": (
            "📋 <b>Scheda PULL</b>\n\n"
            "• Trazioni zavorrate: 5 rep + 2 back off\n"
            "• Pulley: 3xmax\n"
            "• Rematore manubrio: 2xmax\n"
            "• Del posteriori cavo: 3xmax\n"
            "• Curl ez: 6-8 rep + 2 back off\n"
            "• Curl martello: 2xmax"
        ),
        "exercises": [
            "Trazioni zavorrate",
            "Pulley",
            "Rematore manubrio",
            "Del posteriori cavo",
            "Curl ez",
            "Curl martello"
        ]
    },
    "Legs": {
        "text": (
            "📋 <b>Scheda LEGS</b>\n\n"
            "• Squat: 6 rep + 2 back off\n"
            "• Leg extension: 3xmax\n"
            "• Stacco rumeno: 8 rep + 2 back off\n"
            "• Leg curl: 3xmax\n"
            "• Calf: 2xmax\n"
            "• Copenhagen plank"
        ),
        "exercises": [
            "Squat",
            "Leg extension",
            "Stacco rumeno",
            "Leg curl",
            "Calf",
            "Copenhagen plank"
        ]
    },
    "Upper": {
        "text": (
            "📋 <b>Scheda UPPER</b>\n\n"
            "• Dips zavorrati: 6-8 rep + 2 back off\n"
            "• Rematore bilanciere: 6-8 rep + 2 back off\n"
            "• Croci panca inclinata: 3xmax\n"
            "• Trazioni: 3xmax\n"
            "• Alzate laterali: 2xmax\n"
            "• Del posteriori: 2xmax\n"
            "• Tricipiti overhead: 2xmax\n"
            "• Curl su panca inclinata: 3xmax"
        ),
        "exercises": [
            "Dips zavorrati",
            "Rematore bilanciere",
            "Croci panca inclinata",
            "Trazioni",
            "Alzate laterali",
            "Del posteriori",
            "Tricipiti overhead",
            "Curl su panca inclinata"
        ]
    },
    "Lower": {
        "text": (
            "📋 <b>Scheda LOWER</b>\n\n"
            "• Leg press: 10 rep + 2 back off\n"
            "• Affondi bulgari: 2xmax\n"
            "• Hip thrust: 3xmax\n"
            "• Iper estensioni: 2xmax\n"
            "• Calf: 2xmax\n"
            "• Copenhagen plank"
        ),
        "exercises": [
            "Leg press",
            "Affondi bulgari",
            "Hip thrust",
            "Iper estensioni",
            "Calf",
            "Copenhagen plank"
        ]
    }
}

def get_routine_text(split_name: str) -> str:
    routine = WORKOUT_ROUTINES.get(split_name)
    return routine["text"] if routine else f"📋 <b>Scheda {split_name}</b>"

def get_exercises_for_split(split_name: str) -> list[str]:
    routine = WORKOUT_ROUTINES.get(split_name)
    return routine["exercises"] if routine else []