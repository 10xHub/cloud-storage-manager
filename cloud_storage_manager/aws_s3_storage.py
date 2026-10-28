from pathlib import Path

import aioboto3
from botocore.exceptions import ClientError

from . import logger
from .base_storage import BaseCloudStorage, guess_content_type
from .exceptions import DeleteError, DownloadError, ListError, NotFoundError, UploadError
from .storage_schema import StorageConfig

_MISSING_CODES = {"404", "NoSuchKey", "NotFound"}


def _is_missing(error: ClientError) -> bool:
    return error.response.get("Error", {}).get("Code") in _MISSING_CODES


class AWSClientStorage(BaseCloudStorage):
    """
    AWSClientStorage is a class for interacting with AWS S3 storage.
    It implements every BaseCloudStorage operation against one S3 bucket.
    Attributes:
        session (aioboto3.Session): The boto3 session for AWS S3 interactions.
        bucket (str): The name of the S3 bucket.
    """

    def __init__(self, config: StorageConfig):
        """Initialize AWS S3 storage client.

        Args:
            config (StorageConfig): Configuration containing AWS credentials and settings
                Must include aws.access_key_id, aws.secret_access_key, and aws.bucket_name

        Raises:
            ValueError: If AWS configuration is missing
        """
        if not config.aws:
            raise ValueError("AWS configuration is required")
        super().__init__(config)
        # `region` is deliberately not passed: 0.1.x let boto resolve the region from the
        # environment, and forcing the field's us-east-1 default would re-sign callers' URLs.
        self.session = aioboto3.Session(
            aws_access_key_id=config.aws.access_key_id,
            aws_secret_access_key=config.aws.secret_access_key,
        )
        self.bucket = config.aws.bucket_name
        logger.info(f"AWSClientStorage initialized with bucket: {self.bucket}")

    async def upload(self, file_path: Path | str, cloud_path: str) -> str:
        """Upload a local file to the S3 bucket; returns the S3 object path."""
        logger.info(f"Starting upload of {file_path} to s3://{self.bucket}/{cloud_path}")
        return await self.upload_file(file_path, cloud_path)

    async def upload_bytes(
        self, data: bytes, cloud_path: str, content_type: str | None = None
    ) -> str:
        """Upload in-memory bytes to the S3 bucket; returns the S3 object path."""
        logger.info(f"Uploading {len(data)} bytes to s3://{self.bucket}/{cloud_path}")
        content_type = content_type or guess_content_type(cloud_path)
        extra = {"ContentType": content_type} if content_type else {}
        async with self.session.client("s3") as s3:
            try:
                await s3.put_object(Bucket=self.bucket, Key=cloud_path, Body=data, **extra)
                return cloud_path
            except Exception as e:
                logger.error(f"Upload failed: {e}")
                raise UploadError(f"Failed to upload bytes to S3: {e}") from e

    async def download_bytes(self, cloud_path: str) -> bytes:
        """Download the S3 object's content."""
        logger.info(f"Downloading s3://{self.bucket}/{cloud_path}")
        async with self.session.client("s3") as s3:
            try:
                response = await s3.get_object(Bucket=self.bucket, Key=cloud_path)
                async with response["Body"] as body:
                    return await body.read()
            except ClientError as e:
                if _is_missing(e):
                    raise NotFoundError(f"S3 object not found: {cloud_path}") from e
                logger.error(f"Download failed: {e}")
                raise DownloadError(f"Failed to download file from S3: {e}") from e
            except Exception as e:
                logger.error(f"Download failed: {e}")
                raise DownloadError(f"Failed to download file from S3: {e}") from e

    async def list_objects(self, prefix: str) -> list[str]:
        """List S3 object keys under `prefix`."""
        return list(await self.list_object_sizes(prefix))

    async def list_object_sizes(self, prefix: str) -> dict[str, int]:
        """S3 object key -> size in bytes under `prefix`."""
        logger.info(f"Listing s3://{self.bucket}/{prefix}")
        async with self.session.client("s3") as s3:
            try:
                sizes: dict[str, int] = {}
                paginator = s3.get_paginator("list_objects_v2")
                async for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                    for item in page.get("Contents", []):
                        sizes[item["Key"]] = item.get("Size", 0)
                return sizes
            except Exception as e:
                logger.error(f"Listing failed: {e}")
                raise ListError(f"Failed to list objects in S3: {e}") from e

    async def delete(self, cloud_path: str) -> bool:
        """Delete a file from the S3 bucket; True even for a missing key, as S3 answers."""
        logger.info(f"Deleting s3://{self.bucket}/{cloud_path}")
        return await self.delete_file(cloud_path)

    async def delete_if_exists(self, cloud_path: str) -> bool:
        """Delete an S3 object; False when it did not exist."""
        logger.info(f"Deleting s3://{self.bucket}/{cloud_path} if it exists")
        async with self.session.client("s3") as s3:
            try:
                # S3 deletes a missing key without complaint, so existence is checked first.
                await s3.head_object(Bucket=self.bucket, Key=cloud_path)
            except ClientError as e:
                if _is_missing(e):
                    return False
                logger.error(f"Deletion failed: {e}")
                raise DeleteError(f"Failed to delete file from S3: {e}") from e
            except Exception as e:
                logger.error(f"Deletion failed: {e}")
                raise DeleteError(f"Failed to delete file from S3: {e}") from e
        return await self.delete_file(cloud_path)

    async def get_public_url(self, cloud_path: str, expiration: int = 3600) -> str:
        """Generate a pre-signed GET URL for a private S3 object."""
        logger.info(f"Generating pre-signed URL for s3://{self.bucket}/{cloud_path}")
        async with self.session.client("s3") as s3:
            try:
                url = await s3.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self.bucket, "Key": cloud_path},
                    ExpiresIn=expiration,
                )
                logger.debug(f"Generated pre-signed URL (expires in {expiration}s)")
                return url
            except Exception as e:
                logger.error(f"Failed to generate pre-signed URL: {e}")
                raise DownloadError(f"Failed to generate pre-signed URL: {e}") from e

    # Helper methods
    async def upload_file(self, file_path: Path | str, cloud_path: str) -> str:
        """Internal method to handle file upload to S3.

        No ContentType is sent, as in 0.1.x, so objects keep the type S3 assigned them before.
        """
        async with self.session.client("s3") as s3:
            try:
                with Path(file_path).open("rb") as file_obj:
                    await s3.upload_fileobj(file_obj, self.bucket, cloud_path)
                    logger.debug(f"Successfully uploaded to s3://{self.bucket}/{cloud_path}")
                return cloud_path
            except Exception as e:
                logger.error(f"Upload failed: {e}")
                raise UploadError(f"Failed to upload file to S3: {e}") from e

    async def delete_file(self, cloud_path: str) -> bool:
        """Internal method to handle file deletion from S3."""
        async with self.session.client("s3") as s3:
            try:
                await s3.delete_object(Bucket=self.bucket, Key=cloud_path)
                logger.debug(f"Successfully deleted s3://{self.bucket}/{cloud_path}")
                return True
            except Exception as e:
                logger.error(f"Deletion failed: {e}")
                raise DeleteError(f"Failed to delete file from S3: {e}") from e
