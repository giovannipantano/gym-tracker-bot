# Gym Tracker

App web (PWA, installabile su iPhone) per registrare gli allenamenti. Ogni persona ha il proprio account
(email + password), le proprie schede e i propri dati. Backend FastAPI + SQLite.

Funzioni: account con verifica email e recupero password · schede personali (editor, import CSV, schede di esempio)
· registrazione serie (peso × ripetizioni o secondi) · storico · progressi (1RM stimato, volume, carico massimo)
· volume settimanale per gruppo muscolare · esportazione ed eliminazione dell'account · email di novità solo con consenso.

## Avvio

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # poi compila SECRET_KEY e BASE_URL
python -m src.main        # http://127.0.0.1:8000
```

L'app ascolta solo su `127.0.0.1`: in produzione mettila dietro un reverse proxy HTTPS (es. Caddy), che
inoltra `X-Forwarded-For`. Senza HTTPS la PWA non si installa e il Service Worker non parte.

Esempio di servizio systemd:

```ini
[Service]
WorkingDirectory=/home/utente/gym-tracker-bot
ExecStart=/home/utente/gym-tracker-bot/.venv/bin/python -m src.main
Restart=always
```

## Configurazione

Tutte le variabili sono documentate in `.env.example`. Le uniche obbligatorie sono `SECRET_KEY` e (in produzione) `BASE_URL`.
Le vecchie variabili `BOT_TOKEN`, `ALLOWED_USER_IDS` e `API_KEY` non servono più: Telegram è stato rimosso.

### Email (SMTP)
Serve un provider SMTP (Brevo, Mailgun, Gmail con "password per app", ecc.): compila `SMTP_*` nel `.env`.
Senza SMTP le email non partono ma il loro testo (con i link) compare nel log, utile in sviluppo.
Con `REQUIRE_EMAIL_VERIFICATION=true` l'SMTP è obbligatorio.

## Novità via email

Ricevono le novità solo gli utenti con **email verificata** e **consenso** (casella spuntata in registrazione o nell'Account).
Ogni email contiene il link di disiscrizione e le intestazioni `List-Unsubscribe`.

```bash
echo "Ciao! Ecco cosa c'è di nuovo..." > novita.txt
python3 scripts/send_newsletter.py --subject "Novità" --body-file novita.txt --dry-run            # elenca i destinatari
python3 scripts/send_newsletter.py --subject "Novità" --body-file novita.txt --test-to tu@esempio.it  # prova su di te
python3 scripts/send_newsletter.py --subject "Novità" --body-file novita.txt                      # invio reale (chiede conferma)
```

Le email di servizio (verifica, reset password) non sono "novità" e non richiedono consenso.

## Dati della versione a utente singolo

Dopo l'aggiornamento i vecchi allenamenti (senza proprietario) sono invisibili a tutti. Per riaverli:
registrati dall'app con la tua email, poi

```bash
python3 scripts/claim_legacy_data.py --email tu@esempio.it --seed-template
```

`--seed-template` aggiunge anche le schede Push/Pull/Legs/Upper/Lower di esempio.

## Backup

```bash
python3 scripts/backup_db.py     # es. da cron ogni notte
```

Crea copie verificate in `BACKUP_DIR` (ultime `BACKUP_KEEP`, permessi 0700). Non vanno più su Telegram: proteggono da errori,
**non dalla perdita del server**. Copia la cartella altrove con regolarità (rsync, rclone verso un cloud).

## Privacy

`src/web/privacy.html` è un **modello**: sostituisci i testi tra `[parentesi quadre]` con i tuoi dati prima di invitare altre persone.
Non è consulenza legale. L'app permette già agli utenti di esportare i dati, eliminare l'account e revocare il consenso.

## Test

```bash
pip install -r requirements-dev.txt
python -m pytest
```

## Formato CSV per importare le schede

```csv
scheda,esercizio,gruppo,note
Push,Panca,Petto,6 rep + 2 back off
Pull,Trazioni,Dorso,3xmax
```
Separatore virgola o punto e virgola; `gruppo` e `note` facoltativi (il gruppo, se manca, viene dedotto dal nome).
Una scheda con lo stesso nome viene aggiornata.
