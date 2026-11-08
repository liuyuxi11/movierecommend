"""Safe local storage for user avatar uploads."""

from __future__ import annotations

import mimetypes
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status


AVATAR_DIR = Path(__file__).resolve().parent.parent / "uploads" / "avatars"
MAX_AVATAR_SIZE = 5 * 1024 * 1024
AVATAR_DIR.mkdir(parents=True, exist_ok=True)
_ALLOWED_EXTENSIONS = {
    ".jpg", ".jpeg", ".jfif", ".pjpeg", ".png", ".apng", ".gif",
    ".webp", ".avif", ".bmp", ".tif", ".tiff", ".svg", ".ico",
    ".heic", ".heif", ".img",
}
_MIME_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
    "image/svg+xml": ".svg",
    "image/x-icon": ".ico",
}


async def save_avatar(upload: UploadFile) -> str:
    content_type = (upload.content_type or "").lower().strip()
    filename_extension = Path(upload.filename or "").suffix.lower()
    if not content_type.startswith("image/") and filename_extension not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="\u5934\u50cf\u5fc5\u987b\u662f\u56fe\u7247\u6587\u4ef6",
        )

    data = await upload.read(MAX_AVATAR_SIZE + 1)
    if len(data) > MAX_AVATAR_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="\u5934\u50cf\u6587\u4ef6\u4e0d\u80fd\u8d85\u8fc7 5MB",
        )
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="\u5934\u50cf\u6587\u4ef6\u4e0d\u80fd\u4e3a\u7a7a",
        )

    extension = _MIME_EXTENSIONS.get(content_type)
    if extension is None:
        extension = filename_extension
        if extension not in _ALLOWED_EXTENSIONS:
            extension = mimetypes.guess_extension(content_type) or ".img"

    filename = f"{uuid.uuid4().hex}{extension}"
    (AVATAR_DIR / filename).write_bytes(data)
    return f"/uploads/avatars/{filename}"
