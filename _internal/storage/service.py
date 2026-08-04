from supabase import create_client, Client

from config.environments import Environments
from .storage import IStorageService
from .exceptions import StorageUploadException


class SupabaseStorageService(IStorageService):
    """Supabase Storage implementation of IStorageService."""

    client: Client

    def __init__(self, envs: Environments):
        self.client = create_client(envs.SUPABASE_URL, envs.SUPABASE_SERVICE_ROLE_KEY)
        self.bucket_name = envs.SUPABASE_BUCKET_NAME

    def upload(self, content: bytes, filename: str, content_type: str) -> str:
        try:
            bucket = self.client.storage.from_(self.bucket_name)
            bucket.upload(filename, content, {"content-type": content_type})
            return bucket.get_public_url(filename)
        except Exception as e:
            raise StorageUploadException(str(e)) from e
