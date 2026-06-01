import asyncio
import os
import threading
from datetime import datetime
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.types import ParseMode, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from http.server import HTTPServer, BaseHTTPRequestHandler

import database as db
import twitch_api

load_dotenv()

# ========== HEALTH CHECK SERVER ==========
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'Twitch Stream Bot is running!')
    
    def log_message(self, format, *args):
        pass

def run_health_server():
    port = int(os.environ.get('PORT', 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    print(f"✅ Health check server running on port {port}")
    server.serve_forever()
# ==========================================

# Telegram
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Twitch токены
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_ACCESS_TOKEN = os.getenv("TWITCH_ACCESS_TOKEN")
TWITCH_REFRESH_TOKEN = os.getenv("TWITCH_REFRESH_TOKEN")

# Устанавливаем токены
twitch_api.set_tokens(TWITCH_ACCESS_TOKEN, TWITCH_REFRESH_TOKEN, TWITCH_CLIENT_ID)

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

# Эмодзи
EMOJIS = {
    "online": "🔴",
    "offline": "⚫",
    "game": "🎮",
    "viewers": "👁️",
    "title": "📝",
    "add": "➕",
    "remove": "❌",
    "list": "📋",
    "help": "ℹ️",
    "stats": "📊"
}

def get_main_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton(text=f"{EMOJIS['add']} Добавить стримера", callback_data="add_streamer"),
        InlineKeyboardButton(text=f"{EMOJIS['list']} Мои стримеры", callback_data="my_streamers")
    )
    keyboard.add(
        InlineKeyboardButton(text=f"{EMOJIS['remove']} Удалить стримера", callback_data="remove_streamer"),
        InlineKeyboardButton(text=f"{EMOJIS['stats']} Статистика", callback_data="stats")
    )
    keyboard.add(InlineKeyboardButton(text=f"{EMOJIS['help']} Помощь", callback_data="help"))
    return keyboard

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    
    await db.add_user(user_id, username)
    
    welcome_text = (
        "🎬 *Добро пожаловать в бота для отслеживания стримов на Twitch!*\n\n"
        "Я буду уведомлять тебя, когда твои любимые стримеры начинают трансляцию.\n\n"
        "📌 *Как пользоваться:*\n"
        "• Используй кнопки ниже\n"
        "• Добавь стримеров по логину (например, `ninja`)\n"
        "• Получай уведомления о начале стримов\n\n"
        "🔄 Бот проверяет стримы каждые 5 минут и работает 24/7!"
    )
    
    await message.answer(welcome_text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    help_text = (
        "📖 *Команды:*\n\n"
        "/start - Перезапустить бота\n"
        "/help - Помощь\n"
        "/add <логин> - Добавить стримера\n"
        "/remove <логин> - Удалить стримера\n"
        "/list - Мои стримеры\n"
        "/check - Проверить стримы вручную\n"
        "/stats - Статистика\n\n"
        "📌 *Пример:* `/add ninja`"
    )
    await message.answer(help_text, parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    user_count = await db.get_user_count()
    total_subs = await db.get_total_subscriptions_count()
    user_streamers = await db.get_user_streamers(message.from_user.id)
    
    stats_text = (
        "📊 *Статистика:*\n\n"
        f"👥 Всего пользователей: `{user_count}`\n"
        f"🔔 Всего подписок: `{total_subs}`\n"
        f"👤 Твоих стримеров: `{len(user_streamers)}`\n\n"
        "🔄 Проверка каждые 5 минут\n"
        "💾 База данных: Supabase"
    )
    await message.answer(stats_text, parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("add"))
async def cmd_add_streamer(message: types.Message):
    user_id = message.from_user.id
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer("❌ Укажи логин стримера.\nПример: `/add ninja`", parse_mode=ParseMode.MARKDOWN)
        return
    
    streamer_login = args[1].strip().lower()
    
    await message.answer(f"🔍 Проверяю стримера `{streamer_login}`...", parse_mode=ParseMode.MARKDOWN)
    
    stream_info = await twitch_api.get_stream_info(streamer_login)
    
    if stream_info is None:
        await message.answer(f"❌ Стример `{streamer_login}` не найден на Twitch!", parse_mode=ParseMode.MARKDOWN)
        return
    
    success = await db.add_streamer(user_id, streamer_login)
    
    if success:
        await message.answer(f"✅ Стример `{streamer_login}` добавлен в список отслеживания!", parse_mode=ParseMode.MARKDOWN)
    else:
        await message.answer(f"⚠️ Стример `{streamer_login}` уже есть в твоём списке!", parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("remove"))
async def cmd_remove_streamer(message: types.Message):
    user_id = message.from_user.id
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer("❌ Укажи логин стримера.\nПример: `/remove ninja`", parse_mode=ParseMode.MARKDOWN)
        return
    
    streamer_login = args[1].strip().lower()
    success = await db.remove_streamer(user_id, streamer_login)
    
    if success:
        await message.answer(f"✅ Стример `{streamer_login}` удалён из списка!", parse_mode=ParseMode.MARKDOWN)
    else:
        await message.answer(f"❌ Стример `{streamer_login}` не найден в твоём списке!", parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("list"))
async def cmd_list_streamers(message: types.Message):
    user_id = message.from_user.id
    streamers = await db.get_user_streamers(user_id)
    
    if not streamers:
        await message.answer(
            "📋 У тебя пока нет добавленных стримеров.\n\nДобавь первого командой `/add <логин>`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    streamers_list = "\n".join([f"• `{s}`" for s in streamers])
    await message.answer(
        f"📋 *Твои стримеры:*\n\n{streamers_list}\n\nВсего: {len(streamers)}",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("check"))
async def cmd_check_now(message: types.Message):
    await message.answer("🔄 Проверяю стримы... Это может занять несколько секунд.")
    await check_all_streams(manual_mode=True, notifier_user_id=message.from_user.id)

@dp.callback_query()
async def handle_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    if callback.data == "add_streamer":
        await callback.message.answer(
            "✏️ Введи логин стримера командой:\n`/add <логин>`\n\nПример: `/add ninja`",
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif callback.data == "my_streamers":
        streamers = await db.get_user_streamers(user_id)
        if not streamers:
            await callback.message.answer("📋 У тебя пока нет добавленных стримеров.")
        else:
            streamers_list = "\n".join([f"• `{s}`" for s in streamers])
            await callback.message.answer(
                f"📋 *Твои стримеры:*\n\n{streamers_list}",
                parse_mode=ParseMode.MARKDOWN
            )
    
    elif callback.data == "remove_streamer":
        streamers = await db.get_user_streamers(user_id)
        if not streamers:
            await callback.message.answer("📋 У тебя нет стримеров для удаления.")
        else:
            keyboard = InlineKeyboardMarkup(row_width=1)
            for s in streamers:
                keyboard.add(InlineKeyboardButton(text=f"❌ {s}", callback_data=f"del_{s}"))
            keyboard.add(InlineKeyboardButton(text="🔙 Назад", callback_data="back"))
            await callback.message.answer("Выбери стримера для удаления:", reply_markup=keyboard)
    
    elif callback.data == "stats":
        await cmd_stats(callback.message)
    
    elif callback.data == "help":
        await cmd_help(callback.message)
    
    elif callback.data.startswith("del_"):
        streamer_login = callback.data[4:]
        success = await db.remove_streamer(user_id, streamer_login)
        if success:
            await callback.message.edit_text(f"✅ Стример `{streamer_login}` удалён.")
        else:
            await callback.message.edit_text(f"❌ Ошибка при удалении.")
    
    elif callback.data == "back":
        await callback.message.edit_text("🔙 Главное меню:", reply_markup=get_main_keyboard())
    
    await callback.answer()

async def check_all_streams(manual_mode: bool = False, notifier_user_id: int = None):
    """Основная функция проверки всех стримов"""
    print(f"[{datetime.now()}] 🔍 Запуск проверки стримов...")
    
    all_subscriptions = await db.get_all_subscriptions()
    
    if not all_subscriptions:
        print("Нет активных подписок")
        if manual_mode and notifier_user_id:
            await bot.send_message(notifier_user_id, "📭 Нет активных подписок для проверки.")
        return
    
    # Группируем подписки по стримерам
    streamer_users = {}
    for user_id, streamer_login in all_subscriptions:
        if streamer_login not in streamer_users:
            streamer_users[streamer_login] = []
        streamer_users[streamer_login].append(user_id)
    
    unique_streamers = list(streamer_users.keys())
    print(f"📡 Проверяем {len(unique_streamers)} стримеров...")
    
    streams_data = await twitch_api.check_multiple_streams(unique_streamers)
    
    for streamer_login, data in streams_data.items():
        is_live = data.get('is_live', False)
        last_status = await db.get_last_status(streamer_login)
        
        # Если стрим начался (был оффлайн, стал онлайн)
        if is_live and not last_status:
            await db.update_streamer_status(streamer_login, True)
            
            title = data.get('title', 'Без названия')[:100]
            game = data.get('game', 'Неизвестная игра')
            viewers = data.get('viewer_count', 0)
            
            message_text = (
                f"{EMOJIS['online']} *{streamer_login}* начал стрим!\n\n"
                f"{EMOJIS['title']} *Тема:* {title}\n"
                f"{EMOJIS['game']} *Игра:* {game}\n"
                f"{EMOJIS['viewers']} *Зрителей:* {viewers}\n\n"
                f"🔗 [Смотреть на Twitch](https://twitch.tv/{streamer_login})"
            )
            
            # Отправляем уведомление всем подписанным пользователям
            for user_id in streamer_users[streamer_login]:
                try:
                    await bot.send_message(user_id, message_text, parse_mode=ParseMode.MARKDOWN)
                    print(f"✅ Уведомление отправлено {user_id} о стриме {streamer_login}")
                except Exception as e:
                    print(f"❌ Ошибка отправки {user_id}: {e}")
        
        # Если стрим закончился
        elif not is_live and last_status:
            await db.update_streamer_status(streamer_login, False)
            print(f"📴 Стрим {streamer_login} закончился")
    
    if manual_mode and notifier_user_id:
        await bot.send_message(
            notifier_user_id,
            "✅ Проверка завершена! Если кто-то начал стрим, ты получишь уведомление."
        )
    
    print(f"[{datetime.now()}] ✅ Проверка завершена")

async def main():
    """Запуск бота"""
    print("🚀 Запуск бота...")
    
    # Проверяем подключение к Supabase
    if not await db.init_db():
        print("❌ Не удалось подключиться к Supabase. Проверь настройки в .env")
        return
    
    # Проверяем наличие токенов Twitch
    if not TWITCH_ACCESS_TOKEN or not TWITCH_REFRESH_TOKEN or not TWITCH_CLIENT_ID:
        print("❌ Не указаны токены Twitch в .env")
        return
    
    print("✅ Токены Twitch загружены")
    
    # Запускаем health check сервер в отдельном потоке
    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()
    print("✅ Health check сервер запущен")
    
    # Запускаем планировщик
    scheduler.add_job(check_all_streams, IntervalTrigger(minutes=5))
    scheduler.start()
    
    print("🤖 Бот успешно запущен и работает!")
    print("🔄 Планировщик активен, проверка каждые 5 минут")
    print("💾 База данных: Supabase (облако)")
    print("🎮 Twitch API: готов к работе")
    
    # Запускаем поллинг
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
