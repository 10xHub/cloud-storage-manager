import pytest
from pydantic import ValidationError

from cloud_storage_manager import AzureConfig, StorageConfig, StorageProvider

from .factories import FAKE_AZURE_KEY, aws_config, azure_conn_config, azure_key_config, gcp_config


@pytest.mark.parametrize(
    ("factory", "provider"),
    [
        (aws_config, StorageProvider.AWS),
        (gcp_config, StorageProvider.GCP),
        (azure_key_config, StorageProvider.AZURE),
    ],
)
def test_provider_property_names_the_one_configured(factory, provider):
    config = factory()
    assert config.provider is provider
    assert config.has_valid_provider() is True
    config.validate_provider()


def test_no_provider_is_rejected():
    with pytest.raises(ValidationError, match="exactly one storage provider \\(got: none\\)"):
        StorageConfig()


def test_two_providers_are_rejected():
    with pytest.raises(ValidationError, match="got: aws, gcp"):
        StorageConfig(aws=aws_config().aws, gcp=gcp_config().gcp)


def test_validator_returns_the_model_not_a_bool():
    assert isinstance(aws_config(), StorageConfig)


def test_legacy_helpers_report_a_config_mutated_after_validation():
    config = aws_config()
    config.aws = None
    assert config.has_valid_provider() is False
    with pytest.raises(ValueError, match="exactly one storage provider"):
        config.validate_provider()


def test_azure_accepts_account_key():
    assert azure_key_config().azure.account_key == FAKE_AZURE_KEY


def test_azure_accepts_connection_string():
    assert azure_conn_config().azure.connection_string.startswith("DefaultEndpointsProtocol")


def test_azure_rejects_neither_credential():
    with pytest.raises(ValidationError, match="exactly one of account_key or connection_string"):
        AzureConfig(account_name="a", container_name="c")


def test_azure_rejects_both_credentials():
    with pytest.raises(ValidationError, match="exactly one of account_key or connection_string"):
        AzureConfig(account_name="a", container_name="c", account_key="k", connection_string="s")
