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
python3 scripts/backup_db.py
```

Crea una copia verificata in `BACKUP_DIR` (ultime `BACKUP_KEEP`, permessi 0700). Da sola protegge da errori e corruzioni,
**non dalla perdita del server**: per quello serve una copia fuori dal server.

### Backup notturno automatico

Sul server, `crontab -e` e aggiungi (ogni notte alle 03:15; sostituisci il percorso se diverso):

```
15 3 * * * cd /home/ubuntu/gym-tracker-bot && .venv/bin/python scripts/backup_db.py >> backups/backup.log 2>&1
```

Controllo: il giorno dopo la pagina `/admin` mostra "ultimo backup: N ore fa" (diventa arancione oltre 36 ore).

### Copia fuori dal server (rclone)

Il database contiene email e dati di tutti gli utenti: **cifra la copia** prima che esca dal server. rclone sa farlo
con una destinazione "crypt". Una volta sola, sul server:

```bash
sudo apt install rclone
rclone config      # 1) crea la destinazione cloud (es. Google Drive, Backblaze B2, Dropbox...) chiamata "cloud"
                   # 2) crea una destinazione di tipo "crypt" chiamata "cloudcrypt" che punta a  cloud:gym-backups
```

Poi nel `.env` del server:

```
BACKUP_REMOTE=cloudcrypt:
BACKUP_REMOTE_KEEP_DAYS=30
```

Da quel momento ogni backup notturno viene caricato (cifrato) e le copie remote più vecchie di 30 giorni vengono eliminate.
Provalo a mano con `python3 scripts/backup_db.py; echo $?`: `0` ok, `1` backup locale fallito, `2` copia remota fallita.
**Conserva la password di cifratura di rclone** (`rclone config show`) in un posto sicuro fuori dal server: senza,
le copie remote non si possono leggere.

Per ripristinare: scarica il file (`rclone copy cloudcrypt: ./ripristino`), ferma l'app (`sudo systemctl stop gymbot`),
sostituisci `workout_tracker.db` con la copia, riavvia (`sudo systemctl start gymbot`).

## Amministrazione e log

- **Statistiche**: metti la tua email in `ADMIN_EMAILS` nel `.env` e riavvia. Dopo l'accesso trovi il link nella scheda
  Account, oppure apri `/admin`: solo numeri (utenti, attivi, allenamenti, andamento a 30 giorni, backup, disco).
  Con SMTP attivo serve anche l'email verificata.
- **Log degli accessi**: ogni richiesta alle API lascia una riga con id utente, esito, durata e IP (mai email, password o token):
  `journalctl -u gymbot | grep gymbot.access`. Per vedere cosa ha fatto un utente:
  `journalctl -u gymbot | grep gymbot.access | grep "uid=3 "`. L'id di un utente si trova con
  `sqlite3 workout_tracker.db "SELECT id, email FROM users;"`.

## Privacy

`src/web/privacy.html` è un **modello**: sostituisci i testi tra `[parentesi quadre]` con i tuoi dati prima di invitare altre persone.
Non è consulenza legale. L'app permette già agli utenti di esportare i dati, eliminare l'account e revocare il consenso.

## Asset locali (senza CDN)

Per default la pagina carica Tailwind e Chart.js da CDN esterne. Per servirli dal tuo server (più veloce, funziona anche
se la CDN è irraggiungibile), sul tuo PC (serve Node.js 18+ e internet), dalla radice del progetto:

```bash
node scripts/build_assets.mjs
git add src/web/vendor && git commit -m "Aggiungi asset locali"
```

Il server li usa da solo non appena `src/web/vendor/tailwind.css` e `chart.umd.js` esistono; se mancano ricade sulle CDN.
Rilancia lo script quando aggiungi nuove classi Tailwind a `index.html`. Le icone si rigenerano con `python scripts/make_icons.py` (richiede Pillow).

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
