import asyncio
import os
import threading
from datetime import datetime
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from http.server import HTTPServer, BaseHTTPRequestHandler

import database as db
import twitch_api

load_dotenv()

# ========== HTTP HEALTH CHECK SERVER ==========
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'Bot is alive! Twitch Stream Bot Running')
    
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()
    
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

# Хранилище для ожидающих добавления пользователей
awaiting_streamer = {}

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
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=f"{EMOJIS['add']} Добавить стримера", callback_data="add_streamer"),
                InlineKeyboardButton(text=f"{EMOJIS['list']} Мои стримеры", callback_data="my_streamers")
            ],
            [
                InlineKeyboardButton(text=f"{EMOJIS['remove']} Удалить стримера", callback_data="remove_streamer"),
                InlineKeyboardButton(text=f"{EMOJIS['stats']} Статистика", callback_data="stats")
            ],
            [
                InlineKeyboardButton(text=f"{EMOJIS['help']} Помощь", callback_data="help")
            ]
        ]
    )
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
        "• Нажми 'Добавить стримера' и введи логин\n"
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
        "📌 *Примеры:*\n"
        "`/add ninja` - добавить Ninja\n"
        "`/check_stream ninja` - проверить стримит ли Ninja\n"
        "`/streams` - статус всех твоих стримеров"
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

# Обработка текстовых сообщений для добавления стримера (только когда ожидаем ввод)
@dp.message(lambda message: message.from_user.id in awaiting_streamer and awaiting_streamer[message.from_user.id])
async def handle_text_message(message: types.Message):
    user_id = message.from_user.id
    
    # Убираем флаг ожидания
    awaiting_streamer[user_id] = False
    streamer_login = message.text.strip().lower()
    
    # Проверяем, что это не команда
    if streamer_login.startswith('/'):
        await message.answer("❌ Отменено. Используй кнопки для команд.", parse_mode=ParseMode.MARKDOWN)
        return
    
    await message.answer(f"🔍 Проверяю стримера `{streamer_login}`...", parse_mode=ParseMode.MARKDOWN)
    
    stream_info = await twitch_api.get_stream_info(streamer_login)
    
    if stream_info is None:
        await message.answer(f"❌ Стример `{streamer_login}` не найден на Twitch!\n\nПопробуй ещё раз через кнопку 'Добавить стримера'.", parse_mode=ParseMode.MARKDOWN)
        return
    
    success = await db.add_streamer(user_id, streamer_login)
    
    if success:
        await message.answer(f"✅ Стример `{streamer_login}` добавлен в список отслеживания!", parse_mode=ParseMode.MARKDOWN)
    else:
        await message.answer(f"⚠️ Стример `{streamer_login}` уже есть в твоём списке!", parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("add"))
