# 🏋️‍♂️ Gym Tracker & Analytics (Telegram Bot + iOS PWA)

Piattaforma self-hosted per il tracciamento e l'analisi degli allenamenti contro resistenza, accessibile sia come **Progressive Web App (PWA)** mobile-first ottimizzata per iOS Safari, sia tramite **Bot Telegram** interattivo. Tutti i dati convergono in tempo reale su un unico database SQLite relazionale operante in modalità WAL.

---

## 🏗️ Architettura del Sistema

```text
[ Client iOS (Safari PWA) ]           [ Telegram App ]
            │                                │
            ▼ (HTTPS / TLS 1.3)              ▼ (HTTPS Polling)
   [ Caddy Reverse Proxy ]             [ Telegram Servers ]
    (Porte 80/443 + HSTS)                    │
            │                                │
            ▼ (127.0.0.1:8000)               │
    [ FastAPI Backend ] ◄────────────────────┘
            │          (aiogram v3 Polling)
            ▼
 [ SQLite Database (WAL Mode) ] ──(Cron 03:30)──► [ Backup DB Telegram ]
```

---

## ✨ Funzionalità

### 📱 Progressive Web App (Apple Design System)
* **Interfaccia Nativa iOS:** Palette Apple Dark (`#000000`), bordi continui, sfocature *frosted glass* (`backdrop-blur-2xl`), controlli a segmenti e supporto completo alle *Safe Areas* (Dynamic Island e Home Bar).
* **Supporto Offline (Service Worker):** Caching locale degli asset statici (`sw.js`) e manifest PWA standalone per avvio immediato a schermo intero anche in palestre prive di connettività.
* **Direct Progressive Overload:** Al tocco di un esercizio durante una sessione attiva, compare immediatamente il riepilogo delle serie e dei carichi eseguiti nell'ultima sessione completata.
* **Logging Multimodale:**
  * Sovraccarichi classici (es. `80kg 8, 8, 6` o `80 8 8 6`).
  * Esercizi a corpo libero a peso zero (es. `12, 10, 8`).
  * Esercizi a tempo / isometrici (es. `60s, 45s` o `1m, 30s`).

### 📊 Analytics & Metriche Avanzate
* **Progressione 1RM (Formula di Epley):** Calcolo dinamico del massimale stimato con matching esatto del nome esercizio per evitare collisioni tra varianti simili (es. *Panca Piana* vs *Panca Inclinata*).
* **Switch Metriche Interattivo:** Selettore a segmenti integrato con Chart.js per passare da **1RM Stimato**, a **Volume Totale (kg)** fino al **Carico Massimo (kg)** sollevato.
* **Volume Settimanale per Gruppo Muscolare:** Aggregazione automatica delle serie allenanti completate negli ultimi 7 giorni raggruppate per distretto (Petto, Dorso, Gambe, Spalle, Braccia, Addome).
* **Elenco Dinamico Esercizi:** Menu a tendina generato unendo gli esercizi definiti a catalogo con le serie effettivamente registrate nel database.

### 🤖 Bot Telegram (`aiogram v3`)
* Inserimento rapido delle serie tramite messaggi naturali (es. `Panca Piana: 80 8 8 6`).
* Visualizzazione istantanea del riepilogo a fine sessione.
* Controllo accessi rigoroso basato su whitelist di `user_id`.

### 🛡️ Sicurezza & Infrastruttura
* **Reverse Proxy Caddy:** Gestione e rinnovo automatico dei certificati TLS/SSL Let's Encrypt tramite DuckDNS con header HSTS (`Strict-Transport-Security`), `X-Frame-Options` e `X-Content-Type-Options`.
* **Isolamento Applicativo:** Uvicorn vincolato esclusivamente all'interfaccia di loopback locale `127.0.0.1:8000`.
* **Protezione Anti Brute-Force:** Rate-limiting applicativo in memoria su FastAPI con blocco temporaneo (15 minuti) dopo 5 tentativi consecutivi di PIN errato.
* **Intrusion Prevention:** Daemon Fail2ban a protezione del servizio SSH su Linux.
* **Affidabilità Database:** Concorrenza senza lock grazie a `PRAGMA journal_mode = WAL;` e vincoli referenziali `PRAGMA foreign_keys = ON;`.
* **Disaster Recovery Automatico:** Dump atomico a caldo SQLite (`.backup`) eseguito ogni notte alle 03:30 e recapitato come documento via Bot API su Telegram.

---

## 🛠️ Stack Tecnologico

* **Linguaggio & Runtime:** Python 3.12
* **Framework Web & API:** FastAPI, Uvicorn, Pydantic v2
* **Framework Bot:** aiogram v3
* **Database:** SQLite3 (WAL mode)
* **Frontend:** HTML5, TailwindCSS, Chart.js, Service Worker API
* **Web Server & SSL:** Caddy Server, Let's Encrypt, DuckDNS
* **Infrastruttura:** Oracle Cloud Infrastructure (Ubuntu Linux 24.04), systemd, Fail2ban

