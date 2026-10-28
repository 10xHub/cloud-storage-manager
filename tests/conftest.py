import pytest


@pytest.fixture
def sample_file(tmp_path):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"video-bytes")
    return path


@pytest.fixture
def untyped_file(tmp_path):
    path = tmp_path / "blob.unknownext"
    path.write_bytes(b"raw")
    return path
