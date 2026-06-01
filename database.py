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
        print(f"❌ Ошибка подключения: {e}")
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

async def add_streamer(user_id: int, streamer_login: str) -> bool:
    """Добавляет стримера"""
    try:
        supabase.table('streamers').insert({
            'user_id': user_id,
            'streamer_login': streamer_login.lower(),
            'is_active': True,
            'last_status': False,
        }).execute()
        return True
    except Exception as e:
        if 'duplicate key' in str(e).lower():
            return False
        print(f"Ошибка: {e}")
        return False

async def remove_streamer(user_id: int, streamer_login: str) -> bool:
    """Удаляет стримера"""
    try:
        result = supabase.table('streamers')\
            .delete()\
            .eq('user_id', user_id)\
            .eq('streamer_login', streamer_login.lower())\
            .execute()
        return len(result.data) > 0
    except Exception as e:
        print(f"Ошибка: {e}")
        return False

async def get_user_streamers(user_id: int) -> List[str]:
    """Список стримеров пользователя"""
    try:
        result = supabase.table('streamers')\
            .select('streamer_login')\
            .eq('user_id', user_id)\
            .eq('is_active', True)\
            .execute()
        return [row['streamer_login'] for row in result.data]
    except Exception as e:
        print(f"Ошибка: {e}")
        return []

async def get_all_subscriptions() -> List[Tuple[int, str]]:
    """Все подписки"""
    try:
        result = supabase.table('streamers')\
            .select('user_id, streamer_login')\
            .eq('is_active', True)\
            .execute()
        return [(row['user_id'], row['streamer_login']) for row in result.data]
    except Exception as e:
        print(f"Ошибка: {e}")
        return []

async def update_streamer_status(streamer_login: str, is_live: bool):
    """Обновляет статус стримера"""
    try:
        supabase.table('streamers')\
            .update({'last_status': is_live})\
            .eq('streamer_login', streamer_login.lower())\
            .execute()
    except Exception as e:
        print(f"Ошибка: {e}")

async def get_last_status(streamer_login: str) -> Optional[bool]:
    """Последний статус стримера"""
    try:
        result = supabase.table('streamers')\
            .select('last_status')\
            .eq('streamer_login', streamer_login.lower())\
            .limit(1)\
            .execute()
        return result.data[0]['last_status'] if result.data else None
    except Exception as e:
        print(f"Ошибка: {e}")
        return None

async def get_user_count() -> int:
    """Количество пользователей"""
    try:
        result = supabase.table('users').select('count', count='exact').execute()
        return result.count if result.count else 0
    except Exception as e:
        return 0
