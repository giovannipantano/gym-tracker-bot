# 🏋️‍♂️ Gym Tracker & Analytics (Telegram Bot + PWA)

Applicazione full-stack per il monitoraggio e l'analisi degli allenamenti, accessibile sia tramite **Bot Telegram** interattivo, sia come **Progressive Web App (PWA)** mobile-first ottimizzata per iOS (Safari). I dati sono sincronizzati in tempo reale su un unico database SQLite relazionale.

---

## ✨ Funzionalità Principali

### 📱 Progressive Web App (iOS Design System)
* **Design Nativo Apple:** Interfaccia scura pura (`#000000`), controlli a segmenti, layout ergonomico per l'uso con una sola mano e supporto alle *Safe Areas* di iPhone (Dynamic Island e Home Bar).
* **Supporto Offline:** Service Worker dedicato (`sw.js`) e Web App Manifest per memorizzazione in cache locale e avvio a schermo intero senza barra del browser.
* **Inserimento Flessibile:**
  * Sovraccarichi tradizionali (es. `80kg 8, 8, 6`).
  * Esercizi a corpo libero a peso zero (es. `12, 10, 8`).
  * Esercizi isometrici o a tempo (es. `60s, 45s` o `1m, 30s`).
* **Direct Progressive Overload:** Mostra in tempo reale la prestazione dell'ultima sessione completata quando viene selezionato un esercizio, evidenziando il target da superare.
* **Sicurezza:** Accesso protetto da PIN/API Key salvata in `localStorage` e verificata tramite header HTTP `X-API-Key`.

### 📊 Statistiche e Analytics Avanzate
* **Progressione 1RM:** Calcolo dinamico dell'1RM stimato (formula di Epley) con match esatto dei nomi per evitare collisioni tra varianti di esercizi (es. *Panca Piana* vs *Panca Inclinata*).
* **Switch Metriche:** Possibilità di visualizzare nel grafico:
  * 1RM Stimato (kg)
  * Volume Totale Sessione (kg)
  * Carico Massimo Sollevato (kg)
* **Volume Settimanale per Distretto:** Conteggio automatico delle serie allenanti completate negli ultimi 7 giorni raggruppate per gruppo muscolare (Petto, Dorso, Gambe, Spalle, Braccia, Addome).
* **Menu Dinamico Esercizi:** Popolamento automatico della lista esercizi derivato dall'unione tra catalogo predefinito e serie storiche registrate.

### 🤖 Bot Telegram (`aiogram v3`)
* Gestione rapida tramite comandi e tastiere inline.
* Parsing naturale dei messaggi di log (es. `Panca Piana: 80 8 8 6` o `Plank 60s 45s`).
* Riepiloghi immediati a fine sessione e visualizzazione dello storico.
* Accesso ristretto tramite whitelist di `user_id`.

### 🛡️ Affidabilità e DevOps
* **Backup Notturno su Telegram:** Script autonomo schedulato via `cron` che esegue un backup atomico a caldo di SQLite (`.backup`) e invia automaticamente il file `.db` al tuo account Telegram.
* **Reverse Proxy HTTPS:** Integrazione con Caddy Server e DuckDNS per certificati SSL automatici gestiti da Let's Encrypt.
* **Esecuzione H24:** Gestione del processo demone tramite `systemd`.

---

## 🛠️ Stack Tecnologico

* **Backend:** Python 3.12, FastAPI, Uvicorn
* **Telegram Framework:** aiogram v3
* **Database:** SQLite3 (con vincoli di integrità referenziale `PRAGMA foreign_keys = ON`)
* **Frontend Web:** HTML5, TailwindCSS (CDN), Chart.js, Vanilla ES6+
* **Infrastruttura:** Oracle Cloud Infrastructure (Ubuntu VPS), Caddy Server, systemd

---

## 📁 Struttura del Progetto

```text
gym-tracker-bot/
├── scripts/
│   └── backup_db.py         # Script per dump atomico e invio file su Telegram
├── src/
│   ├── handlers/
│   │   ├── analytics.py     # Gestori comandi analitici bot
│   │   └── workout.py       # Gestori sessione attiva bot
│   ├── web/
│   │   ├── index.html       # UI della PWA mobile-first
│   │   ├── manifest.json    # Configurazione installazione standalone PWA
│   │   └── sw.js            # Service worker per caching asset
│   ├── api.py               # Endpoint REST FastAPI protetti da API Key
│   ├── bot.py               # Entrypoint runner polling Telegram + FastAPI
│   ├── catalog.py           # Routine, schede e mappatura gruppi muscolari
│   ├── config.py            # Caricamento variabili d'ambiente (.env)
│   ├── database.py          # Query SQL, migrazioni e aggregazioni
│   └── parser.py            # Logica di estrazione carichi, reps e tempi
├── .env.example
├── requirements.txt
├── workout_tracker.db       # Database SQLite locale/produzione
└── README.md