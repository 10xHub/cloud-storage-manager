class CloudStorageError(Exception):
    """Base exception for cloud storage operations"""


class UploadError(CloudStorageError):
    """Error occurred during file upload"""


class DeleteError(CloudStorageError):
    """Error occurred during file deletion"""


class DownloadError(CloudStorageError):
    """Error occurred during file download"""


class NotFoundError(CloudStorageError):
    """Resource not found"""


class AuthorizationError(CloudStorageError):
    """Authorization/Authentication failed"""


class ListError(CloudStorageError):
    """Error occurred while listing objects"""
