import subprocess
import sys
from importlib import metadata

import pytest
from packaging.requirements import Requirement

import cloud_storage_manager
from cloud_storage_manager import BaseCloudStorage, StorageConfig
from cloud_storage_manager.base_storage import guess_content_type


def test_public_names_are_importable_from_the_package():
    for name in cloud_storage_manager.__all__:
        assert hasattr(cloud_storage_manager, name)


def test_importing_the_package_loads_no_cloud_sdk():
    code = (
        "import sys, cloud_storage_manager; "
        "print([m for m in ('aioboto3', 'google.cloud.storage', 'azure.storage.blob') "
        "if m in sys.modules])"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"


def test_guess_content_type():
    assert guess_content_type("a/b/clip.mp4") == "video/mp4"
    assert guess_content_type("a/b/blob.unknownext") is None


def test_base_install_requires_what_0_1_did():
    base = {
        Requirement(r).name
        for r in metadata.requires("cloud-storage-manager")
        if Requirement(r).marker is None
    }
    assert base == {"aioboto3", "google-cloud-storage", "pydantic"}


def test_azure_stays_an_optional_extra():
    azure = [
        Requirement(r).name
        for r in metadata.requires("cloud-storage-manager")
        if Requirement(r).marker is not None and "azure" in str(Requirement(r).marker)
    ]
    assert "azure-storage-blob" in azure


class _V01Storage(BaseCloudStorage):
    """A subclass written against 0.1.x: only the three methods that version had."""

    async def upload(self, file_path, cloud_path):
        return cloud_path

    async def delete(self, cloud_path):
        return True

    async def get_public_url(self, cloud_path, expiration=3600):
        return cloud_path


async def test_a_0_1_subclass_still_instantiates_and_lacks_only_the_new_methods():
    storage = _V01Storage(StorageConfig())
    assert await storage.upload("a", "b") == "b"
    assert await storage.delete("b") is True
    assert await storage.get_public_url("b") == "b"
    new_calls = [
        storage.upload_bytes(b"", "b"),
        storage.download_bytes("b"),
        storage.list_objects(""),
        storage.list_object_sizes(""),
        storage.delete_if_exists("b"),
    ]
    for call in new_calls:
        with pytest.raises(NotImplementedError, match="_V01Storage does not implement"):
            await call
