"""
Invia un'email di novità agli utenti che hanno dato il consenso.

Riceve SOLO chi ha (1) verificato l'email e (2) spuntato "Voglio ricevere novità" (o riattivato
l'opzione dall'account). Ogni messaggio contiene il link di disiscrizione.

Esempi (dalla radice del progetto, con l'ambiente virtuale attivo):
    python3 scripts/send_newsletter.py --subject "Novità" --body-file novita.txt --dry-run
    python3 scripts/send_newsletter.py --subject "Novità" --body-file novita.txt --test-to tu@esempio.it
    python3 scripts/send_newsletter.py --subject "Novità" --body-file novita.txt
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config, users  # noqa: E402
from src.database import init_db  # noqa: E402
from src.emailer import send_newsletter_email  # noqa: E402


def run(subject: str, body: str, *, dry_run=False, delay=1.0, test_to=None,
        send=send_newsletter_email, sleep=time.sleep, out=print) -> tuple[int, int]:
    """Invia (o simula) la newsletter. Restituisce (inviate, fallite)."""
    if test_to:
        user = users.get_user_by_email(test_to.strip().lower())
        if user is None:
            raise SystemExit(f"Nessun utente registrato con l'email {test_to}")
        recipients = [{"id": user["id"], "email": user["email"]}]
    else:
        recipients = users.list_newsletter_recipients()

    out(f"Destinatari: {len(recipients)}")
    if dry_run:
        for r in recipients:
            out(f"  [simulazione] {r['email']}")
        return 0, 0

    sent = failed = 0
    for i, recipient in enumerate(recipients):
        if i and delay:
            sleep(delay)  # rispetta i limiti di invio del provider SMTP
        if send(recipient["email"], recipient["id"], subject, body):
            sent += 1
            out(f"  inviata a {recipient['email']}")
        else:
            failed += 1
            out(f"  ERRORE con {recipient['email']}")
    return sent, failed


def main() -> int:
    parser = argparse.ArgumentParser(description="Invia un'email di novità agli utenti iscritti.")
    parser.add_argument("--subject", required=True, help="Oggetto dell'email")
    parser.add_argument("--body-file", required=True, help="File di testo con il contenuto dell'email")
    parser.add_argument("--dry-run", action="store_true", help="Mostra i destinatari senza inviare nulla")
    parser.add_argument("--test-to", metavar="EMAIL", help="Invia solo a questo utente registrato (prova)")
    parser.add_argument("--delay", type=float, default=1.0, help="Secondi tra un invio e l'altro (default 1)")
    parser.add_argument("--yes", action="store_true", help="Non chiedere conferma")
    args = parser.parse_args()

    body = Path(args.body_file).read_text(encoding="utf-8")
    if not body.strip():
        print("Il file del messaggio è vuoto.")
        return 1
    if not args.dry_run and not config.SMTP_ENABLED:
        print("SMTP non configurato nel file .env: impossibile inviare email.")
        return 1

    init_db()
    if not args.dry_run and not args.test_to and not args.yes:
        count = len(users.list_newsletter_recipients())
        if input(f"Inviare «{args.subject}» a {count} destinatari? [s/N] ").strip().lower() not in {"s", "si", "sì", "y"}:
            print("Annullato.")
            return 0

    sent, failed = run(args.subject, body, dry_run=args.dry_run, delay=args.delay, test_to=args.test_to)
    if not args.dry_run:
        print(f"Fatto: {sent} inviate, {failed} non riuscite.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
