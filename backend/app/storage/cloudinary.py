"""Cloudinary storage for chat image uploads."""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path

import cloudinary
import cloudinary.uploader

from app.config import get_settings

logger = logging.getLogger(__name__)


def _configure_cloudinary() -> None:
    settings = get_settings()
    if not all(
        [
            settings.cloudinary_cloud_name,
            settings.cloudinary_api_key,
            settings.cloudinary_api_secret,
        ]
    ):
        raise ValueError(
            "Cloudinary is not configured. Set CLOUDINARY_CLOUD_NAME, "
            "CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET."
        )
    cloudinary.config(
        cloud_name=settings.cloudinary_cloud_name,
        api_key=settings.cloudinary_api_key,
        api_secret=settings.cloudinary_api_secret,
        secure=True,
    )


def _upload_sync(image_bytes: bytes, *, public_id: str, folder: str) -> str:
    _configure_cloudinary()
    result = cloudinary.uploader.upload(
        image_bytes,
        folder=folder,
        public_id=public_id,
        resource_type="image",
        overwrite=False,
    )
    return str(result["secure_url"])


async def upload_chat_image(
    image_bytes: bytes,
    *,
    filename: str,
    session_id: str,
) -> str:
    ext = Path(filename).suffix.lower().lstrip(".") or "jpg"
    public_id = f"{session_id}_{uuid.uuid4().hex[:12]}.{ext}"
    folder = "chat/medical"
    try:
        return await asyncio.to_thread(
            _upload_sync,
            image_bytes,
            public_id=public_id,
            folder=folder,
        )
    except Exception as exc:
        logger.exception("Cloudinary upload failed for session %s", session_id)
        raise RuntimeError("Failed to upload image") from exc
