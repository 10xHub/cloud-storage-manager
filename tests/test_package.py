import subprocess
import sys

import cloud_storage_manager
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
