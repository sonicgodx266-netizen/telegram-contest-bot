# bot.py
import asyncio
import re
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# === НАСТРОЙКИ ИЗ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ===
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "-1001234567890"))
# =========================================

bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(storage=MemoryStorage())

# Состояние: ждём ссылки
class Form(StatesGroup):
    waiting_for_links = State()

# Хранилище в памяти: {user_id: {"links": [], "completed": False}}
user_data = {}

# Валидация и нормализация ссылки
def normalize_link(text: str) -> str | None:
    pattern = r'(?:https?://)?t\.me/([a-zA-Z0-9_]{5,})'
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        return f"t.me/{match.group(1)}"
    return None

# Формируем сообщение для лога в канал
def format_log_message(user: types.User, link: str) -> str:
    username = f"@{user.username}" if user.username else "Нет юзернейма"
    return (
        f"<b>Новая ссылка в конкурсе</b>\n\n"
        f"<b>Участник:</b> {username} (ID: <code>{user.id}</code>)\n"
        f"<b>Ссылка:</b> <code>{link}</code>\n"
        f"<b>Время:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )

# Формируем финальное сообщение для канала
def format_final_message(user: types.User, links: list) -> str:
    username = f"@{user.username}" if user.username else "Нет юзернейма"
    links_text = "\n".join([f"• <code>{link}</code>" for link in links])
    return (
        f"<b>✅ ЗАЯВКА ПРИНЯТА</b>\n\n"
        f"<b>Участник:</b> {username} (ID: <code>{user.id}</code>)\n"
        f"<b>Количество приглашённых:</b> {len(links)}\n\n"
        f"<b>Ссылки:</b>\n{links_text}\n\n"
        f"<b>Дата подачи:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )

# Кнопка "Выполнил условия"
def get_submit_button():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Выполнил условия", callback_data="submit_links")]
    ])
    return keyboard

# === СТАРТ ===
@dp.message(Command("start"))
async def start_command(message: types.Message, state: FSMContext):
    user_id = message.from_user.id

    # Проверка: уже участвует?
    if user_id in user_data and user_data[user_id].get("completed"):
        await message.answer(
            "✅ Ты уже участвуешь в конкурсе!\n\n"
            "Результаты будут объявлены <b>25 ноября 2025</b>."
        )
        return

    # Инициализация данных пользователя
    user_data[user_id] = {"links": [], "completed": False}
    await state.set_state(Form.waiting_for_links)

    await message.answer(
        "👋 <b>Привет!</b>\n\n"
        "Чтобы участвовать в конкурсе, пригласи <b>минимум 3 человека</b>.\n\n"
        "📝 Пришли мне ссылки на их профили (по одной в сообщении):\n"
        "• <code>t.me/username</code>\n"
        "• <code>https://t.me/username</code>\n\n"
        "Когда пришлёшь 3+ уникальные ссылки — появится кнопка для завершения."
    )

# === ОБРАБОТКА ССЫЛОК ===
@dp.message(Form.waiting_for_links)
async def handle_link(message: types.Message, state: FSMContext):
    user_id = message.from_user.id

    # Проверка: данные есть и не завершено?
    if user_id not in user_data or user_data[user_id].get("completed"):
        return

    raw_text = message.text.strip()
    link = normalize_link(raw_text)

    # Валидация формата
    if not link:
        await message.answer(
            "❌ Неправильная ссылка!\n\n"
            "Пример правильной ссылки:\n"
            "<code>t.me/username</code> или <code>https://t.me/username</code>"
        )
        return

    # Проверка на дубликат
    if link in user_data[user_id]["links"]:
        await message.answer("⚠️ Эта ссылка уже была добавлена. Пришли другую.")
        return

    # Сохраняем в память
    user_data[user_id]["links"].append(link)

    # Отправляем в канал (каждую ссылку отдельно)
    log_text = format_log_message(message.from_user, link)
    try:
        await bot.send_message(LOG_CHANNEL_ID, log_text, disable_web_page_preview=True)
    except Exception as e:
        print(f"❌ Ошибка отправки в канал: {e}")

    # Подтверждение пользователю
    count = len(user_data[user_id]['links'])
    await message.answer(f"✅ Принято: <code>{link}</code>\n\n📊 Всего ссылок: {count}/3")

    # Показываем кнопку, если 3+
    if count >= 3:
        await message.answer(
            "🎉 <b>Отлично!</b> У тебя уже достаточно ссылок.\n\n"
            "Можешь добавить ещё или нажать кнопку ниже:",
            reply_markup=get_submit_button()
        )

# === НАЖАТИЕ КНОПКИ "ВЫПОЛНИЛ УСЛОВИЯ" ===
@dp.callback_query(F.data == "submit_links")
async def submit_links(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id

    # Проверка: уже отправлял?
    if user_id not in user_data or user_data[user_id].get("completed"):
        await callback.answer("⚠️ Ты уже отправил заявку!", show_alert=True)
        return

    # Проверка: достаточно ли ссылок?
    if len(user_data[user_id]["links"]) < 3:
        await callback.answer("❌ Нужно минимум 3 ссылки!", show_alert=True)
        return

    # Помечаем как завершённое
    user_data[user_id]["completed"] = True

    # Отправляем финальное сообщение в канал
    final_text = format_final_message(callback.from_user, user_data[user_id]["links"])
    try:
        await bot.send_message(LOG_CHANNEL_ID, final_text, disable_web_page_preview=True)
    except Exception as e:
        print(f"❌ Ошибка отправки финального сообщения: {e}")

    # Очищаем состояние
    await state.clear()

    # Подтверждение пользователю
    await callback.message.edit_text(
        "✅ <b>Поздравляем!</b>\n\n"
        f"Твоя заявка принята! Ты пригласил <b>{len(user_data[user_id]['links'])} человек</b>.\n\n"
        "🗓 Результаты конкурса: <b>25 ноября 2025</b>\n\n"
        "Удачи! 🍀"
    )
    await callback.answer("✅ Заявка принята!", show_alert=True)

# === КОМАНДА /STATS (для админа) ===
@dp.message(Command("stats"))
async def stats_command(message: types.Message):
    total_users = len(user_data)
    completed_users = sum(1 for data in user_data.values() if data.get("completed"))
    total_links = sum(len(data["links"]) for data in user_data.values())

    await message.answer(
        f"📊 <b>Статистика бота:</b>\n\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"✅ Завершили участие: {completed_users}\n"
        f"🔗 Всего ссылок собрано: {total_links}"
    )

# === ЗАПУСК БОТА ===
async def main():
    print("🤖 Бот запущен!")
    print(f"📝 Логи отправляются в канал: {LOG_CHANNEL_ID}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
