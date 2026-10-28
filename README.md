# Cloud Storage Manager

One async interface over AWS S3, Google Cloud Storage and Azure Blob Storage. Application code
calls the same methods everywhere; switching cloud is a configuration change.

## Features

- One interface for AWS S3, Google Cloud Storage and Azure Blob Storage
- Async operations
- Upload from a file or from bytes, download, list, delete, signed read URLs
- Content types are stored on upload, so a signed video URL plays in a browser
- Type-safe configuration using Pydantic
- Install only the cloud you use

## Installation

Pick the extra for your cloud:

```bash
pip install "cloud-storage-manager[aws]"    # AWS S3
pip install "cloud-storage-manager[gcp]"    # Google Cloud Storage
pip install "cloud-storage-manager[azure]"  # Azure Blob Storage
pip install "cloud-storage-manager[all]"    # all three
```

Requires Python 3.10+.

## Quick start

```python
import asyncio
from cloud_storage_manager import CloudStorageFactory, StorageConfig


async def main(config: StorageConfig):
    storage = CloudStorageFactory.from_config(config)

    await storage.upload("local/clip.mp4", "recordings/clip.mp4")
    await storage.upload_bytes(b"# Notes", "notes/a.md", content_type="text/markdown")

    data = await storage.download_bytes("notes/a.md")
    names = await storage.list_objects("recordings/")
    sizes = await storage.list_object_sizes("recordings/")  # {name: bytes}

    url = await storage.get_public_url("recordings/clip.mp4", expiration=3600)

    deleted = await storage.delete("notes/a.md")  # False if it was already gone
```

`CloudStorageFactory.from_config` picks the provider from the config.
`CloudStorageFactory.get_storage(StorageProvider.GCP, config)` still works.

## Configuration

A `StorageConfig` sets exactly one provider; zero or two is a validation error.
`config.provider` returns the `StorageProvider` it sets.

### AWS S3

```python
from cloud_storage_manager import AwsConfig, StorageConfig

config = StorageConfig(
    aws=AwsConfig(
        bucket_name="my-bucket",
        access_key_id="...",
        secret_access_key="...",
        region="us-east-1",  # optional, defaults to us-east-1
    )
)
```

### Google Cloud Storage

```python
from cloud_storage_manager import GcpConfig, StorageConfig

config = StorageConfig(
    gcp=GcpConfig(
        bucket_name="my-bucket",
        project_id="my-project",
        credentials={...},  # service account JSON as a dict
    )
)
```

### Azure Blob Storage

Give exactly one of `account_key` or `connection_string`.

```python
from cloud_storage_manager import AzureConfig, StorageConfig

config = StorageConfig(
    azure=AzureConfig(
        account_name="mystorageaccount",
        container_name="my-container",
        account_key="...",
        # or: connection_string="DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...;"
    )
)
```

`get_public_url` on Azure returns a read-only blob SAS URL, signed with the account key. A
connection string that carries a SAS instead of an `AccountKey` can read and write but cannot
sign URLs.

## Interface

Every provider implements `BaseCloudStorage`:

| Method | Returns | Notes |
| --- | --- | --- |
| `upload(file_path, cloud_path)` | `str` | Content type guessed from the file name |
| `upload_bytes(data, cloud_path, content_type=None)` | `str` | Content type guessed from `cloud_path` when omitted |
| `download_bytes(cloud_path)` | `bytes` | `NotFoundError` if missing |
| `list_objects(prefix)` | `list[str]` | Every page |
| `list_object_sizes(prefix)` | `dict[str, int]` | Name to size in bytes |
| `delete(cloud_path)` | `bool` | `False` if it did not exist |
| `get_public_url(cloud_path, expiration=3600)` | `str` | Signed, read-only, expires after `expiration` seconds |

## Error handling

Every error is a `CloudStorageError`: `UploadError`, `DownloadError`, `NotFoundError`,
`ListError`, `DeleteError`. The SDK's own exception is kept as `__cause__`.

```python
from cloud_storage_manager import NotFoundError

try:
    data = await storage.download_bytes("missing.txt")
except NotFoundError:
    data = None
```

## Upgrading from 0.1.x

- Install with an extra (`[aws]`, `[gcp]`, `[azure]` or `[all]`); the base package no longer
  pulls in any cloud SDK.
- `StorageConfig` with no provider, or more than one, now fails validation.
- `delete` returns `False` for a missing object instead of raising.
- Python 3.10+ (0.1.x already used 3.10 syntax and did not import on 3.8 or 3.9).

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest --cov
ruff check . && ruff format --check .
```

Tests mock every cloud SDK and never call a real cloud.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
