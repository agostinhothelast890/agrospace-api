from supabase import Client, create_client

from app.config import SUPABASE_KEY, SUPABASE_URL


def get_client() -> Client:
    # New client per call, so one user's session never leaks to another.
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def get_user_client(token: str) -> Client:
    # Client that acts as the logged-in user (so RLS applies).
    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    client.postgrest.auth(token)
    return client
