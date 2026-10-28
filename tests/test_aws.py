from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from cloud_storage_manager import (
    DeleteError,
    DownloadError,
    ListError,
    NotFoundError,
    UploadError,
)
from cloud_storage_manager.aws_s3_storage import AWSClientStorage

from .factories import async_context, async_iter, aws_config, gcp_config

BUCKET = "test-bucket"


def client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, "Op")


@pytest.fixture
def s3():
    return AsyncMock()


@pytest.fixture
def session_cls(s3):
    with patch("cloud_storage_manager.aws_s3_storage.aioboto3.Session") as cls:
        cls.return_value.client = MagicMock(return_value=async_context(s3))
        yield cls


@pytest.fixture
def storage(session_cls):
    return AWSClientStorage(aws_config())


def test_init_passes_credentials_and_region(session_cls, storage):
    session_cls.assert_called_once_with(
        aws_access_key_id="test-access-key",
        aws_secret_access_key="test-secret",
        region_name="ap-south-1",
    )
    assert storage.bucket == BUCKET


def test_init_requires_aws_config():
    with pytest.raises(ValueError, match="AWS configuration is required"):
        AWSClientStorage(gcp_config())


async def test_upload_sends_guessed_content_type(storage, s3, sample_file):
    assert await storage.upload(sample_file, "videos/clip.mp4") == "videos/clip.mp4"
    args, kwargs = s3.upload_fileobj.call_args
    assert args[1:] == (BUCKET, "videos/clip.mp4")
    assert kwargs == {"ExtraArgs": {"ContentType": "video/mp4"}}


async def test_upload_accepts_str_path_and_unknown_type(storage, s3, untyped_file):
    await storage.upload(str(untyped_file), "x/blob")
    assert s3.upload_fileobj.call_args.kwargs == {}


async def test_upload_failure_raises_upload_error(storage, s3, sample_file):
    s3.upload_fileobj.side_effect = RuntimeError("boom")
    with pytest.raises(UploadError, match="boom"):
        await storage.upload(sample_file, "x.mp4")


async def test_upload_bytes_with_explicit_content_type(storage, s3):
    assert await storage.upload_bytes(b"# hi", "notes/a", "text/markdown") == "notes/a"
    s3.put_object.assert_awaited_once_with(
        Bucket=BUCKET, Key="notes/a", Body=b"# hi", ContentType="text/markdown"
    )


async def test_upload_bytes_guesses_or_omits_content_type(storage, s3):
    await storage.upload_bytes(b"{}", "a.json")
    assert s3.put_object.call_args.kwargs["ContentType"] == "application/json"
    await storage.upload_bytes(b"?", "a.unknownext")
    assert "ContentType" not in s3.put_object.call_args.kwargs


async def test_upload_bytes_failure(storage, s3):
    s3.put_object.side_effect = RuntimeError("denied")
    with pytest.raises(UploadError, match="denied"):
        await storage.upload_bytes(b"x", "a")


async def test_download_bytes_reads_the_body(storage, s3):
    body = AsyncMock()
    body.read.return_value = b"payload"
    s3.get_object.return_value = {"Body": async_context(body)}
    assert await storage.download_bytes("a/b") == b"payload"
    s3.get_object.assert_awaited_once_with(Bucket=BUCKET, Key="a/b")


@pytest.mark.parametrize("code", ["NoSuchKey", "404"])
async def test_download_missing_raises_not_found(storage, s3, code):
    s3.get_object.side_effect = client_error(code)
    with pytest.raises(NotFoundError):
        await storage.download_bytes("gone")


@pytest.mark.parametrize("error", [client_error("AccessDenied"), RuntimeError("reset")])
async def test_download_other_failures_raise_download_error(storage, s3, error):
    s3.get_object.side_effect = error
    with pytest.raises(DownloadError):
        await storage.download_bytes("a")


def paginate_pages(s3, pages):
    paginator = MagicMock()
    paginator.paginate.return_value = async_iter(pages)
    s3.get_paginator = MagicMock(return_value=paginator)
    return paginator


async def test_list_object_sizes_walks_every_page(storage, s3):
    paginator = paginate_pages(
        s3,
        [
            {"Contents": [{"Key": "p/a", "Size": 3}, {"Key": "p/b"}]},
            {"Contents": [{"Key": "p/c", "Size": 7}]},
            {},
        ],
    )
    assert await storage.list_object_sizes("p/") == {"p/a": 3, "p/b": 0, "p/c": 7}
    s3.get_paginator.assert_called_once_with("list_objects_v2")
    paginator.paginate.assert_called_once_with(Bucket=BUCKET, Prefix="p/")


async def test_list_objects_returns_names(storage, s3):
    paginate_pages(s3, [{"Contents": [{"Key": "p/a", "Size": 1}, {"Key": "p/b", "Size": 2}]}])
    assert await storage.list_objects("p/") == ["p/a", "p/b"]


async def test_list_failure_raises_list_error(storage, s3):
    s3.get_paginator = MagicMock(side_effect=RuntimeError("throttled"))
    with pytest.raises(ListError, match="throttled"):
        await storage.list_objects("p/")


async def test_delete_existing_returns_true(storage, s3):
    assert await storage.delete("a") is True
    s3.head_object.assert_awaited_once_with(Bucket=BUCKET, Key="a")
    s3.delete_object.assert_awaited_once_with(Bucket=BUCKET, Key="a")


@pytest.mark.parametrize("code", ["404", "NoSuchKey", "NotFound"])
async def test_delete_missing_returns_false(storage, s3, code):
    s3.head_object.side_effect = client_error(code)
    assert await storage.delete("gone") is False
    s3.delete_object.assert_not_awaited()


@pytest.mark.parametrize("error", [client_error("AccessDenied"), RuntimeError("reset")])
async def test_delete_other_failures_raise_delete_error(storage, s3, error):
    s3.delete_object.side_effect = error
    with pytest.raises(DeleteError):
        await storage.delete("a")


async def test_get_public_url_presigns_a_get(storage, s3):
    s3.generate_presigned_url.return_value = "https://signed"
    assert await storage.get_public_url("a.mp4", expiration=120) == "https://signed"
    s3.generate_presigned_url.assert_awaited_once_with(
        "get_object", Params={"Bucket": BUCKET, "Key": "a.mp4"}, ExpiresIn=120
    )


async def test_get_public_url_failure(storage, s3):
    s3.generate_presigned_url.side_effect = RuntimeError("no creds")
    with pytest.raises(DownloadError, match="no creds"):
        await storage.get_public_url("a")
