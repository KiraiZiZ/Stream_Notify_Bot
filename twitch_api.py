import aiohttp
import time
from typing import Dict, List, Optional

# Хранилище для токенов
_tokens = {
    "access_token": None,
    "refresh_token": None,
    "client_id": None,
    "expires_at": 0
}

def set_tokens(access_token: str, refresh_token: str, client_id: str):
    """Устанавливает токены из twitchtokengenerator.com"""
    _tokens["access_token"] = access_token
    _tokens["refresh_token"] = refresh_token
    _tokens["client_id"] = client_id
    _tokens["expires_at"] = time.time() + 50 * 24 * 3600

async def refresh_access_token() -> bool:
    """Обновляет access token через refresh token"""
    if not _tokens["refresh_token"] or not _tokens["client_id"]:
        print("❌ Нет refresh_token или client_id для обновления")
        return False
    
    async with aiohttp.ClientSession() as session:
        params = {
            'grant_type': 'refresh_token',
            'refresh_token': _tokens["refresh_token"],
            'client_id': _tokens["client_id"]
        }
        async with session.post('https://id.twitch.tv/oauth2/token', params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                _tokens["access_token"] = data.get('access_token')
                _tokens["expires_at"] = time.time() + data.get('expires_in', 3600)
                print("✅ Access token обновлён")
                return True
            else:
                error = await resp.text()
                print(f"❌ Ошибка обновления токена: {resp.status} - {error}")
                return False

async def get_valid_access_token() -> Optional[str]:
    """Возвращает валидный access token"""
    if not _tokens["access_token"]:
        print("❌ Access token не установлен")
        return None
    
    if time.time() >= _tokens["expires_at"] - 3600:
        print("⏰ Токен истекает, обновляем...")
        if not await refresh_access_token():
            return None
    
    return _tokens["access_token"]

async def check_streamer_exists(streamer_login: str) -> bool:
    """Проверяет, существует ли стример на Twitch"""
    access_token = await get_valid_access_token()
    client_id = _tokens["client_id"]
    
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

async def get_stream_info(streamer_login: str):
    """Проверяет стримера и его стрим. Возвращает None если стример не существует"""
    access_token = await get_valid_access_token()
    client_id = _tokens["client_id"]
    
    if not access_token or not client_id:
        return None
    
    headers = {
        'Client-ID': client_id,
        'Authorization': f'Bearer {access_token}'
    }
    
    async with aiohttp.ClientSession() as session:
        # 1. Проверяем существование стримера
        async with session.get(f'https://api.twitch.tv/helix/users?login={streamer_login}', headers=headers) as resp:
            if resp.status == 200:
                user_data = await resp.json()
                if not user_data.get('data'):
                    print(f"❌ Стример {streamer_login} НЕ СУЩЕСТВУЕТ на Twitch")
                    return None
                print(f"✅ Стример {streamer_login} существует")
            else:
                print(f"❌ Ошибка API: {resp.status}")
                return None
        
        # 2. Проверяем, идёт ли стрим
        async with session.get(f'https://api.twitch.tv/helix/streams?user_login={streamer_login}', headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                if data['data']:
                    stream = data['data'][0]
                    return {
                        'is_live': True,
                        'title': stream.get('title', 'Без названия'),
                        'game': stream.get('game_name', 'Неизвестная игра'),
                        'viewer_count': stream.get('viewer_count', 0)
                    }
                else:
                    return {'is_live': False}
            else:
                return None

async def check_multiple_streams(streamers: List[str]) -> Dict[str, Dict]:
    """Проверяет несколько стримеров за раз"""
    if not streamers:
        return {}
    
    access_token = await get_valid_access_token()
    client_id = _tokens["client_id"]
    
    if not access_token or not client_id:
        return {login: {'is_live': False} for login in streamers}
    
    headers = {
        'Client-ID': client_id,
        'Authorization': f'Bearer {access_token}'
    }
    
    async with aiohttp.ClientSession() as session:
        # Сначала проверяем, какие стримеры вообще существуют
        users_params = {'login': streamers}
        async with session.get('https://api.twitch.tv/helix/users', headers=headers, params=users_params) as resp:
            if resp.status == 200:
                users_data = await resp.json()
                existing_logins = {user['login'].lower() for user in users_data.get('data', [])}
            else:
                existing_logins = set()
        
        # Проверяем стримы только у существующих
        params = {'user_login': streamers}
        async with session.get('https://api.twitch.tv/helix/streams', headers=headers, params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                online = {item['user_login'].lower(): item for item in data['data']}
                
                results = {}
                for login in streamers:
                    if login.lower() not in existing_logins:
                        results[login] = {'is_live': False, 'exists': False}
                    elif login.lower() in online:
                        s = online[login.lower()]
                        results[login] = {
                            'is_live': True,
                            'title': s.get('title', 'Без названия'),
                            'game': s.get('game_name', 'Неизвестная игра'),
                            'viewer_count': s.get('viewer_count', 0),
                            'exists': True
                        }
                    else:
                        results[login] = {'is_live': False, 'exists': True}
                return results
            else:
                return {login: {'is_live': False} for login in streamers}
