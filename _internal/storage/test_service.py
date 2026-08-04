from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from .exceptions import StorageUploadException
from .service import SupabaseStorageService


@pytest.fixture
def envs() -> Any:
    envs = MagicMock()
    envs.SUPABASE_URL = "https://xxxxx.supabase.co"
    envs.SUPABASE_SERVICE_ROLE_KEY = "fake-service-role-key"
    envs.SUPABASE_BUCKET_NAME = "zera-reports"
    return envs


class TestInit:
    @patch("_internal.storage.service.create_client")
    def test_creates_the_supabase_client_with_the_url_and_service_role_key(self, mock_create_client, envs):
        SupabaseStorageService(envs)

        mock_create_client.assert_called_once_with(envs.SUPABASE_URL, envs.SUPABASE_SERVICE_ROLE_KEY)

    @patch("_internal.storage.service.create_client")
    def test_stores_the_bucket_name_from_the_environment(self, mock_create_client, envs):
        service = SupabaseStorageService(envs)

        assert service.bucket_name == "zera-reports"


class TestUpload:
    @patch("_internal.storage.service.create_client")
    def test_uploads_the_content_and_returns_the_public_url(self, mock_create_client, envs):
        bucket = MagicMock()
        bucket.get_public_url.return_value = "https://xxxxx.supabase.co/storage/v1/object/public/zera-reports/report.pdf"
        mock_create_client.return_value.storage.from_.return_value = bucket
        service = SupabaseStorageService(envs)

        result = service.upload(content=b"%PDF-1.7", filename="report.pdf", content_type="application/pdf")

        mock_create_client.return_value.storage.from_.assert_called_once_with("zera-reports")
        bucket.upload.assert_called_once_with("report.pdf", b"%PDF-1.7", {"content-type": "application/pdf"})
        bucket.get_public_url.assert_called_once_with("report.pdf")
        assert result == "https://xxxxx.supabase.co/storage/v1/object/public/zera-reports/report.pdf"

    @patch("_internal.storage.service.create_client")
    def test_wraps_upload_failures_in_storage_upload_exception(self, mock_create_client, envs):
        bucket = MagicMock()
        bucket.upload.side_effect = Exception("404 Not Found")
        mock_create_client.return_value.storage.from_.return_value = bucket
        service = SupabaseStorageService(envs)

        with pytest.raises(StorageUploadException):
            service.upload(content=b"%PDF-1.7", filename="report.pdf", content_type="application/pdf")
