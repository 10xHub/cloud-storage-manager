import base64
from collections.abc import AsyncIterator, Iterable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from cloud_storage_manager import AwsConfig, AzureConfig, GcpConfig, StorageConfig

# generate_blob_sas HMACs with the base64-decoded key, so a fake one must still decode.
FAKE_AZURE_KEY = base64.b64encode(b"k" * 32).decode()


def aws_config(**overrides: Any) -> StorageConfig:
    values = {
        "bucket_name": "test-bucket",
        "access_key_id": "test-access-key",
        "secret_access_key": "test-secret",
        "region": "ap-south-1",
    }
    return StorageConfig(aws=AwsConfig(**{**values, **overrides}))


def gcp_config(**overrides: Any) -> StorageConfig:
    values = {"bucket_name": "test-bucket", "credentials": {"type": "x"}, "project_id": "proj"}
    return StorageConfig(gcp=GcpConfig(**{**values, **overrides}))


def azure_key_config(**overrides: Any) -> StorageConfig:
    values = {
        "account_name": "testaccount",
        "container_name": "media",
        "account_key": FAKE_AZURE_KEY,
    }
    return StorageConfig(azure=AzureConfig(**{**values, **overrides}))


def azure_connection_string(key: str | None = FAKE_AZURE_KEY) -> str:
    parts = ["DefaultEndpointsProtocol=https", "AccountName=testaccount"]
    parts.append(f"AccountKey={key}" if key else "SharedAccessSignature=sv=2024&sig=abc")
    return ";".join([*parts, "EndpointSuffix=core.windows.net"])


def azure_conn_config(key: str | None = FAKE_AZURE_KEY) -> StorageConfig:
    return StorageConfig(
        azure=AzureConfig(
            account_name="testaccount",
            container_name="media",
            connection_string=azure_connection_string(key),
        )
    )


async def async_iter(items: Iterable[Any]) -> AsyncIterator[Any]:
    for item in items:
        yield item


def async_context(value: Any) -> MagicMock:
    """A MagicMock usable as `async with ... as value`."""
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=value)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx
