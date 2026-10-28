# Cloud Storage Manager

One async interface over AWS S3, Google Cloud Storage and Azure Blob Storage. Application code
calls the same methods everywhere; switching cloud is a configuration change.

## Features

- One interface for AWS S3, Google Cloud Storage and Azure Blob Storage
- Async operations
- Upload from a file or from bytes, download, list, delete, signed read URLs
- `upload_bytes` stores a content type, so a signed video URL plays in a browser
- Type-safe configuration using Pydantic
- A drop-in upgrade from 0.1.x (see below)

## Installation

The base install covers AWS S3 and Google Cloud Storage, as 0.1.x did. Azure is an extra:

```bash
pip install cloud-storage-manager           # AWS S3 + Google Cloud Storage
pip install "cloud-storage-manager[azure]"  # adds Azure Blob Storage
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

    deleted = await storage.delete_if_exists("notes/a.md")  # False if it was already gone
```

`CloudStorageFactory.from_config` picks the provider from the config.
`CloudStorageFactory.get_storage(StorageProvider.GCP, config)` still works.

## Configuration

`CloudStorageFactory.get_storage(provider, config)` uses the provider you name, so a config may
hold more than one. `config.provider` and `from_config` infer it, and raise `ValueError` unless
exactly one is set.

### AWS S3

```python
from cloud_storage_manager import AwsConfig, StorageConfig

config = StorageConfig(
    aws=AwsConfig(
        bucket_name="my-bucket",
        access_key_id="...",
        secret_access_key="...",
        region="us-east-1",  # stored but not used; boto resolves the region, as in 0.1.x
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
| `upload(file_path, cloud_path)` | `str` | GCP and Azure type the object from its file name; S3 does not (0.1.x behaviour) |
| `upload_bytes(data, cloud_path, content_type=None)` | `str` | Content type guessed from `cloud_path` when omitted |
| `download_bytes(cloud_path)` | `bytes` | `NotFoundError` if missing |
| `list_objects(prefix)` | `list[str]` | Every page |
| `list_object_sizes(prefix)` | `dict[str, int]` | Name to size in bytes |
| `delete(cloud_path)` | `bool` | 0.1.x behaviour: a missing object raises `DeleteError` on GCP and Azure, returns `True` on S3 |
| `delete_if_exists(cloud_path)` | `bool` | `False` if it did not exist, on every cloud |
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

Nothing to change: every 0.1.x call behaves as before.

- The base install pulls the same packages as 0.1.x; Azure is the `[azure]` extra.
- `StorageConfig` accepts every combination 0.1.x accepted.
- `upload`, `delete` and `get_public_url` behave as in 0.1.x on S3 and GCP; the new
  `delete_if_exists` is the one to use for the same answer on every cloud.
- Only those three methods are abstract, so a subclass written for 0.1.x still instantiates.
- `AWSClientStorage` and `GcpClientStorage` are still importable from
  `cloud_storage_manager.storage_provider`.
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
