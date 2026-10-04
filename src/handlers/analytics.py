from aiogram import Router
from aiogram.types import Message, BufferedInputFile
from aiogram.filters import Command, CommandStart
from src.database import get_exercise_history
from src.charts import generate_progression_chart

router = Router()

@router.message(CommandStart())
async def cmd_start_guide(message: Message):
    guide_text = (
        "<strong>Benvenuto nel tuo Gym Tracker Personale!</strong>\n\n"
        "Ecco una guida rapida ai comandi e alla sintassi:\n\n"
        "<strong>1. Gestione Sessione</strong>\n"
        "• <code>/start_workout</code> — Avvia l'allenamento scegliendo lo split.\n"
        "• <code>/fine</code> — Chiude la sessione e mostra il riassunto con tonnellaggio e carichi massimi.\n\n"
        "<strong>2. Come registrare le serie</strong>\n"
        "Mentre una sessione è attiva, invia semplicemente un messaggio con uno di questi formati:\n"
        "• <code>panca 4x8 80</code> (4 serie uguali da 8 rep con 80 kg)\n"
        "• <code>squat 100 8,8,7</code> (carico fisso da 100 kg con rep variabili)\n"
        "• <code>stacco 140 5</code> (serie singola: 5 rep a 140 kg)\n\n"
        "<strong>3. Statistiche e Grafici</strong>\n"
        "• <code>/progressione <esercizio></code> — Genera il grafico dell'1RM stimato nel tempo.\n"
        "  <em>Esempio:</em> <code>/progressione panca</code>"
    )
    await message.answer(guide_text, parse_mode="HTML")

@router.message(Command("progressione"))
async def cmd_progression(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Specifica il nome dell'esercizio.\n"
            "<em>Esempio:</em> <code>/progressione panca</code>",
            parse_mode="HTML"
        )
        return

    query = parts[1].strip()
    records = get_exercise_history(query)

    if not records:
        await message.answer(
            f"Nessun dato registrato trovato per '<strong>{query}</strong>'.\n"
            "Verifica di aver già registrato almeno una serie con questo nome in una sessione.",
            parse_mode="HTML"
        )
        return

    # Recupera il nome dell'esercizio trovato nel database
    matched_name = records[0][3]
    chart_buf = generate_progression_chart(matched_name, records)

    if not chart_buf:
        await message.answer("Errore durante la generazione del grafico.")
        return

    photo_file = BufferedInputFile(chart_buf.getvalue(), filename=f"{matched_name}_progressione.png")
    await message.answer_photo(
        photo=photo_file,
        caption=f"Curva di progressione (1RM Stimato) per <strong>{matched_name}</strong>",
        parse_mode="HTML"
    )