# 🏋️ Workout Tracker Telegram Bot

Bot Telegram asincrono progettato per tracciare sessioni di allenamento con pesi in modo rapido e senza frizione da mobile (iPhone/Android/Desktop).

## ✨ Funzionalità

- **Avvio sessione guidato**: Selezione split da pulsantiera interattiva.
- **Inserimento rapido (Quick Log)**:
  - Formato serie uguali: `panca 4x8 80`
  - Formato serie scalari: `squat 100 8,8,7`
- **Riepilogo fine sessione**: Calcolo automatico di volume totale, massimi e serie per esercizio.
- **Grafici di progressione**: Generazione automatica in chat dei grafici di stima 1RM con `/progressione `.
- **Whitelisting di sicurezza**: Middleware integrato per consentire l'interazione solo al tuo account Telegram.

## ⚙️ Requisiti

- Python 3.11 o superiore
- Account Telegram

## 🚀 Setup Locale e Avvio

1. **Clona la repository**:
   ```bash
   git clone [https://github.com/](https://github.com/)/gym-tracker-bot.git
   cd gym-tracker-bot