import os
from typing import List, Tuple, Optional
from supabase import create_client, Client
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

async def init_db():
    """Проверяет подключение к Supabase"""
    try:
        supabase.table('users').select('count', count='exact').limit(1).execute()
        print("✅ Подключение к Supabase успешно")
        return True
    except Exception as e:
        print(f"❌ Ошибка подключения к Supabase: {e}")
        return False

async def add_user(user_id: int, username: str = None):
    """Добавляет пользователя"""
    try:
        supabase.table('users').upsert({
            'user_id': user_id,
            'username': username,
            'first_seen': datetime.now().isoformat()
        }).execute()
    except Exception as e:
        print(f"Ошибка добавления пользователя: {e}")

async def add_streamer(user_id: int, streamer_login: str, platform: str = 'twitch', save_identifier: str = None, display_name: str = None) -> bool:
    """
    Добавляет стримера для отслеживания.
    - streamer_login: то, что ввёл пользователь (для отображения)
    - save_identifier: уникальный ID канала (channel_id для YouTube)
    - display_name: отображаемое имя канала
    """
    try:
        identifier_to_save = save_identifier if save_identifier else streamer_login.lower()
        name_to_display = display_name if display_name else streamer_login
        
        supabase.table('streamers').insert({
            'user_id': user_id,
            'streamer_login': name_to_display,  # Отображаемое имя
            'identifier': identifier_to_save,  # Уникальный ID для API
            'platform': platform,
            'is_active': True,
            'last_status': False,
        }).execute()
        return True
    except Exception as e:
        if 'duplicate key' in str(e).lower() or 'unique constraint' in str(e).lower():
            return False
        print(f"Ошибка добавления стримера: {e}")
        return False

async def remove_streamer(user_id: int, streamer_login: str, platform: str = None) -> bool:
    """Удаляет стримера"""
    try:
        query = supabase.table('streamers').delete().eq('user_id', user_id)
        
        if platform:
            query = query.eq('platform', platform)
        query = query.eq('streamer_login', streamer_login)
        
        result = query.execute()
        return len(result.data) > 0
    except Exception as e:
        print(f"Ошибка удаления: {e}")
        return False

async def get_user_streamers(user_id: int) -> List[Tuple[str, str]]:
    """Список стримеров пользователя (display_name, platform)"""
    try:
        result = supabase.table('streamers')\
            .select('streamer_login, platform, identifier')\
            .eq('user_id', user_id)\
            .eq('is_active', True)\
            .execute()
        return [(row['streamer_login'], row['platform'], row['identifier']) for row in result.data]
    except Exception as e:
        print(f"Ошибка получения списка: {e}")
        return []

async def get_all_subscriptions() -> List[Tuple[int, str, str]]:
    """Все подписки (user_id, identifier, platform)"""
    try:
        result = supabase.table('streamers')\
            .select('user_id, identifier, platform')\
            .eq('is_active', True)\
            .execute()
        return [(row['user_id'], row['identifier'], row['platform']) for row in result.data]
    except Exception as e:
        print(f"Ошибка получения подписок: {e}")
        return []

async def update_streamer_status(identifier: str, platform: str, is_live: bool):
    """Обновляет статус стримера"""
    try:
        supabase.table('streamers')\
            .update({'last_status': is_live})\
            .eq('identifier', identifier)\
            .eq('platform', platform)\
            .execute()
    except Exception as e:
        print(f"Ошибка обновления статуса: {e}")

async def get_last_status(identifier: str, platform: str) -> Optional[bool]:
    """Последний известный статус стримера"""
    try:
        result = supabase.table('streamers')\
            .select('last_status')\
            .eq('identifier', identifier)\
            .eq('platform', platform)\
            .limit(1)\
            .execute()
        return result.data[0]['last_status'] if result.data else None
    except Exception as e:
        print(f"Ошибка получения статуса: {e}")
        return None

async def get_user_count() -> int:
    """Количество пользователей"""
    try:
        result = supabase.table('users').select('count', count='exact').execute()
        return result.count if result.count else 0
    except Exception:
        return 0

async def get_total_subscriptions_count() -> int:
    """Общее количество подписок"""
    try:
        result = supabase.table('streamers').select('count', count='exact').execute()
        return result.count if result.count else 0
    except Exception:
        return 0
