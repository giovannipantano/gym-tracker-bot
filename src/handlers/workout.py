from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from src.database import (
    get_active_workout,
    start_new_workout,
    end_active_workout,
    log_sets_batch,
    get_workout_summary,
    get_recent_workouts,
    get_workout_details,
    delete_last_exercise_sets,
    delete_workout
)
from src.catalog import WORKOUT_ROUTINES, get_routine_text, get_exercises_for_split
from src.parser import parse_set_data_only, parse_set_message

router = Router()

class WorkoutState(StatesGroup):
    selecting_exercise = State()
    waiting_for_sets = State()

SPLITS = list(WORKOUT_ROUTINES.keys())

def build_exercise_keyboard(split_name: str) -> InlineKeyboardMarkup:
    exercises = get_exercises_for_split(split_name)
    buttons = [
        [InlineKeyboardButton(text=ex, callback_data=f"sel_ex:{ex}")]
        for ex in exercises
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@router.message(Command("start_workout"))
async def cmd_start_workout(message: Message, state: FSMContext):
    active = get_active_workout()
    if active:
        await message.answer(
            f"⚠️ Hai già una sessione attiva (**{active[1]}**).\n"
            "Usa /fine per chiuderla prima di aprirne una nuova.",
            parse_mode="HTML"
        )
        return

    buttons = [
        [InlineKeyboardButton(text=split, callback_data=f"split:{split}")]
        for split in SPLITS
    ]
    await message.answer("Seleziona lo split di oggi:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data.startswith("split:"))
async def on_split_selected(callback: CallbackQuery, state: FSMContext):
    split_name = callback.data.split(":")[1]
    start_new_workout(split_name)
    await state.set_state(WorkoutState.selecting_exercise)
    
    # 1. Recupera il testo della scheda formattato
    routine_text = get_routine_text(split_name)

    # 2. Modifica il messaggio con la scheda completa
    await callback.message.edit_text(
        f"🏋️ <b>Sessione {split_name} avviata!</b>\n\n"
        f"{routine_text}\n\n"
        "────────────────────\n"
        "Tocca l'esercizio che stai per eseguire:",
        reply_markup=build_exercise_keyboard(split_name),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("sel_ex:"))
async def on_exercise_selected(callback: CallbackQuery, state: FSMContext):
    exercise_name = callback.data.split(":", 1)[1]
    await state.update_data(current_exercise=exercise_name)
    await state.set_state(WorkoutState.waiting_for_sets)

    await callback.message.answer(
        f"🎯 Esercizio: **{exercise_name}**\n\n"
        "Invia carichi e ripetizioni in chat, ad esempio:\n"
        "• `4x8 80` (4 serie da 8 rep con 80kg)\n"
        "• `100 8,8,7` (carico 100kg con rep variabili)\n"
        "• `70 10` (serie singola: 10 rep a 70kg)",
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(Command("annulla"))
async def cmd_cancel_last(message: Message):
    active = get_active_workout()
    if not active:
        await message.answer("Nessuna sessione attiva in corso.", parse_mode="HTML")
        return

    res = delete_last_exercise_sets(active[0])
    if not res:
        await message.answer("Nessuna serie registrata da eliminare in questa sessione.", parse_mode="HTML")
        return

    ex_name, count = res
    await message.answer(f"🗑️ Rimosso l'ultimo esercizio: **{ex_name}** ({count} serie eliminate).", parse_mode="HTML")

@router.message(Command("elimina_workout"))
async def cmd_delete_workout_menu(message: Message):
    workouts = get_recent_workouts(limit=5)
    if not workouts:
        await message.answer("Nessun workout registrato trovato nello storico.", parse_mode="HTML")
        return

    buttons = [
        [InlineKeyboardButton(text=f"❌ Elimina {w[1][:10]} ({w[2]})", callback_data=f"del_w:{w[0]}")]
        for w in workouts
    ]
    await message.answer("Scegli quale workout eliminare definitivamente:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data.startswith("del_w:"))
async def on_delete_workout_confirm(callback: CallbackQuery):
    workout_id = int(callback.data.split(":")[1])
    success = delete_workout(workout_id)
    if success:
        await callback.message.edit_text("✅ Workout eliminato con successo dallo storico.")
    else:
        await callback.message.edit_text("Errore durante l'eliminazione o workout già rimosso.")
    await callback.answer()

@router.message(Command("fine"))
async def cmd_end_workout(message: Message, state: FSMContext):
    active = get_active_workout()
    if not active:
        await message.answer("Nessuna sessione attiva in corso. Usa /start_workout per iniziarne una.")
        return

    workout_id, split_name, _ = active
    summary = get_workout_summary(workout_id)
    end_active_workout(workout_id)
    await state.clear()

    if not summary:
        await message.answer(f"Sessione **{split_name}** terminata. Nessuna serie salvata.", parse_mode="HTML")
        return

    text = f"🏁 **Allenamento Concluso - {split_name}**\n\n"
    total_volume = 0
    for ex, sets_cnt, volume, max_w in summary:
        vol = volume or 0
        total_volume += vol
        text += f"• **{ex}**: {sets_cnt} serie | Max: {max_w}kg | Vol: {vol:,.0f}kg\n"

    text += f"\n📊 **Volume Totale:** {total_volume:,.0f} kg"
    await message.answer(text, parse_mode="HTML")

@router.message(Command("storico"))
async def cmd_history(message: Message):
    workouts = get_recent_workouts(limit=6)
    if not workouts:
        await message.answer("Non ci sono ancora sessioni registrate nello storico.")
        return

    text = "📋 **Ultimi Allenamenti Registrati:**\n\n"
    buttons = []
    for w_id, start_time, split_name, num_ex, total_sets, total_vol in workouts:
        date_short = start_time[:10]
        text += (
            f"📅 **{date_short}** — **{split_name}**\n"
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
    
    text = f"🔍 **Dettaglio Workout**: {split_name} ({date_str})\n\n"
    grouped = {}
    for ex, s_order, w, r in sets:
        grouped.setdefault(ex, []).append(f"{w}kg×{r}")

    for ex_name, s_list in grouped.items():
        text += f"• **{ex_name}**: {', '.join(s_list)}\n"

    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

@router.message(F.text & ~F.text.startswith("/"))
async def handle_workout_set(message: Message, state: FSMContext):
    active = get_active_workout()
    if not active:
        await message.answer("Nessun allenamento attivo. Usa /start_workout per iniziare.", parse_mode="HTML")
        return

    workout_id, split_name, _ = active
    user_data = await state.get_data()
    selected_exercise = user_data.get("current_exercise")

    exercise = None
    entries = None

    # Se l'utente ha selezionato l'esercizio dai pulsanti
    if selected_exercise:
        entries = parse_set_data_only(message.text)
        if entries:
            exercise = selected_exercise

    # Fallback: l'utente scrive nome + serie assieme
    if not entries:
        parsed = parse_set_message(message.text)
        if parsed:
            exercise, entries = parsed

    if not entries or not exercise:
        await message.answer(
            "⚠️ Formato non valido.\n"
            "Se hai selezionato l'esercizio, scrivi ad esempio: `4x8 80` oppure `100 8,8,7`.\n"
            "Altrimenti seleziona di nuovo un esercizio o usa il formato completo `panca 4x8 80`.",
            parse_mode="HTML"
        )
        return

    log_sets_batch(workout_id, exercise, entries)
    summary_entries = ", ".join([f"{w}kg×{r}" for w, r in entries])
    
    # Conferma e ripresenta la lista esercizi per il prossimo
    await message.answer(
        f"✅ Registrato: **{exercise}** [{summary_entries}]\n\n"
        "Tocca il prossimo esercizio o invia un'altra serie per lo stesso:",
        reply_markup=build_exercise_keyboard(split_name),
        parse_mode="HTML"
    )