"""
OCR Document Extraction — FastAPI Application

Endpoints:
    POST /api/upload       — Upload image, run Gemini Vision extraction, return results
    GET  /api/preview/{id} — Get extracted key-value pairs for review
    POST /api/retry/{id}   — Re-extract using Gemini Vision (fresh attempt)
    GET  /api/download/{id}— Download the generated Excel file
    GET  /                 — Serve the web frontend
"""

import json
import logging
import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

import config
import gemini_service
import excel_builder
from gemini_service import DocumentData

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ── FastAPI app ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="OCR Document Extractor",
    description="Extract structured data from financial documents using Gemini Vision",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (CSS, JS, images)
app.mount("/static", StaticFiles(directory=str(config.STATIC_DIR)), name="static")

# ── In-memory job store ──────────────────────────────────────────────────────
# In production you'd use Redis or a database. For this prototype, a dict is fine.
_jobs: dict[str, dict] = {}


# ── Helper ───────────────────────────────────────────────────────────────────

def _validate_extension(filename: str) -> None:
    ext = Path(filename).suffix.lower()
    if ext not in config.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(config.ALLOWED_EXTENSIONS)}",
        )


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the main frontend page."""
    index_path = config.STATIC_DIR / "index.html"
    return HTMLResponse(content=index_path.read_text(encoding="utf-8"))


@app.post("/api/upload")
async def upload_and_process(file: UploadFile = File(...)):
    """Upload an image, send it to Gemini Vision for extraction, build Excel.

    Returns the job ID and extracted data for user review.
    """
    _validate_extension(file.filename)

    # Generate a unique job ID
    job_id = uuid.uuid4().hex[:12]
    ext = Path(file.filename).suffix.lower()
    image_filename = f"{job_id}{ext}"
    image_path = config.UPLOAD_DIR / image_filename

    # Save uploaded file
    with open(image_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    logger.info("Saved upload → %s", image_path)

    # Resize very large images to keep base64 payload reasonable for the API
    try:
        from PIL import Image, ImageOps
        with Image.open(image_path) as img:
            img = ImageOps.exif_transpose(img)
            max_dim = max(img.size)
            if max_dim > 1600:
                logger.info("Image too large (%sx%s), resizing to max 1600px", img.size[0], img.size[1])
                img.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                img.save(image_path, quality=90)
    except Exception as e:
        logger.warning("Failed to resize image: %s", e)

    try:
        # Send image directly to Gemini Vision — no OCR step needed
        try:
            doc_data: DocumentData = gemini_service.vision_extract(str(image_path))
        except ValueError as e:
            logger.error("Vision extraction failed: %s", e)
            raise HTTPException(
                status_code=422,
                detail=f"The AI Vision model failed to extract the document: {str(e)}",
            )

        # Build Excel file
        excel_filename = f"{job_id}.xlsx"
        excel_path = config.OUTPUT_DIR / excel_filename
        excel_builder.build_excel(doc_data, excel_path)

        # Store job metadata
        _jobs[job_id] = {
            "image_path": str(image_path),
            "excel_path": str(excel_path),
            "document_data": doc_data.model_dump(),
            "method": "gemini_vision",
        }

        return {
            "job_id": job_id,
            "document_type": doc_data.document_type,
            "language": doc_data.language,
            "fields": [f.model_dump() for f in doc_data.fields],
            "field_count": len(doc_data.fields),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Processing failed for job %s", job_id)
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


@app.get("/api/preview/{job_id}")
async def preview(job_id: str):
    """Return the extracted data for user review."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = _jobs[job_id]
    data = job["document_data"]
    return {
        "job_id": job_id,
        "document_type": data["document_type"],
        "language": data["language"],
        "fields": data["fields"],
        "method": job["method"],
    }


@app.post("/api/retry/{job_id}")
async def retry_with_vision(job_id: str):
    """Re-extract using Gemini Vision (fresh attempt).

    Called when the user says the initial results don't look right.
    """
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = _jobs[job_id]
    image_path = job["image_path"]

    try:
        try:
            doc_data: DocumentData = gemini_service.vision_extract(str(image_path))
        except ValueError as e:
            logger.error("Vision retry failed: %s", e)
            raise HTTPException(
                status_code=422,
                detail=f"The AI Vision model failed to extract the document: {str(e)}",
            )

        # Rebuild Excel
        excel_filename = f"{job_id}.xlsx"
        excel_path = config.OUTPUT_DIR / excel_filename
        excel_builder.build_excel(doc_data, excel_path)

        # Update job
        job["document_data"] = doc_data.model_dump()
        job["excel_path"] = str(excel_path)
        job["method"] = "gemini_vision_retry"

        return {
            "job_id": job_id,
            "document_type": doc_data.document_type,
            "language": doc_data.language,
            "fields": [f.model_dump() for f in doc_data.fields],
            "field_count": len(doc_data.fields),
            "method": "gemini_vision_retry",
        }

    except Exception as e:
        logger.exception("Vision fallback failed for job %s", job_id)
        raise HTTPException(status_code=500, detail=f"Vision fallback failed: {str(e)}")


@app.get("/api/download/{job_id}")
async def download(job_id: str):
    """Download the generated Excel file."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = _jobs[job_id]
    excel_path = Path(job["excel_path"])

    if not excel_path.exists():
        raise HTTPException(status_code=404, detail="Excel file not found")

    doc_type = job["document_data"]["document_type"].replace("_", " ").title()
    download_name = f"{doc_type} - Extracted Data.xlsx"

    return FileResponse(
        path=str(excel_path),
        filename=download_name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
