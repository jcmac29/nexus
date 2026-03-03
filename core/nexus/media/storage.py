"""S3/MinIO storage client."""

import io
from typing import BinaryIO, AsyncGenerator
from uuid import uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from nexus.config import get_settings

settings = get_settings()


class StorageClient:
    """Client for S3-compatible object storage (MinIO)."""

    def __init__(self):
        self.endpoint_url = settings.storage_endpoint or "http://minio:9000"
        self.access_key = settings.storage_access_key or "nexus"
        self.secret_key = settings.storage_secret_key or "nexus-secret"
        self.bucket = settings.storage_bucket or "nexus-media"

        self.client = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            config=Config(signature_version="s3v4"),
        )

        self._ensure_bucket()

    def _ensure_bucket(self):
        """Create bucket if it doesn't exist."""
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError:
            self.client.create_bucket(Bucket=self.bucket)

    def generate_key(self, agent_id: str, filename: str) -> str:
        """Generate a unique storage key."""
        unique_id = uuid4().hex[:8]
        safe_filename = "".join(c if c.isalnum() or c in ".-_" else "_" for c in filename)
        return f"{agent_id}/{unique_id}/{safe_filename}"

    def upload_file(
        self,
        key: str,
        data: BinaryIO,
        content_type: str,
        size: int | None = None,
    ) -> dict:
        """Upload a file to storage."""
        extra_args = {"ContentType": content_type}

        self.client.upload_fileobj(
            data,
            self.bucket,
            key,
            ExtraArgs=extra_args,
        )

        return {
            "key": key,
            "bucket": self.bucket,
            "size": size,
        }

    def upload_bytes(
        self,
        key: str,
        data: bytes,
        content_type: str,
    ) -> dict:
        """Upload bytes to storage."""
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )

        return {
            "key": key,
            "bucket": self.bucket,
            "size": len(data),
        }

    def download_file(self, key: str) -> bytes:
        """Download a file from storage."""
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        return response["Body"].read()

    def get_download_stream(self, key: str) -> BinaryIO:
        """Get a streaming response for a file."""
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        return response["Body"]

    def get_file_info(self, key: str) -> dict | None:
        """Get file metadata."""
        try:
            response = self.client.head_object(Bucket=self.bucket, Key=key)
            return {
                "size": response["ContentLength"],
                "content_type": response.get("ContentType"),
                "last_modified": response.get("LastModified"),
            }
        except ClientError:
            return None

    def delete_file(self, key: str) -> bool:
        """Delete a file from storage."""
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False

    def generate_presigned_url(
        self,
        key: str,
        expires_in: int = 3600,
        method: str = "get_object",
    ) -> str:
        """Generate a presigned URL for direct access."""
        return self.client.generate_presigned_url(
            method,
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    def file_exists(self, key: str) -> bool:
        """Check if a file exists."""
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False


# Global instance
_storage_client: StorageClient | None = None


def get_storage() -> StorageClient:
    """Get the storage client singleton."""
    global _storage_client
    if _storage_client is None:
        _storage_client = StorageClient()
    return _storage_client
