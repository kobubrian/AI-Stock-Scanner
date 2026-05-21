from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

from app.config import get_settings
from app.services.export import build_ai_export_pack, write_export_files

router = APIRouter(prefix="/export", tags=["export"])


@router.post("/ai-pack")
async def create_ai_pack(limit: int = Query(50, ge=5)):
    """Run scan and export JSON + Markdown for manual ChatGPT analysis."""
    cap = get_settings().scan_max_symbols
    limit = min(limit, cap)
    pack = await build_ai_export_pack(limit=limit)
    paths = write_export_files(pack)
    return {
        "status": "ok",
        "files": paths,
        "summary": pack["summary"],
        "top_longs": [t["ticker"] for t in pack.get("top_longs", [])],
        "top_shorts": [t["ticker"] for t in pack.get("top_shorts", [])],
        "download_json": "/api/export/ai-pack/latest/json",
    }


@router.get("/ai-pack")
async def get_ai_pack_preview(limit: int = Query(50, ge=5)):
    limit = min(limit, get_settings().scan_max_symbols)
    """Build pack in memory without writing files (faster preview)."""
    pack = await build_ai_export_pack(limit=limit)
    return pack


@router.get("/ai-pack/latest/json")
async def download_latest_json():
    from pathlib import Path

    export_dir = Path(__file__).resolve().parents[3] / "data" / "exports"
    files = sorted(export_dir.glob("ai_pack_*.json"), reverse=True)
    if not files:
        return {"error": "No export yet — POST /api/export/ai-pack first"}
    return FileResponse(files[0], media_type="application/json", filename=files[0].name)
