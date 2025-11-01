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
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiohttp import web

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "-1001234567890"))
PORT = int(os.getenv("PORT", 8080))

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

class Form(StatesGroup):
    waiting_for_links = State()

user_data = {}

def normalize_link(text: str):
    pattern = r'(?:https?://)?t\.me/([a-zA-Z0-9_]{5,})'
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        return f"t.me/{match.group(1)}"
    return None

def format_log_message(user: types.User, link: str) -> str:
    username = f"@{user.username}" if user.username else "Нет юзернейма"
    return (
        f"<b>Новая ссылка в конкурсе</b>\n\n"
        f"<b>Участник:</b> {username} (ID: <code>{user.id}</code>)\n"
        f"<b>Ссылка:</b> <code>{link}</code>\n"
        f"<b>Время:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )

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

def get_submit_button():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Выполнил условия", callback_data="submit_links")]
    ])
    return keyboard

@dp.message(Command("start"))
async def start_command(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in user_data and user_data[user_id].get("completed"):
        await message.answer("✅ Ты уже участвуешь в конкурсе!\n\nРезультаты будут объявлены <b>25 ноября 2025</b>.")
        return
    user_data[user_id] = {"links": [], "completed": False}
    await state.set_state(Form.waiting_for_links)
    await message.answer("👋 <b>Привет!</b>\n\nЧтобы участвовать в конкурсе, пригласи <b>минимум 3 человека</b>.\n\n📝 Пришли мне ссылки на их профили (по одной в сообщении):\n• <code>t.me/username</code>\n• <code>https://t.me/username</code>\n\nКогда пришлёшь 3+ уникальные ссылки — появится кнопка для завершения.")

@dp.message(Form.waiting_for_links)
async def handle_link(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id not in user_data or user_data[user_id].get("completed"):
        return
    raw_text = message.text.strip()
    link = normalize_link(raw_text)
    if not link:
        await message.answer("❌ Неправильная ссылка!\n\nПример правильной ссылки:\n<code>t.me/username</code> или <code>https://t.me/username</code>")
        return
    if link in user_data[user_id]["links"]:
        await message.answer("⚠️ Эта ссылка уже была добавлена. Пришли другую.")
        return
    user_data[user_id]["links"].append(link)
    log_text = format_log_message(message.from_user, link)
    try:
        await bot.send_message(LOG_CHANNEL_ID, log_text, disable_web_page_preview=True)
    except Exception as e:
        print(f"❌ Ошибка отправки в канал: {e}")
    count = len(user_data[user_id]['links'])
    await message.answer(f"✅ Принято: <code>{link}</code>\n\n📊 Всего ссылок: {count}/3")
    if count >= 3:
        await message.answer("🎉 <b>Отлично!</b> У тебя уже достаточно ссылок.\n\nМожешь добавить ещё или нажать кнопку ниже:", reply_markup=get_submit_button())

@dp.callback_query(F.data == "submit_links")
async def submit_links(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if user_id not in user_data or user_data[user_id].get("completed"):
        await callback.answer("⚠️ Ты уже отправил заявку!", show_alert=True)
        return
    if len(user_data[user_id]["links"]) < 3:
        await callback.answer("❌ Нужно минимум 3 ссылки!", show_alert=True)
        return
    user_data[user_id]["completed"] = True
    final_text = format_final_message(callback.from_user, user_data[user_id]["links"])
    try:
        await bot.send_message(LOG_CHANNEL_ID, final_text, disable_web_page_preview=True)
    except Exception as e:
        print(f"❌ Ошибка отправки финального сообщения: {e}")
    await state.clear()
    await callback.message.edit_text(f"✅ <b>Поздравляем!</b>\n\nТвоя заявка принята! Ты пригласил <b>{len(user_data[user_id]['links'])} человек</b>.\n\n🗓 Результаты конкурса: <b>25 ноября 2025</b>\n\nУдачи! 🍀")
    await callback.answer("✅ Заявка принята!", show_alert=True)

@dp.message(Command("stats"))
async def stats_command(message: types.Message):
    total_users = len(user_data)
    completed_users = sum(1 for data in user_data.values() if data.get("completed"))
    total_links = sum(len(data["links"]) for data in user_data.values())
    await message.answer(f"📊 <b>Статистика бота:</b>\n\n👥 Всего пользователей: {total_users}\n✅ Завершили участие: {completed_users}\n🔗 Всего ссылок собрано: {total_links}")

# HTTP сервер для Render
async def health_check(request):
    return web.Response(text="Bot is running!")

async def start_webhook():
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    print(f"🌐 HTTP server started on port {PORT}")

async def main():
    print("🤖 Бот запущен!")
    print(f"📝 Логи отправляются в канал: {LOG_CHANNEL_ID}")

    # Запускаем HTTP сервер и бота параллельно
    await asyncio.gather(
        start_webhook(),
        dp.start_polling(bot)
    )

if __name__ == "__main__":
    asyncio.run(main())
