# backend/app/services/storage.py
from supabase import create_client, Client
from app.config import settings

_client: Client | None = None


def get_storage_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
    return _client


def upload_photo(file_bytes: bytes, path: str, content_type: str = "image/jpeg") -> str:
    client = get_storage_client()
    client.storage.from_(settings.SUPABASE_BUCKET).upload(
        path, file_bytes, {"content-type": content_type, "upsert": "false"}
    )
    return path


def delete_photo(path: str) -> None:
    client = get_storage_client()
    client.storage.from_(settings.SUPABASE_BUCKET).remove([path])


def get_public_url(path: str) -> str:
    client = get_storage_client()
    return client.storage.from_(settings.SUPABASE_BUCKET).get_public_url(path)
