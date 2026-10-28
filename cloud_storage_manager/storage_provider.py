from importlib import import_module

from .base_storage import BaseCloudStorage
from .storage_schema import StorageConfig, StorageProvider

__all__ = ["CloudStorageFactory", "StorageProvider"]

# 0.1.x imported these two classes here eagerly; they stay importable from this module, but load
# on first access so `import cloud_storage_manager` pulls in no cloud SDK.
_LEGACY_CLASSES = {
    "AWSClientStorage": ".aws_s3_storage",
    "GcpClientStorage": ".gcp_storage",
}


def __getattr__(name: str):
    if name in _LEGACY_CLASSES:
        return getattr(import_module(_LEGACY_CLASSES[name], __package__), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


class CloudStorageFactory:
    """Factory class for creating cloud storage client instances.

    Each provider module is imported only when it is asked for, so installing a
    single cloud's extra (``cloud-storage-manager[gcp]``) is enough to use it.

    Example:
        >>> config = StorageConfig(gcp=GcpConfig(...))
        >>> storage = CloudStorageFactory.from_config(config)
        >>> await storage.upload_bytes(b"...", "remote/path.txt", "text/plain")
    """

    _providers: dict[StorageProvider, tuple[str, str]] = {
        StorageProvider.AWS: (".aws_s3_storage", "AWSClientStorage"),
        StorageProvider.GCP: (".gcp_storage", "GcpClientStorage"),
        StorageProvider.AZURE: (".azure_storage", "AzureBlobStorage"),
    }

    @classmethod
    def get_storage(cls, provider: StorageProvider, config: StorageConfig) -> BaseCloudStorage:
        """Creates and returns a cloud storage instance for the specified provider.

        Args:
            provider: The cloud storage provider to use.
            config: Configuration parameters for initializing the storage client.

        Returns:
            A concrete implementation of BaseCloudStorage for the specified provider.

        Raises:
            ValueError: If the specified provider is not supported.
            ImportError: If the provider's extra is not installed.
        """
        target = cls._providers.get(provider)
        if not target:
            raise ValueError(f"Unsupported storage provider: {provider}")
        module_name, class_name = target
        try:
            module = import_module(module_name, __package__)
        except ImportError as e:
            raise ImportError(
                f"{provider.value} storage needs its extra: "
                f"pip install 'cloud-storage-manager[{provider.value}]'"
            ) from e
        return getattr(module, class_name)(config)

    @classmethod
    def from_config(cls, config: StorageConfig) -> BaseCloudStorage:
        """Creates the storage client for whichever provider the config sets."""
        return cls.get_storage(config.provider, config)
