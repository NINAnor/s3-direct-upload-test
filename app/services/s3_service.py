"""
S3 service for handling presigned URLs and multipart uploads.
"""

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
import logging
from typing import Dict, List, Optional

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class S3Service:
    """Service for S3 operations and presigned URL generation."""

    def __init__(self):
        """Initialize S3 client with configuration."""
        # Client for internal operations (bucket management, etc.)
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name=settings.S3_REGION,
            config=Config(signature_version="s3v4"),
        )

        # Separate client for generating presigned URLs with public endpoint
        # This ensures the Host header in signatures matches what browsers will use
        self.presign_client = boto3.client(
            "s3",
            endpoint_url=settings.S3_PUBLIC_ENDPOINT,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name=settings.S3_REGION,
            config=Config(signature_version="s3v4"),
        )

        self.bucket_name = settings.S3_BUCKET_NAME
        self.public_endpoint = settings.S3_PUBLIC_ENDPOINT

    def create_bucket_if_not_exists(self) -> bool:
        """
        Create S3 bucket if it doesn't exist.

        Returns:
            bool: True if bucket was created or already exists, False on error.
        """
        try:
            # Check if bucket exists
            self.client.head_bucket(Bucket=self.bucket_name)
            logger.info(f"Bucket '{self.bucket_name}' already exists")
            return True
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            if error_code == "404":
                # Bucket doesn't exist, create it
                try:
                    self.client.create_bucket(Bucket=self.bucket_name)
                    logger.info(f"Created bucket '{self.bucket_name}'")

                    # Set bucket CORS configuration
                    self._set_bucket_cors()
                    return True
                except ClientError as create_error:
                    logger.error(f"Error creating bucket: {create_error}")
                    return False
            else:
                logger.error(f"Error checking bucket: {e}")
                return False

    def _set_bucket_cors(self) -> None:
        """Set CORS configuration for the bucket to allow browser uploads."""
        cors_configuration = {
            "CORSRules": [
                {
                    "AllowedHeaders": ["*"],
                    "AllowedMethods": ["GET", "PUT", "POST", "DELETE", "HEAD"],
                    "AllowedOrigins": ["*"],  # In production, specify exact origins
                    "ExposeHeaders": ["ETag", "Location"],
                    "MaxAgeSeconds": 3000,
                }
            ]
        }
        try:
            self.client.put_bucket_cors(
                Bucket=self.bucket_name, CORSConfiguration=cors_configuration
            )
            logger.info(f"CORS configuration set for bucket '{self.bucket_name}'")
        except ClientError as e:
            logger.error(f"Error setting CORS configuration: {e}")

    def generate_presigned_url_put(
        self,
        key: str,
        content_type: Optional[str] = None,
        expiration: Optional[int] = None,
    ) -> Dict[str, str]:
        """
        Generate a presigned URL for PUT upload.

        Args:
            key: The object key (filename) in S3
            content_type: The content type of the file
            expiration: URL expiration time in seconds

        Returns:
            Dict containing the presigned URL and HTTP method
        """
        if expiration is None:
            expiration = settings.PRESIGNED_URL_EXPIRATION

        params = {
            "Bucket": self.bucket_name,
            "Key": key,
        }

        # Note: DO NOT include ContentType in params for browser uploads
        # Including it causes boto3 to sign the Content-Type header,
        # which can cause SignatureDoesNotMatch errors when the browser
        # sends CORS preflight headers or doesn't match the exact content-type

        try:
            # Use presign_client which has the public endpoint configured
            url = self.presign_client.generate_presigned_url(
                "put_object", Params=params, ExpiresIn=expiration
            )

            result = {"method": "PUT", "url": url, "headers": {}}

            # Don't include Content-Type in headers to avoid signature issues
            # The browser will set it automatically based on the file

            logger.debug(f"Generated presigned URL for key: {key}")
            return result

        except ClientError as e:
            logger.error(f"Error generating presigned URL: {e}")
            raise

    def create_multipart_upload(
        self, key: str, content_type: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Create a multipart upload.

        Args:
            key: The object key (filename) in S3
            content_type: The content type of the file

        Returns:
            Dict containing uploadId and key
        """
        params = {
            "Bucket": self.bucket_name,
            "Key": key,
        }

        if content_type:
            params["ContentType"] = content_type

        try:
            response = self.client.create_multipart_upload(**params)
            logger.info(
                f"Created multipart upload for key: {key}, uploadId: {response['UploadId']}"
            )
            return {"uploadId": response["UploadId"], "key": key}
        except ClientError as e:
            logger.error(f"Error creating multipart upload: {e}")
            raise

    def generate_presigned_part_url(
        self,
        key: str,
        upload_id: str,
        part_number: int,
        expiration: Optional[int] = None,
    ) -> str:
        """
        Generate a presigned URL for uploading a single part.

        Args:
            key: The object key
            upload_id: The multipart upload ID
            part_number: The part number (1-indexed)
            expiration: URL expiration time in seconds

        Returns:
            Presigned URL string
        """
        if expiration is None:
            expiration = settings.PRESIGNED_URL_EXPIRATION

        try:
            # Use presign_client which has the public endpoint configured
            url = self.presign_client.generate_presigned_url(
                "upload_part",
                Params={
                    "Bucket": self.bucket_name,
                    "Key": key,
                    "UploadId": upload_id,
                    "PartNumber": part_number,
                },
                ExpiresIn=expiration,
            )

            logger.debug(
                f"Generated presigned URL for part {part_number} of upload {upload_id}"
            )
            return url

        except ClientError as e:
            logger.error(f"Error generating presigned part URL: {e}")
            raise

    def list_parts(self, key: str, upload_id: str) -> List[Dict]:
        """
        List uploaded parts for a multipart upload.

        Args:
            key: The object key
            upload_id: The multipart upload ID

        Returns:
            List of part dictionaries
        """
        try:
            response = self.client.list_parts(
                Bucket=self.bucket_name, Key=key, UploadId=upload_id
            )

            parts = response.get("Parts", [])
            logger.debug(f"Listed {len(parts)} parts for upload {upload_id}")
            return parts

        except ClientError as e:
            logger.error(f"Error listing parts: {e}")
            raise

    def complete_multipart_upload(
        self, key: str, upload_id: str, parts: List[Dict[str, any]]
    ) -> Dict[str, str]:
        """
        Complete a multipart upload.

        Args:
            key: The object key
            upload_id: The multipart upload ID
            parts: List of parts with PartNumber and ETag

        Returns:
            Dict containing the location of the uploaded object
        """
        try:
            response = self.client.complete_multipart_upload(
                Bucket=self.bucket_name,
                Key=key,
                UploadId=upload_id,
                MultipartUpload={"Parts": parts},
            )

            location = f"{self.public_endpoint}/{self.bucket_name}/{key}"
            logger.info(f"Completed multipart upload for key: {key}")

            return {"location": location}

        except ClientError as e:
            logger.error(f"Error completing multipart upload: {e}")
            raise

    def abort_multipart_upload(self, key: str, upload_id: str) -> None:
        """
        Abort a multipart upload.

        Args:
            key: The object key
            upload_id: The multipart upload ID
        """
        try:
            self.client.abort_multipart_upload(
                Bucket=self.bucket_name, Key=key, UploadId=upload_id
            )
            logger.info(f"Aborted multipart upload: {upload_id} for key: {key}")
        except ClientError as e:
            logger.error(f"Error aborting multipart upload: {e}")
            # Don't raise, as abort is a cleanup operation


# Singleton instance
_s3_service: Optional[S3Service] = None


def get_s3_service() -> S3Service:
    """Get S3 service singleton instance."""
    global _s3_service
    if _s3_service is None:
        _s3_service = S3Service()
    return _s3_service
