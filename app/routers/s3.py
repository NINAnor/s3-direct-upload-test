"""
S3 router for handling presigned URL requests from Uppy.
"""

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel
from typing import List, Optional
import logging

from app.services.s3_service import get_s3_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/s3", tags=["s3"])


# Request/Response models
class PresignedUrlRequest(BaseModel):
    """Request model for generating presigned URL."""

    filename: str
    contentType: Optional[str] = None
    prefix: Optional[str] = None  # Optional prefix/folder path


class PresignedUrlResponse(BaseModel):
    """Response model for presigned URL."""

    method: str
    url: str
    headers: dict = {}


class MultipartCreateRequest(BaseModel):
    """Request model for creating multipart upload."""

    filename: str
    contentType: Optional[str] = None


class MultipartCreateResponse(BaseModel):
    """Response model for multipart upload creation."""

    uploadId: str
    key: str


class MultipartPart(BaseModel):
    """Model for a single part in multipart upload."""

    PartNumber: int
    ETag: str


class MultipartCompleteRequest(BaseModel):
    """Request model for completing multipart upload."""

    parts: List[MultipartPart]


class MultipartCompleteResponse(BaseModel):
    """Response model for completed multipart upload."""

    location: str


@router.post("/params", response_model=PresignedUrlResponse)
async def generate_presigned_url(request: PresignedUrlRequest):
    """
    Generate a presigned URL for direct upload to S3.
    Used by Uppy for single file uploads.
    """
    try:
        s3_service = get_s3_service()

        # Construct the full key with prefix if provided
        key = request.filename
        if request.prefix:
            # Ensure prefix ends with / and doesn't start with /
            prefix = request.prefix.strip("/")
            if prefix:
                key = f"{prefix}/{request.filename}"

        result = s3_service.generate_presigned_url_put(
            key=key, content_type=request.contentType
        )

        logger.info(f"Generated presigned URL for file: {key}")
        return result

    except Exception as e:
        logger.error(f"Error generating presigned URL: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/multipart", response_model=MultipartCreateResponse)
async def create_multipart_upload(
    key: str = Query(..., description="The object key (filename)"),
    type: Optional[str] = Query(None, description="Content type"),
    prefix: Optional[str] = Query(None, description="Optional prefix/folder path"),
):
    """
    Create a multipart upload.
    Used by Uppy for large file uploads.
    """
    try:
        s3_service = get_s3_service()

        # Construct the full key with prefix if provided
        full_key = key
        if prefix:
            # Ensure prefix ends with / and doesn't start with /
            prefix_clean = prefix.strip("/")
            if prefix_clean:
                full_key = f"{prefix_clean}/{key}"

        result = s3_service.create_multipart_upload(key=full_key, content_type=type)

        logger.info(f"Created multipart upload for: {full_key}")
        return result

    except Exception as e:
        logger.error(f"Error creating multipart upload: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/multipart/{upload_id}")
async def list_multipart_parts(
    upload_id: str = Path(..., description="The upload ID"),
    key: str = Query(..., description="The object key"),
):
    """
    List uploaded parts for a multipart upload.
    Used by Uppy to resume interrupted uploads.
    """
    try:
        s3_service = get_s3_service()
        parts = s3_service.list_parts(key=key, upload_id=upload_id)

        logger.info(f"Listed {len(parts)} parts for upload: {upload_id}")
        return parts

    except Exception as e:
        logger.error(f"Error listing parts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/multipart/{upload_id}/{part_number}")
async def sign_multipart_part(
    upload_id: str = Path(..., description="The upload ID"),
    part_number: int = Path(..., description="The part number", ge=1),
    key: str = Query(..., description="The object key"),
):
    """
    Generate a presigned URL for uploading a specific part.
    Used by Uppy for each part of a multipart upload.
    """
    try:
        s3_service = get_s3_service()
        url = s3_service.generate_presigned_part_url(
            key=key, upload_id=upload_id, part_number=part_number
        )

        logger.debug(f"Signed part {part_number} for upload: {upload_id}")
        return {"url": url}

    except Exception as e:
        logger.error(f"Error signing part: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/multipart/{upload_id}/complete", response_model=MultipartCompleteResponse
)
async def complete_multipart_upload(
    upload_id: str = Path(..., description="The upload ID"),
    key: str = Query(..., description="The object key"),
    request: MultipartCompleteRequest = None,
):
    """
    Complete a multipart upload.
    Used by Uppy after all parts have been uploaded.
    """
    try:
        s3_service = get_s3_service()

        # Convert Pydantic models to dicts for boto3
        parts = [part.dict() for part in request.parts]

        result = s3_service.complete_multipart_upload(
            key=key, upload_id=upload_id, parts=parts
        )

        logger.info(f"Completed multipart upload: {upload_id}")
        return result

    except Exception as e:
        logger.error(f"Error completing multipart upload: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/multipart/{upload_id}")
async def abort_multipart_upload(
    upload_id: str = Path(..., description="The upload ID"),
    key: str = Query(..., description="The object key"),
):
    """
    Abort a multipart upload.
    Used by Uppy when user cancels an upload.
    """
    try:
        s3_service = get_s3_service()
        s3_service.abort_multipart_upload(key=key, upload_id=upload_id)

        logger.info(f"Aborted multipart upload: {upload_id}")
        return {"message": "Upload aborted successfully"}

    except Exception as e:
        logger.error(f"Error aborting multipart upload: {e}")
        # Don't raise exception for abort, just log and return success
        return {"message": "Upload abort attempted"}
