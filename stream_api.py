import aiohttp
import time
import os
from typing import Dict, List, Optional
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
        # Проверяем существование
        async with session.get(f'https://api.twitch.tv/helix/users?login={streamer_login}', headers=headers) as resp:
            if resp.status == 200:
                user_data = await resp.json()
                if not user_data.get('data'):
                    return None
            else:
                return None
        
        # Проверяем стрим
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
async def check_youtube_channel_exists(channel_input: str) -> tuple:
    """
    Проверяет, существует ли канал на YouTube.
    Принимает: channel_id или username (c @ или без)
    Возвращает: (exists, channel_id, channel_name, url)
    """
    if not YOUTUBE_API_KEY:
        return (False, None, None, None)
    
    channel_input = channel_input.strip().lower()
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
                    return (True, channel_id, channel_name, url)
        
        # Если не нашли, пробуем как channel_id
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
                    return (True, channel_id, channel_name, url)
        
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
                    return {
                        'is_live': True,
                        'title': video['snippet'].get('title', 'Без названия'),
                        'channel_name': video['snippet'].get('channelTitle', 'Неизвестный канал'),
                        'video_id': video_id,
                        'url': f'https://youtube.com/watch?v={video_id}'
                    }
                else:
                    return {'is_live': False}
            return None

# ========== ОБЩИЕ ФУНКЦИИ ==========
async def get_stream_info(platform: str, identifier: str):
    """Получает информацию о стриме в зависимости от платформы"""
    if platform == 'twitch':
        return await get_twitch_stream_info(identifier)
    elif platform == 'youtube':
        # Для YouTube identifier - это channel_id (сохранённый в БД)
        return await get_youtube_stream_info(identifier)
    return None

async def check_streamer_exists(platform: str, identifier: str) -> tuple:
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
        exists, channel_id, channel_name, url = await check_youtube_channel_exists(identifier)
        if exists:
            return (True, channel_name, channel_id, url)
        return (False, None, None, None)
    
    return (False, None, None, None)

async def check_multiple_streams(subscriptions: List[tuple]) -> Dict:
    """
    Проверяет несколько стримов.
    subscriptions: список кортежей (platform, identifier, user_id)
    """
    results = {}
    
    # Группируем по платформам
    twitch_streamers = []
    youtube_streamers = []
    
    for platform, identifier, _ in subscriptions:
        if platform == 'twitch':
            if identifier not in twitch_streamers:
                twitch_streamers.append(identifier)
        elif platform == 'youtube':
            if identifier not in youtube_streamers:
                youtube_streamers.append(identifier)
    
    # Проверяем Twitch
    for login in twitch_streamers:
        info = await get_twitch_stream_info(login)
        if info:
            results[(login, 'twitch')] = info
    
    # Проверяем YouTube
    for channel_id in youtube_streamers:
        info = await get_youtube_stream_info(channel_id)
        if info:
            results[(channel_id, 'youtube')] = info
    
    return results
