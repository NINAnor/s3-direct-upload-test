"""
Application configuration.
"""

import os
from functools import lru_cache
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Settings:
    """Application settings loaded from environment variables."""

    # S3 Configuration (internal endpoint for backend)
    S3_ENDPOINT: str = os.getenv("S3_ENDPOINT", "http://rustfs:9000")
    S3_PUBLIC_ENDPOINT: str = os.getenv("S3_PUBLIC_ENDPOINT", "http://localhost:9000")
    S3_ACCESS_KEY: str = os.getenv("S3_ACCESS_KEY", "minioadmin")
    S3_SECRET_KEY: str = os.getenv("S3_SECRET_KEY", "minioadmin")
    S3_BUCKET_NAME: str = os.getenv("S3_BUCKET_NAME", "uploads")
    S3_REGION: str = os.getenv("S3_REGION", "us-east-1")

    # Presigned URL Configuration
    PRESIGNED_URL_EXPIRATION: int = int(os.getenv("PRESIGNED_URL_EXPIRATION", "3600"))

    # Application Configuration
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    def __repr__(self) -> str:
        return (
            f"Settings(S3_ENDPOINT={self.S3_ENDPOINT}, "
            f"S3_BUCKET_NAME={self.S3_BUCKET_NAME}, "
            f"DEBUG={self.DEBUG})"
        )


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
