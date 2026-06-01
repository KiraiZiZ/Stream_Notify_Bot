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
    _tokens["expires_at"] = time.time() + 50 * 24 * 3600  # 50 дней запас

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
                _tokens["expires_in"] = data.get('expires_in', 3600)
                _tokens["expires_at"] = time.time() + _tokens["expires_in"]
                print("✅ Access token обновлён")
                return True
            else:
                error = await resp.text()
                print(f"❌ Ошибка обновления токена: {resp.status} - {error}")
                return False

async def get_valid_access_token() -> str:
    """Возвращает валидный access token (автоматически обновляет если нужно)"""
    if time.time() >= _tokens["expires_at"] - 3600:  # Обновляем за час до истечения
        await refresh_access_token()
    return _tokens["access_token"]

async def check_multiple_streams(streamers: List[str]) -> Dict[str, Dict]:
    """Проверяет несколько стримеров за раз (использует сохранённые токены)"""
    if not streamers:
        return {}
    
    access_token = await get_valid_access_token()
    client_id = _tokens["client_id"]
    
    if not access_token or not client_id:
        print("❌ Нет валидного access_token или client_id")
        return {login: {'is_live': False} for login in streamers}
    
    headers = {
        'Client-ID': client_id,
        'Authorization': f'Bearer {access_token}'
    }
    
    async with aiohttp.ClientSession() as session:
        params = {'user_login': streamers}
        async with session.get('https://api.twitch.tv/helix/streams', headers=headers, params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                online = {item['user_login'].lower(): item for item in data['data']}
                
                results = {}
                for login in streamers:
                    if login.lower() in online:
                        s = online[login.lower()]
                        results[login] = {
                            'is_live': True,
                            'title': s.get('title', 'Без названия'),
                            'game': s.get('game_name', 'Неизвестная игра'),
                            'viewer_count': s.get('viewer_count', 0)
                        }
                    else:
                        results[login] = {'is_live': False}
                return results
            elif resp.status == 401:  # Unauthorized — токен умер
                print("⚠️ Токен истёк, пробуем обновить...")
                if await refresh_access_token():
                    # Повторяем запрос с новым токеном
                    return await check_multiple_streams(streamers)
                else:
                    print("❌ Не удалось обновить токен")
                    return {login: {'is_live': False} for login in streamers}
            else:
                print(f"❌ Ошибка API: {resp.status}")
                return {login: {'is_live': False} for login in streamers}

async def get_stream_info(streamer_login: str) -> Optional[Dict]:
    """Проверяет стрим у одного стримера"""
    results = await check_multiple_streams([streamer_login])
    return results.get(streamer_login)
