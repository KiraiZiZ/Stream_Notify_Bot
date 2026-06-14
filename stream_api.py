import aiohttp
import time
import os
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv

load_dotenv()

# YouTube API Key
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

# Twitch токены
_twitch_tokens = {
    "access_token": None,
    "refresh_token": None,
    "client_id": None,
    "expires_at": 0
}

def set_twitch_tokens(access_token: str, refresh_token: str, client_id: str):
    """Устанавливает токены Twitch"""
    _twitch_tokens["access_token"] = access_token
    _twitch_tokens["refresh_token"] = refresh_token
    _twitch_tokens["client_id"] = client_id
    _twitch_tokens["expires_at"] = time.time() + 50 * 24 * 3600

async def refresh_twitch_token() -> bool:
    """Обновляет Twitch access token"""
    if not _twitch_tokens["refresh_token"] or not _twitch_tokens["client_id"]:
        return False
    
    async with aiohttp.ClientSession() as session:
        params = {
            'grant_type': 'refresh_token',
            'refresh_token': _twitch_tokens["refresh_token"],
            'client_id': _twitch_tokens["client_id"]
        }
        async with session.post('https://id.twitch.tv/oauth2/token', params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                _twitch_tokens["access_token"] = data.get('access_token')
                _twitch_tokens["expires_at"] = time.time() + data.get('expires_in', 3600)
                return True
            return False

async def get_valid_twitch_token() -> Optional[str]:
    """Возвращает валидный Twitch access token"""
    if not _twitch_tokens["access_token"]:
        return None
    
    if time.time() >= _twitch_tokens["expires_at"] - 3600:
        if not await refresh_twitch_token():
            return None
    
    return _twitch_tokens["access_token"]

# ========== TWITCH ==========
async def check_twitch_streamer_exists(streamer_login: str) -> bool:
    """Проверяет, существует ли стример на Twitch"""
    access_token = await get_valid_twitch_token()
    client_id = _twitch_tokens["client_id"]
    
    if not access_token or not client_id:
        return False
    
    headers = {
        'Client-ID': client_id,
        'Authorization': f'Bearer {access_token}'
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(f'https://api.twitch.tv/helix/users?login={streamer_login}', headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                return len(data.get('data', [])) > 0
            return False

async def get_twitch_stream_info(streamer_login: str):
    """Проверяет стрим на Twitch"""
    access_token = await get_valid_twitch_token()
    client_id = _twitch_tokens["client_id"]
    
    if not access_token or not client_id:
        return None
    
    headers = {
        'Client-ID': client_id,
        'Authorization': f'Bearer {access_token}'
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(f'https://api.twitch.tv/helix/streams?user_login={streamer_login}', headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                if data['data']:
                    stream = data['data'][0]
                    return {
                        'is_live': True,
                        'title': stream.get('title', 'Без названия'),
                        'game': stream.get('game_name', 'Неизвестная игра'),
                        'viewer_count': stream.get('viewer_count', 0),
                        'url': f'https://twitch.tv/{streamer_login}'
                    }
                else:
                    return {'is_live': False}
            return None

# ========== YOUTUBE ==========
async def check_youtube_channel_exists(channel_input: str) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
    """
    Проверяет, существует ли канал на YouTube.
    Принимает: channel_id или username (c @ или без) или ссылку
    Возвращает: (exists, channel_name, channel_id, url)
    """
    if not YOUTUBE_API_KEY:
        print("❌ YouTube API ключ не настроен")
        return (False, None, None, None)
    
    original_input = channel_input.strip()
    channel_input = original_input
    
    # Извлекаем ID/username из ссылки
    if 'youtube.com' in channel_input or 'youtu.be' in channel_input:
        if '/@' in channel_input:
            # Ссылка вида youtube.com/@username
            channel_input = channel_input.split('/@')[-1].split('/')[0].split('?')[0]
        elif '/channel/' in channel_input:
            channel_input = channel_input.split('/channel/')[-1].split('/')[0].split('?')[0]
        elif '/c/' in channel_input:
            channel_input = channel_input.split('/c/')[-1].split('/')[0].split('?')[0]
        else:
            # Другие форматы ссылок
            pass
    
    # Убираем @ если есть
    if channel_input.startswith('@'):
        channel_input = channel_input[1:]
    
    async with aiohttp.ClientSession() as session:
        # Пробуем найти по username (handle)
        async with session.get(
            f'https://www.googleapis.com/youtube/v3/channels',
            params={
                'part': 'snippet',
                'forHandle': channel_input,
                'key': YOUTUBE_API_KEY
            }
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                if data.get('items'):
                    channel = data['items'][0]
                    channel_id = channel['id']
                    channel_name = channel['snippet']['title']
                    url = f'https://youtube.com/channel/{channel_id}'
                    print(f"✅ YouTube: найден канал '{channel_name}' (ID: {channel_id})")
                    return (True, channel_name, channel_id, url)
        
        # Пробуем как channel_id
        async with session.get(
            f'https://www.googleapis.com/youtube/v3/channels',
            params={
                'part': 'snippet',
                'id': channel_input,
                'key': YOUTUBE_API_KEY
            }
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                if data.get('items'):
                    channel = data['items'][0]
                    channel_id = channel['id']
                    channel_name = channel['snippet']['title']
                    url = f'https://youtube.com/channel/{channel_id}'
                    print(f"✅ YouTube: найден канал '{channel_name}' (ID: {channel_id})")
                    return (True, channel_name, channel_id, url)
        
        # Пробуем поиск по ключевым словам (как запасной вариант)
        async with session.get(
            f'https://www.googleapis.com/youtube/v3/search',
            params={
                'part': 'snippet',
                'q': channel_input,
                'type': 'channel',
                'maxResults': 1,
                'key': YOUTUBE_API_KEY
            }
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                if data.get('items'):
                    channel = data['items'][0]
                    channel_id = channel['id']['channelId']
                    channel_name = channel['snippet']['channelTitle']
                    url = f'https://youtube.com/channel/{channel_id}'
                    print(f"✅ YouTube: найден канал '{channel_name}' через поиск")
                    return (True, channel_name, channel_id, url)
        
        print(f"❌ YouTube: канал '{original_input}' не найден")
        return (False, None, None, None)

async def get_youtube_stream_info(channel_id: str):
    """Проверяет, идёт ли стрим на YouTube канале"""
    if not YOUTUBE_API_KEY:
        return None
    
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f'https://www.googleapis.com/youtube/v3/search',
            params={
                'part': 'snippet',
                'channelId': channel_id,
                'eventType': 'live',
                'type': 'video',
                'key': YOUTUBE_API_KEY
            }
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                if data.get('items'):
                    video = data['items'][0]
                    video_id = video['id']['videoId']
                    # Получаем имя канала из snippet
                    channel_name = video['snippet'].get('channelTitle', 'Неизвестный канал')
                    return {
                        'is_live': True,
                        'title': video['snippet'].get('title', 'Без названия'),
                        'channel_name': channel_name,
                        'url': f'https://youtube.com/watch?v={video_id}'
                    }
                else:
                    return {'is_live': False}
            return None

# ========== KICK ==========
async def check_kick_streamer_exists(streamer_slug: str) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
    """
    Проверяет, существует ли стример на Kick.com.
    Принимает: slug (никнейм) стримера (регистр не важен).
    Возвращает: (exists, display_name, slug, url)
    """
    # Приводим к нижнему регистру для поиска
    original_slug = streamer_slug.strip()
    streamer_slug = original_slug.lower()
    
    if streamer_slug.startswith('@'):
        streamer_slug = streamer_slug[1:]
        original_slug = original_slug[1:]
    
    async with aiohttp.ClientSession() as session:
        url = f'https://kick.com/api/v2/channels/{streamer_slug}'
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://kick.com/',
            'Origin': 'https://kick.com',
        }
        
        try:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    channel_name = data.get('slug', streamer_slug)
                    # Отображаемое имя берём из user.username (сохраняем оригинальный регистр)
                    display_name = data.get('user', {}).get('username', channel_name)
                    url = f'https://kick.com/{channel_name}'
                    print(f"✅ Kick: найден {display_name} (slug: {channel_name})")
                    return (True, display_name, channel_name, url)
                elif resp.status == 404:
                    print(f"❌ Kick: {streamer_slug} не найден (404)")
                    return (False, None, None, None)
                else:
                    print(f"❌ Kick: ошибка {resp.status} для {streamer_slug}")
                    return (False, None, None, None)
        except Exception as e:
            print(f"❌ Ошибка при запросе к Kick: {e}")
            return (False, None, None, None)


async def get_kick_stream_info(streamer_slug: str):
    """
    Проверяет, идёт ли стрим на Kick.com.
    """
    streamer_slug = streamer_slug.strip().lower()
    if streamer_slug.startswith('@'):
        streamer_slug = streamer_slug[1:]
    
    async with aiohttp.ClientSession() as session:
        url = f'https://kick.com/api/v2/channels/{streamer_slug}'
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://kick.com/',
            'Origin': 'https://kick.com',
        }
        
        try:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    print(f"❌ Kick API ошибка: {resp.status} для {streamer_slug}")
                    return None
                
                data = await resp.json()
                livestream = data.get('livestream')
                
                if livestream and livestream.get('is_live', False):
                    # Получаем правильное отображаемое имя
                    display_name = data.get('user', {}).get('username', streamer_slug)
                    return {
                        'is_live': True,
                        'title': livestream.get('session_title', 'Без названия'),
                        'viewer_count': livestream.get('viewer_count', 0),
                        'category': livestream.get('category', {}).get('name', 'Неизвестная категория'),
                        'channel_name': display_name,
                        'url': f'https://kick.com/{streamer_slug}'
                    }
                else:
                    return {'is_live': False}
        except Exception as e:
            print(f"❌ Ошибка при проверке стрима Kick: {e}")
            return None

# ========== ОБЩИЕ ФУНКЦИИ ==========
async def check_streamer_exists(platform: str, identifier: str) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
    """
    Проверяет, существует ли стример/канал.
    Возвращает: (exists, display_name, save_identifier, url)
    """
    if platform == 'twitch':
        exists = await check_twitch_streamer_exists(identifier)
        if exists:
            return (True, identifier, identifier, f'https://twitch.tv/{identifier}')
        return (False, None, None, None)
    
    elif platform == 'youtube':
        return await check_youtube_channel_exists(identifier)
    
    elif platform == 'kick':
        return await check_kick_streamer_exists(identifier)
    
    return (False, None, None, None)

async def get_stream_info(platform: str, identifier: str):
    """Получает информацию о стриме в зависимости от платформы"""
    if platform == 'twitch':
        return await get_twitch_stream_info(identifier)
    elif platform == 'youtube':
        return await get_youtube_stream_info(identifier)
    elif platform == 'kick':
        return await get_kick_stream_info(identifier)
    return None

async def check_multiple_streams(subscriptions: List[tuple]) -> Dict:
    """
    Проверяет несколько стримов.
    subscriptions: список кортежей (platform, identifier, user_id)
    """
    results = {}
    
    twitch_streamers = []
    youtube_streamers = []
    kick_streamers = []
    
    for platform, identifier, _ in subscriptions:
        if platform == 'twitch':
            if identifier not in twitch_streamers:
                twitch_streamers.append(identifier)
        elif platform == 'youtube':
            if identifier not in youtube_streamers:
                youtube_streamers.append(identifier)
        elif platform == 'kick':
            if identifier not in kick_streamers:
                kick_streamers.append(identifier)
    
    for login in twitch_streamers:
        info = await get_twitch_stream_info(login)
        if info:
            results[(login, 'twitch')] = info
    
    for channel_id in youtube_streamers:
        info = await get_youtube_stream_info(channel_id)
        if info:
            results[(channel_id, 'youtube')] = info
    
    for slug in kick_streamers:
        info = await get_kick_stream_info(slug)
        if info:
            results[(slug, 'kick')] = info
    
    return results
