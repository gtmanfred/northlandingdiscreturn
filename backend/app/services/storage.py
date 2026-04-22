# backend/app/services/storage.py
from supabase import create_client, Client
from app.config import settings

_client: Client | None = None


def get_storage_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
    return _client


def storage_path_to_url(path: str) -> str:
    """Convert a bucket-relative storage path to a full public URL.

    Also accepts an already-absolute URL and returns it unchanged, so this
    is safe to call on both old (relative) and new (absolute) photo_path values.
    """
    if path.startswith("http://") or path.startswith("https://"):
        return path
    base = settings.SUPABASE_URL.rstrip("/")
    return f"{base}/storage/v1/object/public/{settings.SUPABASE_BUCKET}/{path}"


def upload_photo(file_bytes: bytes, path: str, content_type: str = "image/jpeg") -> str:
    client = get_storage_client()
    client.storage.from_(settings.SUPABASE_BUCKET).upload(
        path, file_bytes, {"content-type": content_type, "upsert": "false"}
    )
    return path


def delete_photo(path: str) -> None:
    client = get_storage_client()
    client.storage.from_(settings.SUPABASE_BUCKET).remove([path])
