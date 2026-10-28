"""
Cloud Storage Manager Package
"""

import logging

from .base_storage import BaseCloudStorage
from .exceptions import (
    AuthorizationError,
    CloudStorageError,
    DeleteError,
    DownloadError,
    ListError,
    NotFoundError,
    UploadError,
)
from .storage_provider import CloudStorageFactory
from .storage_schema import AwsConfig, AzureConfig, GcpConfig, StorageConfig, StorageProvider

logger = logging.getLogger(__name__)

__all__ = [
    "AuthorizationError",
    "AwsConfig",
    "AzureConfig",
    "BaseCloudStorage",
    "CloudStorageError",
    "CloudStorageFactory",
    "DeleteError",
    "DownloadError",
    "GcpConfig",
    "ListError",
    "NotFoundError",
    "StorageConfig",
    "StorageProvider",
    "UploadError",
    "logger",
]
