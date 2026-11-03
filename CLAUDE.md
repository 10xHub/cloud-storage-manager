# CLAUDE.md — cloud-storage-manager

## Project Overview
A Python library that puts one async interface over AWS S3, Google Cloud Storage and Azure Blob
Storage. Published on PyPI as `10x-cloud-storage-manager`, imported as `cloud_storage_manager`.

## Tech Stack
- Python 3.10+, setuptools (`pyproject.toml`)
- `aioboto3` (S3), `google-cloud-storage` (GCS), `azure-storage-blob` + `aiohttp` (Azure, extra)
- Pydantic v2 for config
- pytest, pytest-asyncio, pytest-cov (100% gate), ruff
- GitHub Actions; PyPI Trusted Publishing

## Architecture
A library, not a service. `BaseCloudStorage` (ABC) defines the interface; each provider
implements it. `CloudStorageFactory` imports a provider module lazily, so `import
cloud_storage_manager` loads no cloud SDK and a missing extra fails only when it is used.

## Project Flow
Caller → `StorageConfig` → `CloudStorageFactory.from_config` (needs exactly one provider set) or
`get_storage(provider, config)` (picks one from several) →
lazy import of provider module → `AWSClientStorage` / `GcpClientStorage` / `AzureBlobStorage` →
cloud SDK. SDK errors are mapped to `exceptions.py` types (`UploadError`, `NotFoundError`, …).

## Directory Structure
- `cloud_storage_manager/base_storage.py`: interface + `guess_content_type`
- `cloud_storage_manager/{aws_s3,gcp,azure}_storage.py`: provider implementations
- `cloud_storage_manager/storage_provider.py`: factory, legacy 0.1.x re-exports
- `cloud_storage_manager/storage_schema.py`: Pydantic configs, `StorageProvider` enum
- `cloud_storage_manager/_distribution.py`: the PyPI name (keep in sync with pyproject)
- `tests/`: SDKs fully mocked; `factories.py` holds config fixtures
- `.github/workflows/test.yml`: lint + tests (PRs, pushes to dev, called by release)
- `.github/workflows/release.yml`: publish to PyPI + GitHub release on push to prod
- `.github/actions/version-status/`: reads name/version, checks PyPI (shared by both workflows)

## Key Commands
```bash
uv pip install -p .venv -e ".[dev]"
.venv/bin/pytest --cov --cov-report=term-missing --cov-fail-under=100
.venv/bin/ruff check . && .venv/bin/ruff format --check .
uvx --from build pyproject-build && uvx twine check dist/*
uvx --from actionlint-py actionlint
```

## Branches and Releases
- `dev` is the default branch; feature PRs target it.
- Merging into `prod` releases. Bump `[project].version` in the PR to prod; CI blocks the PR if
  PyPI already has that version.
- The PyPI side trusts `10xHub/cloud-storage-manager`, workflow `release.yml`, environment
  `pypi`. Renaming any of these breaks publishing until PyPI's trusted publisher is updated.

## Environment Setup
None for tests. At runtime, credentials come from `StorageConfig` or each SDK's default chain.

## Conventions
- 0.1.x callers must keep working: never make a new method abstract, and keep legacy names.
- 100% line and branch coverage is enforced in CI.
- ruff, line length 100, rules E F W I B UP.

## Current Focus
Moving to the `10x-cloud-storage-manager` PyPI name and the dev → prod auto-release flow.
