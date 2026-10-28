from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlsplit

import pytest
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError

from cloud_storage_manager import (
    DeleteError,
    DownloadError,
    ListError,
    NotFoundError,
    UploadError,
)
from cloud_storage_manager.azure_storage import AzureBlobStorage

from .factories import (
    FAKE_AZURE_KEY,
    async_iter,
    azure_conn_config,
    azure_connection_string,
    azure_key_config,
    gcp_config,
)

CONTAINER = "media"


@pytest.fixture
def service():
    client = MagicMock()
    client.__aenter__.return_value = client
    blob = client.get_blob_client.return_value
    blob.upload_blob = AsyncMock()
    blob.delete_blob = AsyncMock()
    blob.download_blob = AsyncMock()
    with patch("cloud_storage_manager.azure_storage.BlobServiceClient") as cls:
        cls.return_value = client
        cls.from_connection_string.return_value = client
        yield SimpleNamespace(cls=cls, client=client, blob=blob)


@pytest.fixture
def storage(service):
    return AzureBlobStorage(azure_key_config())


def test_init_requires_azure_config():
    with pytest.raises(ValueError, match="Azure configuration is required"):
        AzureBlobStorage(gcp_config())


async def test_account_key_config_targets_the_public_endpoint(service, storage):
    await storage.delete("a")
    service.cls.assert_called_once_with(
        account_url="https://testaccount.blob.core.windows.net", credential=FAKE_AZURE_KEY
    )
    service.client.get_blob_client.assert_called_with(CONTAINER, "a")


async def test_connection_string_config_uses_from_connection_string(service):
    await AzureBlobStorage(azure_conn_config()).delete("a")
    service.cls.from_connection_string.assert_called_once_with(azure_connection_string())
    service.cls.assert_not_called()


async def test_upload_streams_file_with_guessed_content_type(service, storage, sample_file):
    assert await storage.upload(sample_file, "v/clip.mp4") == "v/clip.mp4"
    args, kwargs = service.blob.upload_blob.call_args
    assert args[0].name == str(sample_file)
    assert kwargs["overwrite"] is True
    assert kwargs["content_settings"].content_type == "video/mp4"


async def test_upload_unknown_type_sends_no_content_settings(service, storage, untyped_file):
    await storage.upload(str(untyped_file), "x")
    assert "content_settings" not in service.blob.upload_blob.call_args.kwargs


async def test_upload_failure(service, storage, sample_file):
    service.blob.upload_blob.side_effect = HttpResponseError("denied")
    with pytest.raises(UploadError, match="denied"):
        await storage.upload(sample_file, "x")


async def test_upload_bytes_explicit_and_guessed_type(service, storage):
    assert await storage.upload_bytes(b"# x", "a.md", "text/markdown") == "a.md"
    first = service.blob.upload_blob.call_args
    assert first.args == (b"# x",)
    assert first.kwargs["content_settings"].content_type == "text/markdown"
    await storage.upload_bytes(b"v", "clip.webm")
    assert service.blob.upload_blob.call_args.kwargs["content_settings"].content_type == (
        "video/webm"
    )


async def test_upload_bytes_failure(service, storage):
    service.blob.upload_blob.side_effect = HttpResponseError("quota")
    with pytest.raises(UploadError, match="quota"):
        await storage.upload_bytes(b"x", "a")


async def test_download_bytes_reads_all(service, storage):
    downloader = MagicMock(readall=AsyncMock(return_value=b"payload"))
    service.blob.download_blob.return_value = downloader
    assert await storage.download_bytes("a") == b"payload"


async def test_download_missing_raises_not_found(service, storage):
    service.blob.download_blob.side_effect = ResourceNotFoundError("gone")
    with pytest.raises(NotFoundError):
        await storage.download_bytes("a")


async def test_download_failure(service, storage):
    service.blob.download_blob.side_effect = HttpResponseError("reset")
    with pytest.raises(DownloadError, match="reset"):
        await storage.download_bytes("a")


def blob_item(name: str, size: int | None) -> SimpleNamespace:
    return SimpleNamespace(name=name, size=size)


async def test_list_object_sizes_and_names(service, storage):
    container = service.client.get_container_client.return_value
    container.list_blobs.side_effect = lambda **_: async_iter(
        [blob_item("p/a", 5), blob_item("p/b", None)]
    )
    assert await storage.list_object_sizes("p/") == {"p/a": 5, "p/b": 0}
    assert await storage.list_objects("p/") == ["p/a", "p/b"]
    service.client.get_container_client.assert_called_with(CONTAINER)
    container.list_blobs.assert_called_with(name_starts_with="p/")


async def test_list_empty_prefix_lists_the_whole_container(service, storage):
    container = service.client.get_container_client.return_value
    container.list_blobs.side_effect = lambda **_: async_iter([])
    assert await storage.list_objects("") == []
    container.list_blobs.assert_called_with(name_starts_with=None)


async def test_list_failure(service, storage):
    service.client.get_container_client.return_value.list_blobs.side_effect = HttpResponseError(
        "throttled"
    )
    with pytest.raises(ListError, match="throttled"):
        await storage.list_objects("p/")


async def test_delete_existing_returns_true(service, storage):
    assert await storage.delete("a") is True
    service.blob.delete_blob.assert_awaited_once_with()


async def test_delete_missing_returns_false(service, storage):
    service.blob.delete_blob.side_effect = ResourceNotFoundError("gone")
    assert await storage.delete("a") is False


async def test_delete_failure(service, storage):
    service.blob.delete_blob.side_effect = HttpResponseError("locked")
    with pytest.raises(DeleteError, match="locked"):
        await storage.delete("a")


def sas_query(url: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


@pytest.mark.parametrize("config_factory", [azure_key_config, azure_conn_config])
async def test_sas_url_is_read_only_and_carries_the_expiry(config_factory):
    before = datetime.now(timezone.utc).replace(microsecond=0)
    url = await AzureBlobStorage(config_factory()).get_public_url("v/clip 1.mp4", expiration=900)
    query = sas_query(url)
    expiry = datetime.strptime(query["se"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)

    assert url.startswith("https://testaccount.blob.core.windows.net/media/v/clip%201.mp4?")
    assert query["sp"] == "r"
    assert query["sr"] == "b"
    assert "sig" in query
    assert before + timedelta(seconds=899) <= expiry <= before + timedelta(seconds=902)
    # A response-header override would replace the stored type and stop browser playback.
    assert "rsct" not in query


async def test_sas_url_without_an_account_key_is_refused():
    storage = AzureBlobStorage(azure_conn_config(key=None))
    with pytest.raises(DownloadError, match="needs an account key"):
        await storage.get_public_url("a")


async def test_sas_url_signing_failure(storage):
    with patch(
        "cloud_storage_manager.azure_storage.generate_blob_sas", side_effect=ValueError("bad key")
    ):
        with pytest.raises(DownloadError, match="bad key"):
            await storage.get_public_url("a")
