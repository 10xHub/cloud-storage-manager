import sys
from unittest.mock import patch

import pytest

from cloud_storage_manager import CloudStorageFactory, StorageConfig, StorageProvider
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


def test_get_storage_picks_by_enum_when_a_config_holds_two_providers():
    config = StorageConfig(aws=aws_config().aws, gcp=gcp_config().gcp)
    storage = CloudStorageFactory.get_storage(StorageProvider.AWS, config)
    assert isinstance(storage, AWSClientStorage)


def test_from_config_refuses_to_guess_between_two_providers():
    config = StorageConfig(aws=aws_config().aws, gcp=gcp_config().gcp)
    with pytest.raises(ValueError, match="got: aws, gcp"):
        CloudStorageFactory.from_config(config)


def test_0_1_provider_classes_are_still_importable_from_storage_provider():
    import cloud_storage_manager.storage_provider as module

    assert module.AWSClientStorage is AWSClientStorage
    assert module.GcpClientStorage is GcpClientStorage


def test_storage_provider_still_raises_attribute_error_for_unknown_names():
    import cloud_storage_manager.storage_provider as module

    with pytest.raises(AttributeError, match="no attribute 'Missing'"):
        _ = module.Missing
