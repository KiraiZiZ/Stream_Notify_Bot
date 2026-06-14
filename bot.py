import asyncio
import os
import threading
from datetime import datetime
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
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
        self.wfile.write(b'Bot is alive! Twitch & YouTube & Kick Stream Bot Running')
    
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
awaiting_streamer = {}  # user_id -> {'platform': 'twitch' or 'youtube' or 'kick'}

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
    "youtube": "📺",
    "kick": "🦵"
}

def get_main_keyboard():
    """Постоянная клавиатура под полем ввода"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=f"{EMOJIS['add']} Добавить стримера"),
                KeyboardButton(text=f"{EMOJIS['list']} Мои стримеры")
            ],
            [
                KeyboardButton(text=f"{EMOJIS['remove']} Удалить стримера"),
                KeyboardButton(text=f"{EMOJIS['stats']} Статистика")
            ],
            [
                KeyboardButton(text=f"{EMOJIS['help']} Помощь")
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )
    return keyboard

def cancel_keyboard():
    """Клавиатура с кнопкой отмены"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❌ Отмена")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    return keyboard

def get_platform_keyboard():
    """Клавиатура выбора платформы (с Kick)"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎮 Twitch", callback_data="platform_twitch"),
                InlineKeyboardButton(text="📺 YouTube", callback_data="platform_youtube")
            ],
            [
                InlineKeyboardButton(text="🦵 Kick", callback_data="platform_kick"),
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
        "Я уведомляю о начале стримов на *Twitch*, *YouTube* и *Kick*.\n\n"
        "📌 *Как пользоваться:*\n"
        "• Используй кнопки под полем ввода\n"
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
        "/add_kick <ник> - Добавить стримера Kick\n"
        "/remove <логин> - Удалить стримера\n"
        "/list - Мои стримеры\n"
        "/streams - Проверить всех моих стримеров\n"
        "/stats - Статистика\n\n"
        "📌 *Примеры:*\n"
        "`/add ninja` - добавить Ninja на Twitch\n"
        "`/add_yt @ninja` - добавить Ninja на YouTube\n"
        "`/add_kick xqc` - добавить xqc на Kick\n\n"
        "💡 *Совет:* Используй кнопки под полем ввода!"
    )
    await message.answer(help_text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    user_count = await db.get_user_count()
    total_subs = await db.get_total_subscriptions_count()
    user_streamers = await db.get_user_streamers(message.from_user.id)
    
    twitch_count = sum(1 for _, p, _ in user_streamers if p == 'twitch')
    youtube_count = sum(1 for _, p, _ in user_streamers if p == 'youtube')
    kick_count = sum(1 for _, p, _ in user_streamers if p == 'kick')
    
    stats_text = (
        "📊 *Статистика:*\n\n"
        f"👥 Всего пользователей: `{user_count}`\n"
        f"🔔 Всего подписок: `{total_subs}`\n\n"
        f"👤 *Твои стримеры:*\n"
        f"   🎮 Twitch: `{twitch_count}`\n"
        f"   📺 YouTube: `{youtube_count}`\n"
        f"   🦵 Kick: `{kick_count}`\n\n"
        "🔄 Проверка каждые 5 минут"
    )
    await message.answer(stats_text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

@dp.message(Command("add"))
async def cmd_add_streamer(message: types.Message):
    """Добавление Twitch стримера через команду"""
    user_id = message.from_user.id
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer(
            "❌ Укажи логин стримера.\nПример: `/add ninja`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard()
        )
        return
    
    streamer_login = args[1].strip().lower()
    
    await message.answer(f"🔍 Проверяю стримера `{streamer_login}` на Twitch...", parse_mode=ParseMode.MARKDOWN)
    
    exists, display_name, save_identifier, url = await stream_api.check_streamer_exists('twitch', streamer_login)
    
    if not exists:
        await message.answer(f"❌ Стример `{streamer_login}` не найден на Twitch!", parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())
        return
    
    success = await db.add_streamer(user_id, streamer_login, 'twitch', save_identifier, display_name)
    
    if success:
        await message.answer(
            f"✅ *{display_name}* добавлен в список отслеживания!\n\n"
            f"🎮 Платформа: Twitch\n"
            f"🔗 {url}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard()
        )
    else:
        await message.answer(f"⚠️ *{display_name}* уже есть в твоём списке!", parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

@dp.message(Command("add_yt"))
async def cmd_add_youtube(message: types.Message):
    """Добавление YouTube канала через команду"""
    user_id = message.from_user.id
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer(
            "❌ Укажи название канала YouTube.\n\nПримеры:\n"
            "`/add_yt @ninja`\n"
            "`/add_yt https://youtube.com/@ninja`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard()
        )
        return
    
    channel_input = args[1].strip()
    
    await message.answer(f"🔍 Проверяю канал на YouTube...", parse_mode=ParseMode.MARKDOWN)
    
    exists, display_name, save_identifier, url = await stream_api.check_streamer_exists('youtube', channel_input)
    
    if not exists:
        await message.answer(f"❌ Канал не найден на YouTube!\n\nПроверь правильность ввода.", parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())
        return
    
    # ВАЖНО: Сохраняем display_name (имя канала), а не channel_input
    success = await db.add_streamer(user_id, display_name, 'youtube', save_identifier, display_name)
    
    if success:
        await message.answer(
            f"✅ *{display_name}* добавлен в список отслеживания!\n\n"
            f"📺 Платформа: YouTube\n"
            f"🔗 {url}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard()
        )
    else:
        await message.answer(f"⚠️ *{display_name}* уже есть в твоём списке!", parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

@dp.message(Command("add_kick"))
async def cmd_add_kick(message: types.Message):
    """Добавление Kick стримера через команду"""
    user_id = message.from_user.id
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer(
            "❌ Укажи никнейм стримера на Kick.\nПример: `/add_kick xqc`\n\n"
            "💡 Регистр не важен: можно писать `xqc`, `XQC`, `xQc` — бот найдёт!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard()
        )
        return
    
    streamer_slug = args[1].strip()
    # Убираем @ если есть
    if streamer_slug.startswith('@'):
        streamer_slug = streamer_slug[1:]
    
    await message.answer(f"🔍 Ищу стримера `{streamer_slug}` на Kick...\n(регистр не важен)", parse_mode=ParseMode.MARKDOWN)
    
    exists, display_name, save_identifier, url = await stream_api.check_streamer_exists('kick', streamer_slug)
    
    if not exists:
        await message.answer(
            f"❌ Стример `{streamer_slug}` не найден на Kick!\n\n"
            f"Возможные причины:\n"
            f"• Такой стример не зарегистрирован на Kick\n"
            f"• Стример забанен или удалил аккаунт\n\n"
            f"💡 Попробуй найти стримера вручную на https://kick.com",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard()
        )
        return
    
    success = await db.add_streamer(user_id, streamer_slug, 'kick', save_identifier, display_name)
    
    if success:
        await message.answer(
            f"✅ *{display_name}* добавлен в список отслеживания!\n\n"
            f"🦵 Платформа: Kick\n"
            f"🔗 {url}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard()
        )
    else:
        await message.answer(
            f"⚠️ *{display_name}* уже есть в твоём списке!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard()
        )

@dp.message(Command("remove"))
async def cmd_remove_streamer(message: types.Message):
    user_id = message.from_user.id
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer(
            "❌ Укажи логин стримера.\nПример: `/remove ninja`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard()
        )
        return
    
    streamer_login = args[1].strip()
    
    streamers = await db.get_user_streamers(user_id)
    
    found = False
    for name, platform, identifier in streamers:
        if name.lower() == streamer_login.lower():
            success = await db.remove_streamer(user_id, name, platform)
            if success:
                await message.answer(f"✅ Стример `{name}` удалён из списка!", parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())
            else:
                await message.answer(f"❌ Ошибка при удалении!", parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())
            found = True
            break
    
    if not found:
        await message.answer(f"❌ Стример `{streamer_login}` не найден в твоём списке!", parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

@dp.message(Command("list"))
async def cmd_list_streamers(message: types.Message):
    user_id = message.from_user.id
    streamers = await db.get_user_streamers(user_id)
    
    if not streamers:
        await message.answer(
            "📋 У тебя пока нет добавленных стримеров.\n\nНажми 'Добавить стримера' и выбери платформу.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard()
        )
        return
    
    twitch_list = []
    youtube_list = []
    kick_list = []
    
    for name, platform, _ in streamers:
        if platform == 'twitch':
            twitch_list.append(f"🎮 `{name}`")
        elif platform == 'youtube':
            youtube_list.append(f"📺 `{name}`")
        else:
            kick_list.append(f"🦵 `{name}`")
    
    result = "📋 *Твои стримеры:*\n\n"
    if twitch_list:
        result += "*Twitch:*\n" + "\n".join(twitch_list) + "\n\n"
    if youtube_list:
        result += "*YouTube:*\n" + "\n".join(youtube_list) + "\n\n"
    if kick_list:
        result += "*Kick:*\n" + "\n".join(kick_list) + "\n\n"
    result += f"Всего: {len(streamers)}"
    
    await message.answer(result, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

@dp.message(Command("streams"))
async def cmd_check_all_streams_command(message: types.Message):
    """Проверяет статус всех добавленных стримеров"""
    user_id = message.from_user.id
    streamers = await db.get_user_streamers(user_id)
    
    if not streamers:
        await message.answer(
            "📋 У тебя пока нет добавленных стримеров.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard()
        )
        return
    
    await message.answer(
        f"🔄 Проверяю {len(streamers)} стримеров...\nЭто может занять до 15 секунд.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_main_keyboard()
    )
    
    subscriptions = []
    streamer_names = {}
    
    for display_name, platform, identifier in streamers:
        subscriptions.append((platform, identifier, user_id))
        streamer_names[(identifier, platform)] = display_name
    
    streams_data = await stream_api.check_multiple_streams(subscriptions)
    
    online_list = []
    offline_list = []
    
    for (identifier, platform), data in streams_data.items():
        is_live = data.get('is_live', False)
        display_name = streamer_names.get((identifier, platform), identifier)
        
        if platform == 'twitch':
            icon = "🎮"
        elif platform == 'youtube':
            icon = "📺"
        else:
            icon = "🦵"
        
        if is_live:
            title = data.get('title', 'Без названия')[:50]
            url = data.get('url', '#')
            online_list.append(f"{icon} *{display_name}* — {title}\n   [Смотреть]({url})")
        else:
            offline_list.append(f"⚫ *{display_name}* ({icon})")
    
    result_text = "📊 *Статус стримеров:*\n\n"
    
    if online_list:
        result_text += "🔴 *В ЭФИРЕ:*\n" + "\n".join(online_list) + "\n\n"
    else:
        result_text += "🔴 *В эфире:* никто\n\n"
    
    if offline_list:
        result_text += "⚫ *НЕ В ЭФИРЕ:*\n" + "\n".join(offline_list)
    
    await message.answer(result_text, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True, reply_markup=get_main_keyboard())

# Обработка текстовых сообщений (кнопки)
@dp.message()
async def handle_text_buttons(message: types.Message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    # Проверка на отмену (если в режиме ожидания)
    if user_id in awaiting_streamer and text == "❌ Отмена":
        awaiting_streamer.pop(user_id, None)
        await message.answer("❌ Добавление отменено.", parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())
        return
    
    # Обработка кнопок главного меню
    if text == f"{EMOJIS['add']} Добавить стримера":
        await message.answer("🎮 *Выбери платформу:*", parse_mode=ParseMode.MARKDOWN, reply_markup=get_platform_keyboard())
    
    elif text == f"{EMOJIS['list']} Мои стримеры":
        await cmd_list_streamers(message)
    
    elif text == f"{EMOJIS['remove']} Удалить стримера":
        streamers = await db.get_user_streamers(user_id)
        if not streamers:
            await message.answer("📋 У тебя нет стримеров для удаления.", parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())
        else:
            keyboard_buttons = []
            for name, platform, _ in streamers:
                if platform == 'twitch':
                    icon = "🎮"
                elif platform == 'youtube':
                    icon = "📺"
                else:
                    icon = "🦵"
                keyboard_buttons.append([InlineKeyboardButton(text=f"{icon} {name}", callback_data=f"del_{platform}_{name}")])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
            await message.answer("Выбери стримера для удаления:", reply_markup=keyboard)
    
    elif text == f"{EMOJIS['stats']} Статистика":
        await cmd_stats(message)
    
    elif text == f"{EMOJIS['help']} Помощь":
        await cmd_help(message)
    
    # Обработка ввода при добавлении стримера
    elif user_id in awaiting_streamer:
        platform_info = awaiting_streamer[user_id]
        platform = platform_info['platform']
        
        # Убираем флаг ожидания
        awaiting_streamer.pop(user_id, None)
        
        user_input = text.strip()
        
        await message.answer(f"🔍 Проверяю на {platform.upper()}...", parse_mode=ParseMode.MARKDOWN)
        
        # Подготовка поискового запроса в зависимости от платформы
        if platform == 'twitch':
            search_input = user_input.lower()
            await message.answer(f"📝 Ищу `{search_input}` на Twitch...", parse_mode=ParseMode.MARKDOWN)
        
        elif platform == 'kick':
            search_input = user_input.strip()
            if search_input.startswith('@'):
                search_input = search_input[1:]
            await message.answer(f"📝 Ищу `{search_input}` на Kick (регистр не важен)...", parse_mode=ParseMode.MARKDOWN)
        
        else:  # youtube
            search_input = user_input
            await message.answer(f"📝 Ищу канал на YouTube...", parse_mode=ParseMode.MARKDOWN)
        
        # Проверяем существование стримера/канала
        exists, display_name, save_identifier, url = await stream_api.check_streamer_exists(platform, search_input)
        
        if not exists:
            # Ошибка: стример не найден
            if platform == 'twitch':
                await message.answer(
                    f"❌ Стример `{user_input}` не найден на Twitch!\n\n"
                    f"Возможные причины:\n"
                    f"• Такой стример не зарегистрирован на Twitch\n"
                    f"• Проверь правильность написания\n\n"
                    f"💡 Попробуй найти вручную: https://twitch.tv",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=get_main_keyboard()
                )
            elif platform == 'youtube':
                await message.answer(
                    f"❌ Канал `{user_input}` не найден на YouTube!\n\n"
                    f"Возможные причины:\n"
                    f"• Такой канал не существует\n"
                    f"• Проверь правильность ввода\n\n"
                    f"💡 Попробуй ввести username с @ (например, `@ninja`)",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=get_main_keyboard()
                )
            else:  # kick
                await message.answer(
                    f"❌ Стример `{user_input}` не найден на Kick!\n\n"
                    f"Возможные причины:\n"
                    f"• Такой стример не зарегистрирован на Kick\n"
                    f"• Kick временно блокирует запросы от ботов\n\n"
                    f"💡 Попробуй найти вручную: https://kick.com\n"
                    f"📝 Примеры правильных ников: `xqc`, `punch`, `trainwreckstv`",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=get_main_keyboard()
                )
            return
        
        # ========== ВАЖНОЕ ИСПРАВЛЕНИЕ ДЛЯ YOUTUBE ==========
        # Для YouTube всегда сохраняем display_name (имя канала), а не user_input
        if platform == 'youtube':
            save_name = display_name  # Используем имя канала из API
        else:
            save_name = user_input  # Для Twitch и Kick оставляем введённое имя
        
        # Добавляем стримера в базу данных
        success = await db.add_streamer(user_id, save_name, platform, save_identifier, display_name)
        
        if success:
            # Выбираем иконку и название платформы
            if platform == 'twitch':
                platform_icon = "🎮"
                platform_name = "Twitch"
            elif platform == 'youtube':
                platform_icon = "📺"
                platform_name = "YouTube"
            else:
                platform_icon = "🦵"
                platform_name = "Kick"
            
            await message.answer(
                f"✅ {platform_icon} *{display_name}* добавлен в список отслеживания!\n\n"
                f"📺 Платформа: {platform_name}\n"
                f"🔗 {url}\n\n"
                f"Теперь я буду уведомлять тебя, когда {display_name} начнёт стрим!",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_main_keyboard()
            )
        else:
            await message.answer(
                f"⚠️ *{display_name}* уже есть в твоём списке!\n\n"
                f"Используй команду `/list` чтобы посмотреть всех добавленных стримеров.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_main_keyboard()
            )
    
    # Игнорируем остальные сообщения
    else:
        pass

@dp.callback_query()
async def handle_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    if callback.data == "platform_twitch":
        awaiting_streamer[user_id] = {'platform': 'twitch'}
        await callback.message.delete()
        await callback.message.answer(
            "✏️ *Введи логин стримера на Twitch*\n\n"
            "Просто напиши ник (например, `ninja`)\n\n"
            "Для отмены нажми кнопку '❌ Отмена' под полем ввода",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=cancel_keyboard()
        )
        await callback.answer()
    
    elif callback.data == "platform_youtube":
        awaiting_streamer[user_id] = {'platform': 'youtube'}
        await callback.message.delete()
        await callback.message.answer(
            "✏️ *Введи название канала YouTube*\n\n"
            "Можно ввести:\n"
            "• Username (с @ или без)\n"
            "• Ссылку на канал\n\n"
            "Примеры:\n"
            "`@ninja`\n"
            "`https://youtube.com/@ninja`\n\n"
            "Для отмены нажми кнопку '❌ Отмена' под полем ввода",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=cancel_keyboard()
        )
        await callback.answer()
    
    elif callback.data == "platform_kick":
        awaiting_streamer[user_id] = {'platform': 'kick'}
        await callback.message.delete()
        await callback.message.answer(
            "✏️ *Введи никнейм стримера на Kick*\n\n"
            "Просто напиши ник (например, `xqc`)\n\n"
            "Для отмены нажми кнопку '❌ Отмена' под полем ввода",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=cancel_keyboard()
        )
        await callback.answer()
    
    elif callback.data == "back":
        await callback.message.delete()
        await callback.message.answer("🔙 Главное меню:", reply_markup=get_main_keyboard())
        await callback.answer()
    
    elif callback.data.startswith("del_"):
        parts = callback.data[4:].split('_', 1)
        if len(parts) == 2:
            platform, streamer_name = parts
            success = await db.remove_streamer(user_id, streamer_name, platform)
            if success:
                await callback.message.edit_text(f"✅ Стример `{streamer_name}` удалён.", parse_mode=ParseMode.MARKDOWN)
            else:
                await callback.message.edit_text(f"❌ Ошибка при удалении.", parse_mode=ParseMode.MARKDOWN)
        await callback.answer()

async def check_all_streams(manual_mode: bool = False, notifier_user_id: int = None):
    """Основная функция проверки всех стримов"""
    print(f"[{datetime.now()}] 🔍 Запуск проверки стримов...")
    
    all_subscriptions = await db.get_all_subscriptions()
    
    if not all_subscriptions:
        print("Нет активных подписок")
        if manual_mode and notifier_user_id:
            await bot.send_message(notifier_user_id, "📭 Нет активных подписок для проверки.", reply_markup=get_main_keyboard())
        return
    
    # Группируем по (identifier, platform)
    streamer_users = {}
    streamer_names = {}
    
    for user_id, identifier, platform in all_subscriptions:
        key = (identifier, platform)
        if key not in streamer_users:
            streamer_users[key] = []
        streamer_users[key].append(user_id)
        
        # Получаем отображаемое имя из БД
        streamers = await db.get_user_streamers(user_id)
        for name, p, ident in streamers:
            if p == platform and ident == identifier:
                streamer_names[(identifier, platform)] = name
                break
    
    # Получаем статусы всех стримов
    subscriptions_list = [(platform, identifier, user_id) for (identifier, platform), users in streamer_users.items() for user_id in users]
    streams_data = await stream_api.check_multiple_streams(subscriptions_list)
    
    for (identifier, platform), data in streams_data.items():
        is_live = data.get('is_live', False)
        last_status = await db.get_last_status(identifier, platform)
        display_name = streamer_names.get((identifier, platform), identifier)
        
        if is_live and not last_status:
            await db.update_streamer_status(identifier, platform, True)
            
            title = data.get('title', 'Без названия')[:100]
            url = data.get('url', '#')
            
            if platform == 'twitch':
                icon = "🔴"
                platform_name = "Twitch"
            elif platform == 'youtube':
                icon = "📺"
                platform_name = "YouTube"
            else:
                icon = "🦵"
                platform_name = "Kick"
            
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
            print(f"📴 Стрим {display_name} ({platform}) закончился")
    
    if manual_mode and notifier_user_id:
        await bot.send_message(
            notifier_user_id,
            "✅ Проверка завершена! Если кто-то начал стрим, ты получишь уведомление.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard()
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
    print("🎮 Поддерживаемые платформы: Twitch, YouTube, Kick")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
