from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from google.cloud.exceptions import NotFound

from cloud_storage_manager import (
    DeleteError,
    DownloadError,
    ListError,
    NotFoundError,
    UploadError,
)
from cloud_storage_manager.gcp_storage import GcpClientStorage

from .factories import aws_config, gcp_config


@pytest.fixture
def gcp_sdk():
    with (
        patch("cloud_storage_manager.gcp_storage.storage.Client") as client_cls,
        patch(
            "cloud_storage_manager.gcp_storage.service_account.Credentials.from_service_account_info"
        ) as creds,
    ):
        yield SimpleNamespace(client_cls=client_cls, creds=creds)


@pytest.fixture
def bucket(gcp_sdk):
    return gcp_sdk.client_cls.return_value.get_bucket.return_value


@pytest.fixture
def blob(bucket):
    return bucket.blob.return_value


@pytest.fixture
def storage(gcp_sdk):
    return GcpClientStorage(gcp_config())


def test_init_builds_client_from_service_account(gcp_sdk, storage):
    gcp_sdk.creds.assert_called_once_with({"type": "x"})
    gcp_sdk.client_cls.assert_called_once_with(credentials=gcp_sdk.creds.return_value)
    gcp_sdk.client_cls.return_value.get_bucket.assert_called_once_with("test-bucket")
    assert storage.bucket_name == "test-bucket"


def test_init_requires_gcp_config():
    with pytest.raises(ValueError, match="GCP configuration is required"):
        GcpClientStorage(aws_config())


async def test_upload_uses_filename(storage, bucket, blob, sample_file):
    assert await storage.upload(sample_file, "v/clip.mp4") == "v/clip.mp4"
    bucket.blob.assert_called_with("v/clip.mp4")
    blob.upload_from_filename.assert_called_once_with(str(sample_file))


async def test_upload_defaults_cloud_path_to_file_name(storage, sample_file):
    assert await storage.upload(sample_file) == "clip.mp4"


async def test_upload_failure(storage, blob, sample_file):
    blob.upload_from_filename.side_effect = RuntimeError("boom")
    with pytest.raises(UploadError, match="boom"):
        await storage.upload(sample_file, "x")


async def test_upload_bytes_explicit_and_guessed_type(storage, blob):
    assert await storage.upload_bytes(b"# x", "a.md", "text/markdown") == "a.md"
    blob.upload_from_string.assert_called_with(b"# x", content_type="text/markdown")
    await storage.upload_bytes(b"v", "clip.mp4")
    blob.upload_from_string.assert_called_with(b"v", content_type="video/mp4")


async def test_upload_bytes_failure(storage, blob):
    blob.upload_from_string.side_effect = RuntimeError("denied")
    with pytest.raises(UploadError, match="denied"):
        await storage.upload_bytes(b"x", "a")


async def test_download_bytes(storage, blob):
    blob.download_as_bytes.return_value = b"payload"
    assert await storage.download_bytes("a") == b"payload"


async def test_download_missing_raises_not_found(storage, blob):
    blob.download_as_bytes.side_effect = NotFound("gone")
    with pytest.raises(NotFoundError):
        await storage.download_bytes("a")


async def test_download_failure(storage, blob):
    blob.download_as_bytes.side_effect = RuntimeError("reset")
    with pytest.raises(DownloadError, match="reset"):
        await storage.download_bytes("a")


def gcs_blob(name: str, size: int | None) -> MagicMock:
    item = MagicMock()
    item.name, item.size = name, size
    return item


async def test_list_object_sizes_and_names(storage, bucket):
    bucket.list_blobs.side_effect = lambda prefix: iter([gcs_blob("p/a", 4), gcs_blob("p/b", None)])
    assert await storage.list_object_sizes("p/") == {"p/a": 4, "p/b": 0}
    assert await storage.list_objects("p/") == ["p/a", "p/b"]
    bucket.list_blobs.assert_called_with(prefix="p/")


async def test_list_failure(storage, bucket):
    bucket.list_blobs.side_effect = RuntimeError("throttled")
    with pytest.raises(ListError, match="throttled"):
        await storage.list_objects("p/")


async def test_delete_existing_returns_true(storage, blob):
    assert await storage.delete("a") is True
    blob.delete.assert_called_once_with()


async def test_delete_missing_returns_false(storage, blob):
    blob.delete.side_effect = NotFound("gone")
    assert await storage.delete("a") is False


async def test_delete_failure(storage, blob):
    blob.delete.side_effect = RuntimeError("denied")
    with pytest.raises(DeleteError, match="denied"):
        await storage.delete("a")


async def test_get_public_url_signs_v4_get(storage, blob):
    blob.generate_signed_url.return_value = "https://signed"
    assert await storage.get_public_url("a", expiration=60) == "https://signed"
    blob.generate_signed_url.assert_called_once_with(expiration=60, method="GET", version="v4")


async def test_get_public_url_failure(storage, blob):
    blob.generate_signed_url.side_effect = RuntimeError("no key")
    with pytest.raises(DownloadError, match="no key"):
        await storage.get_public_url("a")
