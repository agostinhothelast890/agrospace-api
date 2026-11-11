from supabase import Client, create_client

from app.config import SUPABASE_KEY, SUPABASE_URL


def get_client() -> Client:
    # New client per call, so one user's session never leaks to another.
    return create_client(SUPABASE_URL, SUPABASE_KEY)
