"""Invio email via SMTP (qualsiasi provider: Gmail con password per app, Brevo, Mailgun, ecc.)."""
import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr

from src import config
from src.auth import unsubscribe_url

log = logging.getLogger(__name__)

SMTP_TIMEOUT_SECONDS = 20


def send_email(to: str, subject: str, body: str, headers: dict[str, str] | None = None) -> bool:
    """
    Invia un'email di testo. Restituisce True se consegnata al server SMTP.
    Non solleva mai eccezioni: un errore di posta non deve rompere la richiesta dell'utente.
    """
    if not config.SMTP_ENABLED:
        # Modalità sviluppo: mostra il messaggio nel log (compresi i link) invece di inviarlo.
        log.warning("SMTP non configurato, email NON inviata.\nA: %s\nOggetto: %s\n\n%s", to, subject, body)
        return False

    message = EmailMessage()
    message["From"] = config.SMTP_FROM
    message["To"] = to
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain=parseaddr(config.SMTP_FROM)[1].split("@")[-1] or None)
    for name, value in (headers or {}).items():
        message[name] = value
    message.set_content(body)

    try:
        if config.SMTP_PORT == 465:
            client = smtplib.SMTP_SSL(
                config.SMTP_HOST, config.SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS,
                context=ssl.create_default_context(),
            )
        else:
            client = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS)
        with client:
            if config.SMTP_PORT != 465 and config.SMTP_STARTTLS:
                client.starttls(context=ssl.create_default_context())
            if config.SMTP_USER:
                client.login(config.SMTP_USER, config.SMTP_PASSWORD)
            client.send_message(message)
        return True
    except Exception:
        # Niente corpo del messaggio nel log: può contenere link con token.
        log.exception("Invio email a %s non riuscito", to)
        return False


def send_verification_email(to: str, token: str) -> bool:
    link = f"{config.BASE_URL}/#verify={token}"
    return send_email(
        to,
        "Conferma il tuo indirizzo email - Gym Tracker",
        "Ciao!\n\n"
        "Grazie per esserti registrato su Gym Tracker.\n"
        "Per confermare il tuo indirizzo email apri questo link (valido 48 ore):\n\n"
        f"{link}\n\n"
        "Se non hai creato tu l'account, ignora questo messaggio.",
    )


def send_password_reset_email(to: str, token: str) -> bool:
    link = f"{config.BASE_URL}/#reset={token}"
    return send_email(
        to,
        "Reimposta la tua password - Gym Tracker",
        "Ciao!\n\n"
        "Abbiamo ricevuto una richiesta di reimpostazione della password.\n"
        "Per sceglierne una nuova apri questo link (valido 1 ora, utilizzabile una sola volta):\n\n"
        f"{link}\n\n"
        "Se non l'hai richiesto tu, ignora questo messaggio: la tua password non cambierà.",
    )


def send_newsletter_email(to: str, user_id: int, subject: str, body: str) -> bool:
    """
    Email di novità. Ogni messaggio contiene il link di disiscrizione nel testo e le intestazioni
    List-Unsubscribe (con "one-click"), che i client di posta mostrano come pulsante "Annulla iscrizione".
    """
    link = unsubscribe_url(user_id)
    footer = (
        "\n\n--\n"
        "Ricevi questa email perché hai scelto di ricevere novità su Gym Tracker.\n"
        f"Per non riceverne più: {link}"
    )
    return send_email(
        to,
        subject,
        body.rstrip() + footer,
        headers={
            "List-Unsubscribe": f"<{link}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
    )
