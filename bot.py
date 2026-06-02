import asyncio
import os
import threading
from datetime import datetime
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder  # Добавьте этот импорт
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

# ИСПРАВЛЕНА ФУНКЦИЯ get_main_keyboard
def get_main_keyboard():
    """Создание главной клавиатуры (aiogram 3.x синтаксис)"""
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

# Альтернативная версия с использованием Builder (более гибкая)
def get_main_keyboard_builder():
    """Создание главной клавиатуры через Builder (альтернативный способ)"""
    builder = InlineKeyboardBuilder()
    builder.button(text=f"{EMOJIS['add']} Добавить стримера", callback_data="add_streamer")
    builder.button(text=f"{EMOJIS['list']} Мои стримеры", callback_data="my_streamers")
    builder.button(text=f"{EMOJIS['remove']} Удалить стримера", callback_data="remove_streamer")
    builder.button(text=f"{EMOJIS['stats']} Статистика", callback_data="stats")
    builder.button(text=f"{EMOJIS['help']} Помощь", callback_data="help")
    builder.adjust(2)  # 2 кнопки в ряду, последняя будет одна
    return builder.as_markup()

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
        "/check_stream <логин> - Проверить статус стримера\n"
        "/streams - Проверить всех моих стримеров\n"
        "/check - Ручная проверка и уведомления\n"
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
        await message.answer(f"✅ Стример `{streamer_login}` добавлен!", parse_mode=ParseMode.MARKDOWN)
    else:
        await message.answer(f"⚠️ Стример `{streamer_login}` уже в списке!", parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("remove"))
async def cmd_remove_streamer(message: types.Message):
    user_id = message.from_user.id
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer("❌ Укажи логин.\nПример: `/remove ninja`", parse_mode=ParseMode.MARKDOWN)
        return
    
    streamer_login = args[1].strip().lower()
    success = await db.remove_streamer(user_id, streamer_login)
    
    if success:
        await message.answer(f"✅ Стример `{streamer_login}` удалён!", parse_mode=ParseMode.MARKDOWN)
    else:
        await message.answer(f"❌ Стример `{streamer_login}` не найден!", parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("list"))
async def cmd_list_streamers(message: types.Message):
    user_id = message.from_user.id
    streamers = await db.get_user_streamers(user_id)
    
    if not streamers:
        await message.answer("📋 У тебя пока нет стримеров.\nДобавь командой `/add`", parse_mode=ParseMode.MARKDOWN)
        return
    
    streamers_list = "\n".join([f"• `{s}`" for s in streamers])
    await message.answer(f"📋 *Твои стримеры:*\n\n{streamers_list}\n\nВсего: {len(streamers)}", parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("check"))
async def cmd_check_now(message: types.Message):
    await message.answer("🔄 Проверяю стримы...")
    await check_all_streams(manual_mode=True, notifier_user_id=message.from_user.id)
