from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from src.database import (
    get_active_workout, 
    start_new_workout, 
    end_active_workout, 
    log_sets_batch, 
    get_workout_summary,
    get_recent_workouts,
    get_workout_details
)
from src.parser import parse_set_message

router = Router()

SPLITS = ["Push", "Pull", "Legs", "Upper", "Lower", "Full Body"]

@router.message(Command("start_workout"))
async def cmd_start_workout(message: Message):
    active = get_active_workout()
    if active:
        await message.answer(
            f"⚠️ Hai già una sessione attiva (<b>{active[1]}</b>).\n"
            "Usa /fine per chiuderla prima di aprirne una nuova.",
            parse_mode="HTML"
        )
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
        f"🏋️ Sessione <b>{split_name}</b> avviata!\n\n"
        "Ora puoi registrare gli esercizi inviando messaggi rapidi:\n"
        "• <code>panca 4x8 80</code>\n"
        "• <code>squat 100 8,8,7</code>\n\n"
        "Quando termini, invia /fine.",
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(Command("fine"))
async def cmd_end_workout(message: Message):
    active = get_active_workout()
    if not active:
        await message.answer("Nessuna sessione attiva in corso. Usa /start_workout per iniziarne una.")
        return

    workout_id, split_name, _ = active
    summary = get_workout_summary(workout_id)
    end_active_workout(workout_id)

    if not summary:
        await message.answer(f"Sessione <b>{split_name}</b> terminata. Nessuna serie registrata.", parse_mode="HTML")
        return

    text = f"🏁 <b>Allenamento Concluso - {split_name}</b>\n\n"
    total_volume = 0
    for ex, sets_cnt, volume, max_w in summary:
        vol = volume or 0
        total_volume += vol
        text += f"• <b>{ex}</b>: {sets_cnt} serie | Max: {max_w}kg | Vol: {vol:,.0f}kg\n"

    text += f"\n📊 <b>Volume Totale:</b> {total_volume:,.0f} kg"
    await message.answer(text, parse_mode="HTML")

@router.message(Command("storico"))
async def cmd_history(message: Message):
    workouts = get_recent_workouts(limit=6)
    if not workouts:
        await message.answer("Non ci sono ancora sessioni registrate nello storico.")
        return

    text = "📋 <b>Ultimi Allenamenti Registrati:</b>\n\n"
    buttons = []
    for w_id, start_time, split_name, num_ex, total_sets, total_vol in workouts:
        date_short = start_time[:10]
        text += (
            f"📅 <b>{date_short}</b> — <b>{split_name}</b>\n"
            f"   └ {num_ex} esercizi | {total_sets} serie | Vol: {total_vol:,.0f} kg\n\n"
        )
        buttons.append([InlineKeyboardButton(text=f"Dettagli {date_short} ({split_name})", callback_data=f"w_detail:{w_id}")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

@router.callback_query(F.data.startswith("w_detail:"))
async def on_workout_detail(callback: CallbackQuery):
    workout_id = int(callback.data.split(":")[1])
    meta, sets = get_workout_details(workout_id)
    
    if not meta or not sets:
        await callback.answer("Dettagli non disponibili.", show_alert=True)
        return

    split_name, start_time, _ = meta
    date_str = start_time[:16].replace("T", " ")
    
    text = f"🔍 <b>Dettaglio Workout</b>: {split_name} ({date_str})\n\n"
    
    grouped = {}
    for ex, s_order, w, r in sets:
        grouped.setdefault(ex, []).append(f"{w}kg×{r}")

    for ex_name, s_list in grouped.items():
        text += f"• <b>{ex_name}</b>: {', '.join(s_list)}\n"

    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

# NOTA FONDAMENTALE: Escludiamo i comandi che iniziano con '/' per evitare che blocchino gli altri router
@router.message(F.text & ~F.text.startswith("/"))
async def handle_workout_set(message: Message):
    active = get_active_workout()
    if not active:
        await message.answer(
            "Non c'è nessun allenamento attivo al momento.\n"
            "Usa /start_workout per iniziare una sessione, oppure /help per la guida.",
            parse_mode="HTML"
        )
        return

    parsed = parse_set_message(message.text)
    if not parsed:
        await message.answer(
            "⚠️ Formato non riconosciuto. Esempi:\n"
            "• <code>panca 4x8 80</code> (4 serie uguali)\n"
            "• <code>squat 100 8,8,7</code> (serie variabili)",
            parse_mode="HTML"
        )
        return

    exercise, entries = parsed
    workout_id = active[0]
    log_sets_batch(workout_id, exercise, entries)

    summary_entries = ", ".join([f"{w}kg×{r}" for w, r in entries])
    await message.answer(f"✅ Registrato: <b>{exercise}</b> [{summary_entries}]", parse_mode="HTML")