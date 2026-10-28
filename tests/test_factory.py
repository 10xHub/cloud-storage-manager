import sys
from unittest.mock import patch

import pytest

from cloud_storage_manager import CloudStorageFactory, StorageProvider
from cloud_storage_manager.aws_s3_storage import AWSClientStorage
from cloud_storage_manager.azure_storage import AzureBlobStorage
from cloud_storage_manager.gcp_storage import GcpClientStorage

from .factories import aws_config, azure_key_config, gcp_config


@pytest.mark.parametrize(
    ("factory", "provider", "cls"),
    [
        (aws_config, StorageProvider.AWS, AWSClientStorage),
        (gcp_config, StorageProvider.GCP, GcpClientStorage),
        (azure_key_config, StorageProvider.AZURE, AzureBlobStorage),
    ],
)
def test_get_storage_and_from_config_build_each_provider(factory, provider, cls):
    with (
        patch("cloud_storage_manager.gcp_storage.storage.Client"),
        patch(
            "cloud_storage_manager.gcp_storage.service_account.Credentials.from_service_account_info"
        ),
    ):
        config = factory()
        assert isinstance(CloudStorageFactory.get_storage(provider, config), cls)
        assert isinstance(CloudStorageFactory.from_config(config), cls)


def test_unsupported_provider_raises():
    with pytest.raises(ValueError, match="Unsupported storage provider"):
        CloudStorageFactory.get_storage("ftp", aws_config())  # type: ignore[arg-type]


def test_missing_extra_names_the_install_command():
    blocked = {"azure.storage.blob": None, "cloud_storage_manager.azure_storage": None}
    with patch.dict(sys.modules, blocked):
        with pytest.raises(ImportError, match=r"cloud-storage-manager\[azure\]"):
            CloudStorageFactory.get_storage(StorageProvider.AZURE, azure_key_config())
