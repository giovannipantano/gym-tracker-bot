from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from src.database import get_active_workout, start_new_workout, end_active_workout, log_sets_batch, get_workout_summary
from src.parser import parse_set_message

router = Router()

SPLITS = ["Push", "Pull", "Legs", "Upper", "Lower", "Full Body"]

@router.message(Command("start_workout"))
async def cmd_start_workout(message: Message):
    active = get_active_workout()
    if active:
        await message.answer(f"Hai già una sessione attiva ({active[1]}). Inviami /fine per chiuderla prima di aprirne una nuova.")
        return

    buttons = [
        [InlineKeyboardButton(text=split, callback_data=f"split:{split}")]
        for split in SPLITS
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("Seleziona lo split di oggi:", reply_markup=keyboard)

@router.callback_query(F.data.startswith("split:"))
async def on_split_selected(callback: CallbackQuery):
    split_name = callback.data.split(":")[1]
    start_new_workout(split_name)
    await callback.message.edit_text(
        f"Sessione **{split_name}** avviata!\n\n"
        "Registra i tuoi esercizi scrivendo ad esempio:\n"
        "• `panca 4x8 80`\n"
        "• `squat 100 8,8,7`\n\n"
        "Usa /fine per terminare la sessione.",
        parse_mode="Markdown"
    )
    await callback.answer()

@router.message(Command("fine"))
async def cmd_end_workout(message: Message):
    active = get_active_workout()
    if not active:
        await message.answer("Nessuna sessione attiva trovata.")
        return

    workout_id, split_name, _ = active
    summary = get_workout_summary(workout_id)
    end_active_workout(workout_id)

    if not summary:
        await message.answer(f"Sessione {split_name} terminata. Nessuna serie registrata.")
        return

    text = f"**Allenamento Concluso - {split_name}**\n\n"
    total_volume = 0
    for ex, sets_cnt, volume, max_w in summary:
        vol = volume or 0
        total_volume += vol
        text += f"• **{ex}**: {sets_cnt} serie | Max: {max_w}kg | Vol: {vol:,.0f}kg\n"

    text += f"\n**Volume Totale Sollevato:** {total_volume:,.0f} kg"
    await message.answer(text, parse_mode="Markdown")

@router.message(F.text)
async def handle_workout_set(message: Message):
    active = get_active_workout()
    if not active:
        return  # Ignora messaggi generici se non si è in allenamento

    parsed = parse_set_message(message.text)
    if not parsed:
        await message.answer(
            "Formato non riconosciuto. Esempi validi:\n"
            "• `panca 4x8 80` (4 serie da 8 con 80kg)\n"
            "• `squat 100 8,8,7` (carico fisso, serie variabili)"
        )
        return

    exercise, entries = parsed
    workout_id = active[0]
    log_sets_batch(workout_id, exercise, entries)

    summary_entries = ", ".join([f"{w}kg×{r}" for w, r in entries])
    await message.answer(f"Registrato: **{exercise}** [{summary_entries}]", parse_mode="Markdown")