import asyncio
import io
import uuid
from datetime import datetime, timezone

from bson import Binary
from fastapi import APIRouter, HTTPException, Query, Response, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from .. import db
from ..config import settings

router = APIRouter(prefix="/api")
FIELDS = {"full": "data", "llm": "llm", "thumb": "thumb"}


def _normalize(raw: bytes) -> tuple[bytes, bytes, bytes]:
    """Verify it is a real image, fix rotation, and re-encode (strips EXIF/GPS) into three sizes:
    full (1024px, for display), llm (384px q65, the small copy the model sees) and thumb (240px, for the UI)."""
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")

    def enc(side: int, quality: int) -> bytes:
        c = img.copy()
        c.thumbnail((side, side))
        out = io.BytesIO()
        c.save(out, "JPEG", quality=quality, optimize=True)
        return out.getvalue()

    return enc(1024, 82), enc(384, 65), enc(240, 70)


@router.post("/sessions")
async def upload(files: list[UploadFile]):
    if not settings.min_images <= len(files) <= settings.max_images:
        raise HTTPException(400, f"Upload between {settings.min_images} and {settings.max_images} photos.")
    session_id, now, docs = uuid.uuid4().hex, datetime.now(timezone.utc), []
    for f in files:
        raw = await f.read(settings.max_upload_bytes + 1)
        if len(raw) > settings.max_upload_bytes:
            raise HTTPException(413, "A photo is too large (max 8 MB).")
        try:
            full, llm, thumb = await asyncio.to_thread(_normalize, raw)
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
            raise HTTPException(400, f"'{f.filename}' is not a valid image.")
        docs.append(
            {
                "_id": uuid.uuid4().hex,
                "session_id": session_id,
                "data": Binary(full),
                "llm": Binary(llm),
                "thumb": Binary(thumb),
                "created_at": now,
            }
        )
    await db.images.insert_many(docs)
    return {"session_id": session_id, "image_ids": [d["_id"] for d in docs]}


@router.get("/images/{image_id}")
async def get_image(image_id: str, size: str = Query("full", pattern="^(full|llm|thumb)$")):
    field = FIELDS[size]
    doc = await db.images.find_one({"_id": image_id}, {field: 1, "data": 1})
    if not doc:
        raise HTTPException(404, "Image expired or not found.")
    return Response(
        bytes(doc.get(field) or doc["data"]), media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"}
    )