@dp.message(Command("check_stream"))
async def cmd_check_stream(message: types.Message):
    """Проверяет текущий статус стримера (стримит или нет)"""
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer(
            "❌ Укажи логин стримера.\nПример: `/check_stream ninja`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    streamer_login = args[1].strip().lower()
    
    await message.answer(f"🔍 Проверяю стримера `{streamer_login}`...", parse_mode=ParseMode.MARKDOWN)
    
    # Получаем информацию о стримере
    stream_info = await twitch_api.get_stream_info(streamer_login)
    
    if stream_info is None:
        await message.answer(
            f"❌ Стример `{streamer_login}` не найден на Twitch!\n\n"
            f"Проверь правильность логина.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    is_live = stream_info.get('is_live', False)
    
    if is_live:
        # Стример онлайн
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
        # Стример оффлайн
        message_text = (
            f"⚫ *{streamer_login}* сейчас НЕ В ЭФИРЕ.\n\n"
            f"🔗 [Страница на Twitch](https://twitch.tv/{streamer_login})"
        )
    
    await message.answer(message_text, parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("streams"))
async def cmd_check_all_streams(message: types.Message):
    """Проверяет статус всех добавленных стримеров"""
    user_id = message.from_user.id
    streamers = await db.get_user_streamers(user_id)
    
    if not streamers:
        await message.answer(
            "📋 У тебя пока нет добавленных стримеров.\n\n"
            "Добавь первого командой `/add <логин>`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    await message.answer(
        f"🔄 Проверяю {len(streamers)} стримеров...\n"
        f"Это может занять до 10 секунд.",
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Проверяем всех стримеров
    streams_data = await twitch_api.check_multiple_streams(streamers)
    
    online_list = []
    offline_list = []
    
    for login, data in streams_data.items():
        is_live = data.get('is_live', False)
        exists = data.get('exists', True)
        
        if not exists:
            continue  # Пропускаем несуществующих
        
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

# ИСПРАВЛЕНА ФУНКЦИЯ handle_callback
@dp.callback_query()
async def handle_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    if callback.data == "add_streamer":
        await callback.message.answer("✏️ Введи логин командой: `/add ninja`", parse_mode=ParseMode.MARKDOWN)
    elif callback.data == "my_streamers":
        streamers = await db.get_user_streamers(user_id)
        if streamers:
            streamers_text = "📋 *Твои стримеры:*\n\n" + "\n".join([f"• {s}" for s in streamers])
            await callback.message.answer(streamers_text, parse_mode=ParseMode.MARKDOWN)
        else:
            await callback.message.answer("📋 У тебя пока нет стримеров")
    elif callback.data == "remove_streamer":
        streamers = await db.get_user_streamers(user_id)
        if streamers:
            # ИСПРАВЛЕНА клавиатура для удаления стримеров
            buttons = []
            for s in streamers:
                buttons.append([InlineKeyboardButton(text=f"❌ {s}", callback_data=f"del_{s}")])
            buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back")])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            await callback.message.answer("Выбери стримера для удаления:", reply_markup=keyboard)
        else:
            await callback.message.answer("📋 У тебя нет стримеров")
    elif callback.data == "stats":
        await cmd_stats(callback.message)
    elif callback.data == "help":
        await cmd_help(callback.message)
    elif callback.data.startswith("del_"):
        streamer = callback.data[4:]
        await db.remove_streamer(user_id, streamer)
        await callback.message.edit_text(f"✅ Стример `{streamer}` удалён!", parse_mode=ParseMode.MARKDOWN)
    elif callback.data == "back":
        await callback.message.edit_text("🔙 Главное меню:", reply_markup=get_main_keyboard())
    
    await callback.answer()

async def check_all_streams(manual_mode: bool = False, notifier_user_id: int = None):
    print(f"[{datetime.now()}] 🔍 Проверка стримов...")
    
    all_subscriptions = await db.get_all_subscriptions()
    if not all_subscriptions:
        if manual_mode and notifier_user_id:
            await bot.send_message(notifier_user_id, "📭 Нет активных подписок")
        return
    
    streamer_users = {}
    for user_id, streamer_login in all_subscriptions:
        if streamer_login not in streamer_users:
            streamer_users[streamer_login] = []
        streamer_users[streamer_login].append(user_id)
    
    streams_data = await twitch_api.check_multiple_streams(list(streamer_users.keys()))
    
    for streamer_login, data in streams_data.items():
        is_live = data.get('is_live', False)
        last_status = await db.get_last_status(streamer_login)
        
        if is_live and not last_status:
            await db.update_streamer_status(streamer_login, True)
            
            message_text = (
                f"🔴 *{streamer_login}* начал стрим!\n\n"
                f"📝 *Тема:* {data.get('title', 'Без названия')[:80]}\n"
                f"🎮 *Игра:* {data.get('game', 'Неизвестная')}\n"
                f"👁️ *Зрителей:* {data.get('viewer_count', 0)}\n\n"
                f"🔗 [Смотреть на Twitch](https://twitch.tv/{streamer_login})"
            )
            
            for user_id in streamer_users[streamer_login]:
                try:
                    await bot.send_message(user_id, message_text, parse_mode=ParseMode.MARKDOWN)
                    print(f"✅ Уведомление {user_id} о {streamer_login}")
                except Exception as e:
                    print(f"❌ Ошибка: {e}")
        
        elif not is_live and last_status:
            await db.update_streamer_status(streamer_login, False)
            print(f"📴 Стрим {streamer_login} закончился")
    
    if manual_mode and notifier_user_id:
        await bot.send_message(notifier_user_id, "✅ Проверка завершена!")

async def main():
    print("🚀 Запуск бота...")
    
    if not await db.init_db():
        print("❌ Ошибка подключения к Supabase")
        return
    
    if not TWITCH_ACCESS_TOKEN or not TWITCH_REFRESH_TOKEN or not TWITCH_CLIENT_ID:
        print("❌ Не указаны токены Twitch")
        return
    
    print("✅ Токены Twitch загружены")
    
    # Запускаем health check сервер
    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()
    print("✅ Health check сервер запущен")
    
    scheduler.add_job(check_all_streams, IntervalTrigger(minutes=5))
    scheduler.start()
    
    print("🤖 Бот успешно запущен!")
    print("🔄 Проверка каждые 5 минут")
    print("💾 База: Supabase")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
