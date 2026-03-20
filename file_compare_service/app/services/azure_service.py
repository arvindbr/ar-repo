"""
app/services/azure_service.py
Download files from Azure Blob Storage.
Supports connection string, account key, and SAS token auth.
"""
from __future__ import annotations

import logging

from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import BlobServiceClient
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.config import get_settings
from app.models.schemas import FileReference

logger = logging.getLogger(__name__)
settings = get_settings()


def _get_blob_client(container: str, blob_path: str):
    """Build a BlobClient using the best available credential."""
    if settings.azure_storage_connection_string:
        svc = BlobServiceClient.from_connection_string(
            settings.azure_storage_connection_string
        )
    elif settings.azure_storage_account_name and settings.azure_storage_account_key:
        url = f"https://{settings.azure_storage_account_name}.blob.core.windows.net"
        svc = BlobServiceClient(account_url=url, credential=settings.azure_storage_account_key)
    elif settings.azure_storage_account_name and settings.azure_sas_token:
        url = f"https://{settings.azure_storage_account_name}.blob.core.windows.net"
        svc = BlobServiceClient(account_url=url, credential=settings.azure_sas_token)
    else:
        raise EnvironmentError(
            "No Azure credentials configured. Set AZURE_STORAGE_CONNECTION_STRING "
            "or AZURE_STORAGE_ACCOUNT_NAME + AZURE_STORAGE_ACCOUNT_KEY in .env"
        )
    return svc.get_blob_client(container=container, blob=blob_path)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
async def download_blob(ref: FileReference) -> bytes:
    """
    Download a blob and return its raw bytes.
    Retries up to 3 times with exponential back-off.
    Raises FileNotFoundError if the blob does not exist.
    """
    logger.info("Downloading blob container=%s path=%s", ref.container, ref.blob_path)
    try:
        client = _get_blob_client(ref.container, ref.blob_path)
        props  = client.get_blob_properties()
        size_mb = props.size / (1024 * 1024)

        max_mb = settings.max_file_size_mb
        if size_mb > max_mb:
            raise ValueError(
                f"Blob {ref.blob_path} is {size_mb:.1f} MB which exceeds the "
                f"{max_mb} MB limit. Increase MAX_FILE_SIZE_MB in .env if needed."
            )

        data = client.download_blob().readall()
        logger.info("Downloaded %s  size=%.2f MB", ref.blob_path, size_mb)
        return data

    except ResourceNotFoundError:
        raise FileNotFoundError(
            f"Blob not found: container={ref.container!r} path={ref.blob_path!r}"
        )
