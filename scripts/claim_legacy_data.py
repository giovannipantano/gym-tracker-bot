"""
Assegna a un account gli allenamenti registrati con la versione a utente singolo.

Dopo l'aggiornamento il vecchio database contiene allenamenti senza proprietario: restano
invisibili a tutti finché non li assegni. Procedura:
  1. avvia la nuova versione e registrati dall'app con la tua email;
  2. esegui, dalla radice del progetto:
       python3 scripts/claim_legacy_data.py --email tu@esempio.it --seed-template

--seed-template aggiunge anche le schede Push/Pull/Legs/Upper/Lower di esempio al tuo account
(sono le stesse che erano scritte nel codice), così ritrovi la tua scheda e i gruppi muscolari.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import routines, users  # noqa: E402
from src.auth import normalize_email  # noqa: E402
from src.database import init_db  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Assegna i vecchi allenamenti a un account.")
    parser.add_argument("--email", required=True, help="Email dell'account che riceverà i dati")
    parser.add_argument("--seed-template", action="store_true", help="Aggiungi anche le schede di esempio")
    parser.add_argument("--yes", action="store_true", help="Non chiedere conferma")
    args = parser.parse_args()

    init_db()
    email = normalize_email(args.email)
    user = users.get_user_by_email(email) if email else None
    if user is None:
        print("Nessun account con questa email: registrati prima dall'app, poi riesegui il comando.")
        return 1

    pending = users.count_legacy_workouts()
    print(f"Allenamenti senza proprietario: {pending}")
    if pending and not args.yes:
        if input(f"Assegnarli a {user['email']}? [s/N] ").strip().lower() not in {"s", "si", "sì", "y"}:
            print("Annullato.")
            return 0

    claimed = users.claim_legacy_workouts(user["id"]) if pending else 0
    print(f"Assegnati {claimed} allenamenti a {user['email']}.")

    if args.seed_template:
        created = routines.seed_template(user["id"])
        print(f"Schede aggiunte: {', '.join(created) if created else 'nessuna (già presenti)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
