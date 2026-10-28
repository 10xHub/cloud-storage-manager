from enum import Enum

from pydantic import BaseModel, Field, model_validator


class StorageProvider(Enum):
    """Enumeration of supported cloud storage providers."""

    AWS = "aws"
    GCP = "gcp"
    AZURE = "azure"


class AwsConfig(BaseModel):
    bucket_name: str = Field(..., description="AWS S3 bucket name")
    access_key_id: str = Field(..., description="AWS access key ID")
    secret_access_key: str = Field(..., description="AWS secret access key")
    region: str = Field(default="us-east-1", description="AWS region")


class GcpConfig(BaseModel):
    bucket_name: str = Field(..., description="GCP bucket name")
    credentials: dict = Field(..., description="GCP service account credentials")
    project_id: str = Field(..., description="GCP project ID")


class AzureConfig(BaseModel):
    account_name: str = Field(..., description="Azure storage account name")
    container_name: str = Field(..., description="Azure Blob container name")
    account_key: str | None = Field(None, description="Storage account shared key")
    connection_string: str | None = Field(None, description="Storage account connection string")

    @model_validator(mode="after")
    def _exactly_one_credential(self) -> "AzureConfig":
        if (self.account_key is None) == (self.connection_string is None):
            raise ValueError("Set exactly one of account_key or connection_string")
        return self


class StorageConfig(BaseModel):
    """Holds one config per cloud.

    Construction accepts any combination, as 0.1.x did: a caller picks the provider explicitly
    with CloudStorageFactory.get_storage(provider, config). Only `provider` and
    `CloudStorageFactory.from_config`, which have to infer it, need exactly one.
    """

    aws: AwsConfig | None = Field(None, description="AWS configuration")
    gcp: GcpConfig | None = Field(None, description="GCP configuration")
    azure: AzureConfig | None = Field(None, description="Azure Blob configuration")

    def _configured(self) -> list[StorageProvider]:
        return [p for p in StorageProvider if getattr(self, p.value) is not None]

    @property
    def provider(self) -> StorageProvider:
        """The one provider this config sets.

        Raises:
            ValueError: If no provider, or more than one, is configured.
        """
        configured = self._configured()
        if len(configured) != 1:
            names = ", ".join(p.value for p in configured) or "none"
            raise ValueError(f"Configure exactly one storage provider (got: {names})")
        return configured[0]

    def has_valid_provider(self) -> bool:
        """True when at least one provider is configured, as in 0.1.x."""
        return bool(self._configured())

    def validate_provider(self) -> None:
        """Kept for 0.1.x callers, where it never raised; it still does not."""
