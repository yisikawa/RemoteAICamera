"""Media serving endpoints (thumbnails, static files)"""
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from PIL import Image
import io

router = APIRouter(prefix="/api/media", tags=["media"])


@router.get("/thumbnail/{path:path}")
def get_thumbnail(path: str):
    """Get resized thumbnail (320x240)"""
    file_path = Path("data") / path

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    if not str(file_path).lower().endswith((".jpg", ".jpeg", ".png")):
        raise HTTPException(status_code=400, detail="Only image files supported")

    try:
        img = Image.open(file_path)
        img.thumbnail((320, 240), Image.Resampling.LANCZOS)

        thumb_path = Path("data") / ".thumbnails" / f"{file_path.stem}_thumb.jpg"
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(thumb_path, "JPEG", quality=80)

        return FileResponse(
            thumb_path,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=86400"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