async def cmd_add_streamer(message: types.Message):
    user_id = message.from_user.id
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer("❌ Укажи логин стримера.\nПример: `/add ninja`\n\nИли нажми кнопку 'Добавить стримера'", parse_mode=ParseMode.MARKDOWN)
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
            "📋 У тебя пока нет добавленных стримеров.\n\nДобавь через кнопку 'Добавить стримера' или командой `/add <логин>`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    streamers_list = "\n".join([f"• `{s}`" for s in streamers])
    await message.answer(
        f"📋 *Твои стримеры:*\n\n{streamers_list}\n\nВсего: {len(streamers)}",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(Command("check_stream"))
async def cmd_check_stream(message: types.Message):
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer("❌ Укажи логин стримера.\nПример: `/check_stream ninja`", parse_mode=ParseMode.MARKDOWN)
        return
    
    streamer_login = args[1].strip().lower()
    
    await message.answer(f"🔍 Проверяю стримера `{streamer_login}`...", parse_mode=ParseMode.MARKDOWN)
    
    stream_info = await twitch_api.get_stream_info(streamer_login)
    
    if stream_info is None:
        await message.answer(f"❌ Стример `{streamer_login}` не найден на Twitch!", parse_mode=ParseMode.MARKDOWN)
        return
    
    is_live = stream_info.get('is_live', False)
    
    if is_live:
        title = stream_info.get('title', 'Без названия')
        game = stream_info.get('game', 'Неизвестная игра')
        viewers = stream_info.get('viewer_count', 0)
        
        message_text = (
            f"🔴 *{streamer_login}* СЕЙЧАС В ЭФИРЕ!\n\n"
            f"📝 *Тема:* {title}\n"
            f"🎮 *Игра:* {game}\n"
            f"👁️ *Зрителей:* {viewers}\n\n"
            f"🔗 [Смотреть на Twitch](https://twitch.tv/{streamer_login})"
        )
    else:
        message_text = (
            f"⚫ *{streamer_login}* сейчас НЕ В ЭФИРЕ.\n\n"
            f"🔗 [Страница на Twitch](https://twitch.tv/{streamer_login})"
        )
    
    await message.answer(message_text, parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("streams"))
async def cmd_check_all_streams_command(message: types.Message):
    user_id = message.from_user.id
    streamers = await db.get_user_streamers(user_id)
    
    if not streamers:
        await message.answer(
            "📋 У тебя пока нет добавленных стримеров.\n\nДобавь через кнопку 'Добавить стримера' или командой `/add <логин>`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    await message.answer(f"🔄 Проверяю {len(streamers)} стримеров...\nЭто может занять до 10 секунд.", parse_mode=ParseMode.MARKDOWN)
    
    streams_data = await twitch_api.check_multiple_streams(streamers)
    
    online_list = []
    offline_list = []
    
    for login, data in streams_data.items():
        is_live = data.get('is_live', False)
        exists = data.get('exists', True)
        
        if not exists:
            continue
        
        if is_live:
            viewers = data.get('viewer_count', 0)
            online_list.append(f"🔴 `{login}` — {viewers} зрителей")
        else:
            offline_list.append(f"⚫ `{login}`")
    
    result_text = "📊 *Статус стримеров:*\n\n"
    
    if online_list:
        result_text += "*В ЭФИРЕ:*\n" + "\n".join(online_list) + "\n\n"
    else:
        result_text += "🔴 *В эфире:* никто\n\n"
    
    if offline_list:
        result_text += "*НЕ В ЭФИРЕ:*\n" + "\n".join(offline_list)
    
    await message.answer(result_text, parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("check"))
async def cmd_check_now(message: types.Message):
    await message.answer("🔄 Проверяю стримы... Это может занять несколько секунд.")
    await check_all_streams(manual_mode=True, notifier_user_id=message.from_user.id)

@dp.callback_query()
async def handle_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    if callback.data == "add_streamer":
        # Устанавливаем флаг, что пользователь ожидает ввода логина
        awaiting_streamer[user_id] = True
        await callback.message.answer(
            "✏️ *Введи логин стримера*\n\n"
            "Просто напиши ник стримера (например, `ninja`)\n\n"
            "Для отмены отправь любую команду, например `/help`",
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()
    
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
        await callback.answer()
    
    elif callback.data == "remove_streamer":
        streamers = await db.get_user_streamers(user_id)
        if not streamers:
            await callback.message.answer("📋 У тебя нет стримеров для удаления.")
        else:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=f"❌ {s}", callback_data=f"del_{s}")] for s in streamers] +
                                [[InlineKeyboardButton(text="🔙 Назад", callback_data="back")]]
            )
            await callback.message.answer("Выбери стримера для удаления:", reply_markup=keyboard)
        await callback.answer()
    
    elif callback.data == "stats":
        await cmd_stats(callback.message)
        await callback.answer()
    
    elif callback.data == "help":
        await cmd_help(callback.message)
        await callback.answer()
    
    elif callback.data.startswith("del_"):
        streamer_login = callback.data[4:]
        success = await db.remove_streamer(user_id, streamer_login)
        if success:
            await callback.message.edit_text(f"✅ Стример `{streamer_login}` удалён.")
        else:
            await callback.message.edit_text(f"❌ Ошибка при удалении.")
        await callback.answer()
    
    elif callback.data == "back":
        await callback.message.edit_text("🔙 Главное меню:", reply_markup=get_main_keyboard())
        await callback.answer()

async def check_all_streams(manual_mode: bool = False, notifier_user_id: int = None):
    print(f"[{datetime.now()}] 🔍 Запуск проверки стримов...")
    
    all_subscriptions = await db.get_all_subscriptions()
    
    if not all_subscriptions:
        print("Нет активных подписок")
        if manual_mode and notifier_user_id:
            await bot.send_message(notifier_user_id, "📭 Нет активных подписок для проверки.")
        return
    
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
            
            for user_id in streamer_users[streamer_login]:
                try:
                    await bot.send_message(user_id, message_text, parse_mode=ParseMode.MARKDOWN)
                    print(f"✅ Уведомление отправлено {user_id} о стриме {streamer_login}")
                except Exception as e:
                    print(f"❌ Ошибка отправки {user_id}: {e}")
        
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
    print("🚀 Запуск бота...")
    
    if not await db.init_db():
        print("❌ Не удалось подключиться к Supabase. Проверь настройки в .env")
        return
    
    if not TWITCH_ACCESS_TOKEN or not TWITCH_REFRESH_TOKEN or not TWITCH_CLIENT_ID:
        print("❌ Не указаны токены Twitch в .env")
        return
    
    print("✅ Токены Twitch загружены")
    
    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()
    print("✅ Health check сервер запущен на порту 8080")
    
    scheduler.add_job(check_all_streams, IntervalTrigger(minutes=5))
    scheduler.start()
    
    print("🤖 Бот успешно запущен и работает!")
    print("🔄 Планировщик активен, проверка каждые 5 минут")
    print("💾 База данных: Supabase (облако)")
    print("🎮 Twitch API: готов к работе")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