---

## 📁 Struttura della Repository

```text
gym-tracker-bot/
├── scripts/
│   └── backup_db.py         # Script per dump atomico e upload DB su Telegram
├── src/
│   ├── handlers/
│   │   ├── analytics.py     # Handler Telegram per comandi analitici
│   │   └── workout.py       # Handler Telegram per gestione workout attivo
│   ├── web/
│   │   ├── index.html       # UI iOS PWA (Apple Design System)
│   │   ├── manifest.json    # Metadati PWA per installazione standalone
│   │   └── sw.js            # Service Worker per caching e supporto offline
│   ├── api.py               # API REST FastAPI protette da PIN e rate limiter
│   ├── bot.py               # Entrypoint: avvio simultaneo Bot e Uvicorn
│   ├── catalog.py           # Definizioni routine e mappatura gruppi muscolari
│   ├── config.py            # Caricamento centralizzato variabili d'ambiente
│   ├── database.py          # Schema SQL, migrazioni e query analitiche
│   └── parser.py            # Parser stringhe serie, carichi, reps e tempi
├── .env.example             # Template variabili d'ambiente
├── requirements.txt         # Dipendenze Python
├── workout_tracker.db       # Database SQLite di produzione
└── README.md
```

---

## ⚙️ Variabili d'Ambiente

Crea un file `.env` nella radice del progetto:

```ini
TELEGRAM_BOT_TOKEN="123456789:ABCdefGHIjklMNOpqrSTUvwxYZ"
ALLOWED_USER_IDS="12345678"
DATABASE_PATH="workout_tracker.db"
API_KEY="il_tuo_pin_segreto"
```

---

## 🚀 Setup & Esecuzione Locale

1. **Clona la repository e crea l'ambiente virtuale:**
   ```bash
   git clone [https://github.com/tuo-username/gym-tracker-bot.git](https://github.com/tuo-username/gym-tracker-bot.git)
   cd gym-tracker-bot
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. **Installa le dipendenze:**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. **Avvia i servizi:**
   ```bash
   python3 -m src.bot
   ```
   * Il Bot Telegram entrerà in modalità polling.
   * La PWA e le API saranno raggiungibili su `http://127.0.0.1:8000`.

---

## 🌐 Deploy su VPS (Oracle Cloud)

### 1. Servizio Systemd (`gymbot.service`)
Crea `/etc/systemd/system/gymbot.service`:

```ini
[Unit]
Description=Gym Tracker Telegram Bot & FastAPI Server
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/gym-tracker-bot
ExecStart=/home/ubuntu/gym-tracker-bot/.venv/bin/python3 -m src.bot
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

Abilita e avvia:
```bash
sudo systemctl daemon-reload
sudo systemctl enable gymbot
sudo systemctl start gymbot
```

### 2. Configurazione Reverse Proxy Caddy
Installa Caddy e modifica `/etc/caddy/Caddyfile`:

```text
tuonome.duckdns.org {
    reverse_proxy 127.0.0.1:8000

    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
        X-Frame-Options "DENY"
        X-Content-Type-Options "nosniff"
        Referrer-Policy "strict-origin-when-cross-origin"
    }

    log {
        output file /var/log/caddy/gymbot_access.log
    }
}
```

Riavvia Caddy:
```bash
sudo systemctl restart caddy
```

### 3. Sicurezza Firewall e Fail2ban
Apri le porte `80` e `443` a livello iptables (oltre a impostare le Ingress Rules sulla VCN di Oracle Cloud):
```bash
sudo iptables -I INPUT 1 -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 1 -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

Proteggi la porta SSH da attacchi a forza bruta:
```bash
sudo apt install -y fail2ban
sudo systemctl enable --now fail2ban
```

---

## 📦 Backup Notturno su Telegram

Lo script `scripts/backup_db.py` genera una copia atomica a caldo del database SQLite tramite `src_conn.backup(dst_conn)` e la invia direttamente come allegato documentale al primo `user_id` specificato in `ALLOWED_USER_IDS`.

Pianifica il Cron job per le **03:30** ogni notte:

```bash
crontab -e
```

Aggiungi la riga:
```text
30 3 * * * /home/ubuntu/gym-tracker-bot/.venv/bin/python3 /home/ubuntu/gym-tracker-bot/scripts/backup_db.py >> /home/ubuntu/gym-tracker-bot/backup.log 2>&1
```

---

## 📲 Installazione PWA su iPhone

1. Apri **Safari** su iPhone e collegati all'indirizzo `https://tuonome.duckdns.org`.
2. Inserisci il PIN configurato nella variabile `API_KEY`.
3. Tocca il tasto **Condividi** di iOS (il quadrato con la freccia verso l'alto).
4. Scorri verso il basso e seleziona **Aggiungi alla schermata Home**.
5. Conferma con **Aggiungi**: l'applicazione verrà installata come PWA nativa, funzionante a schermo intero e con cache offline persistente.