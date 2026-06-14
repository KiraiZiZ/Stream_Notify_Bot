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
import stream_api

load_dotenv()

# ========== HEALTH CHECK SERVER ==========
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'Bot is alive! Twitch & YouTube Stream Bot Running')
    
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

# Устанавливаем токены Twitch
stream_api.set_twitch_tokens(TWITCH_ACCESS_TOKEN, TWITCH_REFRESH_TOKEN, TWITCH_CLIENT_ID)

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

# Хранилище для ожидающих добавления пользователей
awaiting_streamer = {}  # user_id -> {'platform': 'twitch' or 'youtube'}

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
    "stats": "📊",
    "twitch": "🎮",
    "youtube": "📺"
}

def get_main_keyboard():
    """Главная клавиатура с кнопками"""
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

def get_platform_keyboard():
    """Клавиатура выбора платформы"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎮 Twitch", callback_data="platform_twitch"),
                InlineKeyboardButton(text="📺 YouTube", callback_data="platform_youtube")
            ],
            [
                InlineKeyboardButton(text="🔙 Назад", callback_data="back")
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
        "🎬 *Добро пожаловать в бота для отслеживания стримов!*\n\n"
        "Я уведомляю о начале стримов на *Twitch* и *YouTube*.\n\n"
        "📌 *Как пользоваться:*\n"
        "• Используй кнопки ниже\n"
        "• Нажми 'Добавить стримера' и выбери платформу\n"
        "• Введи ник или ссылку на канал\n"
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
        "/add <логин> - Добавить стримера (Twitch)\n"
        "/add_yt <канал> - Добавить YouTube канал\n"
        "/remove <логин> - Удалить стримера\n"
        "/list - Мои стримеры\n"
        "/check_stream <логин> - Проверить статус стримера\n"
        "/streams - Проверить всех моих стримеров\n"
        "/check - Ручная проверка стримов\n"
        "/stats - Статистика\n\n"
        "📌 *Примеры:*\n"
        "`/add ninja` - добавить Ninja на Twitch\n"
        "`/add_yt @ninja` - добавить Ninja на YouTube\n"
        "`/check_stream ninja` - проверить статус\n\n"
        "💡 *Совет:* Используй кнопки под сообщениями!"
    )
    await message.answer(help_text, parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    user_count = await db.get_user_count()
    total_subs = await db.get_total_subscriptions_count()
    user_streamers = await db.get_user_streamers(message.from_user.id)
    
    # Считаем по платформам
    twitch_count = sum(1 for _, p, _ in user_streamers if p == 'twitch')
    youtube_count = sum(1 for _, p, _ in user_streamers if p == 'youtube')
    
    stats_text = (
        "📊 *Статистика:*\n\n"
        f"👥 Всего пользователей: `{user_count}`\n"
        f"🔔 Всего подписок: `{total_subs}`\n\n"
        f"👤 *Твои стримеры:*\n"
        f"   🎮 Twitch: `{twitch_count}`\n"
        f"   📺 YouTube: `{youtube_count}`\n\n"
        "🔄 Проверка каждые 5 минут\n"
        "💾 База данных: Supabase"
    )
    await message.answer(stats_text, parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("add"))
async def cmd_add_streamer(message: types.Message):
    """Добавление Twitch стримера через команду"""
    user_id = message.from_user.id
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer(
            "❌ Укажи логин стримера.\nПример: `/add ninja`\n\n"
            "Или нажми кнопку 'Добавить стримера' и выбери платформу",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    streamer_login = args[1].strip().lower()
    
    await message.answer(f"🔍 Проверяю стримера `{streamer_login}` на Twitch...", parse_mode=ParseMode.MARKDOWN)
    
    exists, display_name, save_identifier, url = await stream_api.check_streamer_exists('twitch', streamer_login)
    
    if not exists:
        await message.answer(f"❌ Стример `{streamer_login}` не найден на Twitch!", parse_mode=ParseMode.MARKDOWN)
        return
    
    success = await db.add_streamer(user_id, streamer_login, 'twitch', save_identifier, display_name)
    
    if success:
        await message.answer(
            f"✅ *{display_name}* добавлен в список отслеживания!\n\n"
            f"🎮 Платформа: Twitch\n"
            f"🔗 {url}",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await message.answer(f"⚠️ *{display_name}* уже есть в твоём списке!", parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("add_yt"))
async def cmd_add_youtube(message: types.Message):
    """Добавление YouTube канала через команду"""
    user_id = message.from_user.id
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer(
            "❌ Укажи название канала YouTube.\n\n"
            "Примеры:\n"
            "`/add_yt @ninja`\n"
            "`/add_yt UC-9-kyTW8ZkZNDHQJ6FgpwQ`\n"
            "`/add_yt https://youtube.com/@ninja`\n\n"
            "Или нажми кнопку 'Добавить стримера' и выбери платформу",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    channel_input = args[1].strip()
    
    await message.answer(f"🔍 Проверяю канал `{channel_input}` на YouTube...", parse_mode=ParseMode.MARKDOWN)
    
    exists, display_name, save_identifier, url = await stream_api.check_streamer_exists('youtube', channel_input)
    
    if not exists:
        await message.answer(
            f"❌ Канал не найден на YouTube!\n\n"
            f"Проверь правильность ввода и попробуй снова.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    success = await db.add_streamer(user_id, channel_input, 'youtube', save_identifier, display_name)
    
    if success:
        await message.answer(
            f"✅ *{display_name}* добавлен в список отслеживания!\n\n"
            f"📺 Платформа: YouTube\n"
            f"🔗 {url}",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await message.answer(f"⚠️ *{display_name}* уже есть в твоём списке!", parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("remove"))
async def cmd_remove_streamer(message: types.Message):
    user_id = message.from_user.id
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer(
            "❌ Укажи логин стримера.\nПример: `/remove ninja`\n\n"
            "Или нажми кнопку 'Удалить стримера' и выбери из списка",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    streamer_login = args[1].strip().lower()
    
    # Сначала пробуем удалить с Twitch
    success = await db.remove_streamer(user_id, streamer_login, 'twitch')
    if not success:
        # Если не нашли на Twitch, пробуем удалить с YouTube
        success = await db.remove_streamer(user_id, streamer_login, 'youtube')
    
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
            "📋 У тебя пока нет добавленных стримеров.\n\n"
            "Нажми кнопку 'Добавить стримера' и выбери платформу.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    twitch_list = []
    youtube_list = []
    
    for name, platform, _ in streamers:
        if platform == 'twitch':
            twitch_list.append(f"🎮 `{name}`")
        else:
            youtube_list.append(f"📺 `{name}`")
    
    result = "📋 *Твои стримеры:*\n\n"
    if twitch_list:
        result += "*Twitch:*\n" + "\n".join(twitch_list) + "\n\n"
    if youtube_list:
        result += "*YouTube:*\n" + "\n".join(youtube_list) + "\n\n"
    result += f"Всего: {len(streamers)}"
    
    await message.answer(result, parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("check_stream"))
async def cmd_check_stream(message: types.Message):
    """Проверяет текущий статус стримера"""
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer(
            "❌ Укажи логин стримера.\nПример: `/check_stream ninja`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    streamer_login = args[1].strip().lower()
    
    await message.answer(f"🔍 Проверяю `{streamer_login}`...", parse_mode=ParseMode.MARKDOWN)
    
    # Пробуем проверить на Twitch
    stream_info = await stream_api.get_twitch_stream_info(streamer_login)
    
    if stream_info is None:
        # Если не нашли на Twitch, пробуем YouTube
        exists, display_name, channel_id, url = await stream_api.check_streamer_exists('youtube', streamer_login)
        if exists:
            stream_info = await stream_api.get_youtube_stream_info(channel_id)
            platform = "YouTube"
            icon = "📺"
            display = display_name
        else:
            await message.answer(f"❌ Стример `{streamer_login}` не найден!", parse_mode=ParseMode.MARKDOWN)
            return
    else:
        platform = "Twitch"
        icon = "🎮"
        display = streamer_login
    
    is_live = stream_info.get('is_live', False) if stream_info else False
    
    if is_live:
        title = stream_info.get('title', 'Без названия')
        url = stream_info.get('url', '#')
        
        message_text = (
            f"{icon} *{display}* СЕЙЧАС В ЭФИРЕ на *{platform}*!\n\n"
            f"📝 *Тема:* {title}\n"
            f"🔗 [Смотреть]({url})"
        )
    else:
        if platform == "Twitch":
            url = f"https://twitch.tv/{streamer_login}"
        else:
            url = f"https://youtube.com/channel/{channel_id}"
        
        message_text = (
            f"⚫ *{display}* сейчас НЕ В ЭФИРЕ на *{platform}*.\n\n"
            f"🔗 [Страница]({url})"
        )
    
    await message.answer(message_text, parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("streams"))
async def cmd_check_all_streams_command(message: types.Message):
    """Проверяет статус всех добавленных стримеров"""
    user_id = message.from_user.id
    streamers = await db.get_user_streamers(user_id)
    
    if not streamers:
        await message.answer(
            "📋 У тебя пока нет добавленных стримеров.\n\n"
            "Нажми кнопку 'Добавить стримера' и выбери платформу.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    await message.answer(
        f"🔄 Проверяю {len(streamers)} стримеров...\n"
        f"Это может занять до 15 секунд.",
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Собираем все подписки для проверки
    subscriptions = []
    for name, platform, identifier in streamers:
        subscriptions.append((platform, identifier, user_id))
    
    streams_data = await stream_api.check_multiple_streams(subscriptions)
    
    online_list = []
    offline_list = []
    
    for (identifier, platform), data in streams_data.items():
        is_live = data.get('is_live', False)
        
        if platform == 'twitch':
            icon = "🎮"
            display = identifier
        else:
            icon = "📺"
            display = data.get('channel_name', identifier)
        
        if is_live:
            url = data.get('url', '#')
            online_list.append(f"{icon} `{display}` — [Смотреть]({url})")
        else:
            offline_list.append(f"⚫ `{display}` ({icon})")
    
    result_text = "📊 *Статус стримеров:*\n\n"
    
    if online_list:
        result_text += "*В ЭФИРЕ:*\n" + "\n".join(online_list) + "\n\n"
    else:
        result_text += "🔴 *В эфире:* никто\n\n"
    
    if offline_list:
        result_text += "*НЕ В ЭФИРЕ:*\n" + "\n".join(offline_list)
    
    await message.answer(result_text, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)

@dp.message(Command("check"))
async def cmd_check_now(message: types.Message):
    await message.answer("🔄 Запускаю ручную проверку стримов... Это может занять до 30 секунд.")
    await check_all_streams(manual_mode=True, notifier_user_id=message.from_user.id)

@dp.callback_query()
async def handle_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    if callback.data == "add_streamer":
        await callback.message.answer(
            "🎮 *Выбери платформу:*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_platform_keyboard()
        )
        await callback.answer()
    
    elif callback.data == "platform_twitch":
        awaiting_streamer[user_id] = {'platform': 'twitch'}
        await callback.message.edit_text(
            "✏️ *Введи логин стримера на Twitch*\n\n"
            "Просто напиши ник (например, `ninja`)\n\n"
            "Для отмены отправь `/cancel`",
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()
    
    elif callback.data == "platform_youtube":
        awaiting_streamer[user_id] = {'platform': 'youtube'}
        await callback.message.edit_text(
            "✏️ *Введи название канала YouTube*\n\n"
            "Можно ввести:\n"
            "• ID канала\n"
            "• Username (с @ или без)\n"
            "• Ссылку на канал\n\n"
            "Примеры:\n"
            "`@ninja`\n"
            "`UC-9-kyTW8ZkZNDHQJ6FgpwQ`\n"
            "`https://youtube.com/@ninja`\n\n"
            "Для отмены отправь `/cancel`",
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()
    
    elif callback.data == "my_streamers":
        streamers = await db.get_user_streamers(user_id)
        if not streamers:
            await callback.message.answer("📋 У тебя пока нет добавленных стримеров.")
        else:
            twitch_list = []
            youtube_list = []
            for name, platform, _ in streamers:
                if platform == 'twitch':
                    twitch_list.append(f"🎮 `{name}`")
                else:
                    youtube_list.append(f"📺 `{name}`")
            
            result = "📋 *Твои стримеры:*\n\n"
            if twitch_list:
                result += "*Twitch:*\n" + "\n".join(twitch_list) + "\n\n"
            if youtube_list:
                result += "*YouTube:*\n" + "\n".join(youtube_list) + "\n\n"
            result += f"Всего: {len(streamers)}"
            
            await callback.message.answer(result, parse_mode=ParseMode.MARKDOWN)
        await callback.answer()
    
    elif callback.data == "remove_streamer":
        streamers = await db.get_user_streamers(user_id)
        if not streamers:
            await callback.message.answer("📋 У тебя нет стримеров для удаления.")
        else:
            keyboard_buttons = []
            for name, platform, _ in streamers:
                icon = "🎮" if platform == 'twitch' else "📺"
                keyboard_buttons.append([InlineKeyboardButton(text=f"{icon} {name}", callback_data=f"del_{platform}_{name}")])
            keyboard_buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back")])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
            await callback.message.answer("Выбери стримера для удаления:", reply_markup=keyboard)
        await callback.answer()
    
    elif callback.data == "stats":
        await cmd_stats(callback.message)
        await callback.answer()
    
    elif callback.data == "help":
        await cmd_help(callback.message)
        await callback.answer()
    
    elif callback.data.startswith("del_"):
        # Формат: del_platform_name
        parts = callback.data[4:].split('_', 1)
        if len(parts) == 2:
            platform, streamer_name = parts
            success = await db.remove_streamer(user_id, streamer_name, platform)
            if success:
                await callback.message.edit_text(f"✅ Стример `{streamer_name}` удалён.")
            else:
                await callback.message.edit_text(f"❌ Ошибка при удалении.")
        await callback.answer()
    
    elif callback.data == "back":
        await callback.message.edit_text("🔙 Главное меню:", reply_markup=get_main_keyboard())
        await callback.answer()

# Обработка текстовых сообщений для добавления стримера (когда ожидаем ввод)
@dp.message(lambda message: message.from_user.id in awaiting_streamer)
async def handle_text_message(message: types.Message):
    user_id = message.from_user.id
    user_input = message.text.strip()
    
    # Проверка на отмену
    if user_input.lower() == '/cancel':
        awaiting_streamer.pop(user_id, None)
        await message.answer("❌ Добавление отменено.", parse_mode=ParseMode.MARKDOWN)
        return
    
    platform_info = awaiting_streamer.get(user_id)
    if not platform_info:
        return
    
    platform = platform_info['platform']
    awaiting_streamer.pop(user_id, None)
    
    await message.answer(f"🔍 Проверяю на {platform.upper()}...", parse_mode=ParseMode.MARKDOWN)
    
    # Проверяем существование
    exists, display_name, save_identifier, url = await stream_api.check_streamer_exists(platform, user_input)
    
    if not exists:
        if platform == 'twitch':
            await message.answer(
                f"❌ Стример `{user_input}` не найден на Twitch!\n\n"
                f"Проверь правильность написания и попробуй снова.",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await message.answer(
                f"❌ Канал `{user_input}` не найден на YouTube!\n\n"
                f"Проверь правильность ввода и попробуй снова.",
                parse_mode=ParseMode.MARKDOWN
            )
        return
    
    # Добавляем в базу
    success = await db.add_streamer(user_id, user_input, platform, save_identifier, display_name)
    
    if success:
        platform_icon = "🎮" if platform == 'twitch' else "📺"
        platform_name = "Twitch" if platform == 'twitch' else "YouTube"
        await message.answer(
            f"✅ {platform_icon} *{display_name}* добавлен в список отслеживания!\n\n"
            f"📺 Платформа: {platform_name}\n"
            f"🔗 {url}",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await message.answer(
            f"⚠️ *{display_name}* уже есть в твоём списке!",
            parse_mode=ParseMode.MARKDOWN
        )

async def check_all_streams(manual_mode: bool = False, notifier_user_id: int = None):
    """Основная функция проверки всех стримов"""
    print(f"[{datetime.now()}] 🔍 Запуск проверки стримов...")
    
    all_subscriptions = await db.get_all_subscriptions()  # (user_id, identifier, platform)
    
    if not all_subscriptions:
        print("Нет активных подписок")
        if manual_mode and notifier_user_id:
            await bot.send_message(notifier_user_id, "📭 Нет активных подписок для проверки.")
        return
    
    # Группируем по (identifier, platform)
    streamer_users = {}
    for user_id, identifier, platform in all_subscriptions:
        key = (identifier, platform)
        if key not in streamer_users:
            streamer_users[key] = []
        streamer_users[key].append(user_id)
    
    # Получаем статусы всех стримов
    subscriptions_list = [(platform, identifier, user_id) for (identifier, platform), users in streamer_users.items() for user_id in users]
    streams_data = await stream_api.check_multiple_streams(subscriptions_list)
    
    for (identifier, platform), data in streams_data.items():
        is_live = data.get('is_live', False)
        last_status = await db.get_last_status(identifier, platform)
        
        if is_live and not last_status:
            await db.update_streamer_status(identifier, platform, True)
            
            title = data.get('title', 'Без названия')[:100]
            url = data.get('url', '#')
            
            if platform == 'twitch':
                icon = "🔴"
                platform_name = "Twitch"
                display_name = identifier
            else:
                icon = "📺"
                platform_name = "YouTube"
                display_name = data.get('channel_name', identifier)
            
            message_text = (
                f"{icon} *{display_name}* начал стрим на *{platform_name}*!\n\n"
                f"📝 *Тема:* {title}\n"
                f"🔗 [Смотреть]({url})"
            )
            
            for user_id in streamer_users[(identifier, platform)]:
                try:
                    await bot.send_message(user_id, message_text, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=False)
                    print(f"✅ Уведомление отправлено {user_id} о стриме {display_name} ({platform})")
                except Exception as e:
                    print(f"❌ Ошибка отправки {user_id}: {e}")
        
        elif not is_live and last_status:
            await db.update_streamer_status(identifier, platform, False)
            print(f"📴 Стрим {identifier} ({platform}) закончился")
    
    if manual_mode and notifier_user_id:
        await bot.send_message(
            notifier_user_id,
            "✅ Проверка завершена! Если кто-то начал стрим, ты получишь уведомление."
        )
    
    print(f"[{datetime.now()}] ✅ Проверка завершена")

async def main():
    """Запуск бота"""
    print("🚀 Запуск бота...")
    
    if not await db.init_db():
        print("❌ Не удалось подключиться к Supabase. Проверь настройки в .env")
        return
    
    if not TWITCH_ACCESS_TOKEN or not TWITCH_REFRESH_TOKEN or not TWITCH_CLIENT_ID:
        print("❌ Не указаны токены Twitch в .env")
        return
    
    print("✅ Токены Twitch загружены")
    
    # Проверяем YouTube API
    youtube_key = os.getenv("YOUTUBE_API_KEY")
    if youtube_key:
        print("✅ YouTube API ключ загружен")
    else:
        print("⚠️ YouTube API ключ не указан (YouTube не будет работать)")
    
    # Запускаем health check сервер
    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()
    print("✅ Health check сервер запущен на порту 8080")
    
    # Запускаем планировщик
    scheduler.add_job(check_all_streams, IntervalTrigger(minutes=5))
    scheduler.start()
    
    print("🤖 Бот успешно запущен и работает!")
    print("🔄 Планировщик активен, проверка каждые 5 минут")
    print("💾 База данных: Supabase (облако)")
    print("🎮 Поддерживаемые платформы: Twitch, YouTube")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
