from aiogram import Router
from aiogram.types import Message, BufferedInputFile
from aiogram.filters import Command
from src.database import get_exercise_history
from src.charts import generate_progression_chart

router = Router()

@router.message(Command("progressione"))
async def cmd_progression(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Specificare l'esercizio. Esempio: `/progressione panca`", parse_mode="Markdown")
        return

    exercise_name = parts[1].strip()
    records = get_exercise_history(exercise_name)

    if not records:
        await message.answer(f"Nessuno storico trovato per '{exercise_name}'.")
        return

    chart_buf = generate_progression_chart(exercise_name, records)
    if not chart_buf:
        await message.answer("Dati insufficienti per costruire il grafico.")
        return

    file = BufferedInputFile(chart_buf.getvalue(), filename=f"{exercise_name}_progression.png")
    await message.answer_photo(photo=file, caption=f"Grafico di progressione per **{exercise_name.title()}**", parse_mode="Markdown")