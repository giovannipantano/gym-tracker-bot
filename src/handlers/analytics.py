from aiogram import Router
from aiogram.types import Message, BufferedInputFile
from aiogram.filters import Command, CommandStart
from src.database import get_exercise_history
from src.charts import generate_progression_chart

router = Router()

def get_guide_text() -> str:
    return (
        "📖 <b>Guida ai Comandi del Gym Tracker</b>\n\n"
        "<b>🏋️ Gestione Allenamento:</b>\n"
        "• /start_workout — Avvia una nuova sessione e seleziona lo split (Push, Pull, Legs...).\n"
        "• /fine — Termina la sessione corrente e restituisce il riassunto con tonnellaggio e carichi.\n\n"
        "<b>✍️ Come Registrare le Serie:</b>\n"
        "Mentre la sessione è aperta, scrivi direttamente in chat:\n"
        "• <code>panca 4x8 80</code> ➔ Registra 4 serie da 8 ripetizioni con 80 kg.\n"
        "• <code>squat 100 8,8,7</code> ➔ Registra 3 serie a 100 kg (rispettivamente 8, 8 e 7 rep).\n"
        "• <code>trazioni 15 3x6</code> ➔ Riconosce carichi e combinazioni di ripetizioni.\n\n"
        "<b>📈 Statistiche & Storico:</b>\n"
        "• /storico — Mostra gli ultimi workout effettuati con i pulsanti per ispezionare le serie.\n"
        "• /progressione [esercizio] — Genera il grafico dell'1RM stimato nel tempo.\n"
        "  <i>Esempio:</i> <code>/progressione panca</code> oppure <code>/progressione squat</code>\n\n"
        "• /help — Mostra di nuovo questo messaggio."
    )

@router.message(CommandStart())
@router.message(Command("help"))
async def cmd_start_and_help(message: Message):
    await message.answer(get_guide_text(), parse_mode="HTML")

@router.message(Command("progressione"))
async def cmd_progression(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "⚠️ Specifica il nome dell'esercizio da tracciare.\n\n"
            "<i>Esempi:</i>\n"
            "• <code>/progressione panca</code>\n"
            "• <code>/progressione squat</code>",
            parse_mode="HTML"
        )
        return

    query = parts[1].strip()
    records = get_exercise_history(query)

    if not records:
        await message.answer(
            f"❌ Nessun dato trovato per '<b>{query}</b>'.\n"
            "Assicurati di aver registrato almeno una serie con questo esercizio durante un allenamento.",
            parse_mode="HTML"
        )
        return

    matched_name = records[0][3]
    chart_buf = generate_progression_chart(matched_name, records)

    if not chart_buf:
        await message.answer("Errore nella generazione del grafico.")
        return

    photo_file = BufferedInputFile(chart_buf.getvalue(), filename=f"{matched_name}_progression.png")
    await message.answer_photo(
        photo=photo_file,
        caption=f"📈 Progressione 1RM stimato per <b>{matched_name}</b>",
        parse_mode="HTML"
    )