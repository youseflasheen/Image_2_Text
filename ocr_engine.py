"""
OCR Engine module — wraps PaddleOCR for text extraction with Arabic support.

Extracts text and bounding-box coordinates from document images.
Post-processes Arabic text for correct RTL rendering.

Compatible with PaddleOCR 3.x (paddleocr >= 3.7).
"""

import logging
from typing import Optional

from paddleocr import PaddleOCR

logger = logging.getLogger(__name__)

# ── Lazy singleton ───────────────────────────────────────────────────────────
_ocr_instance: Optional[PaddleOCR] = None


def _get_ocr() -> PaddleOCR:
    """Return a shared PaddleOCR instance (models download on first call)."""
    global _ocr_instance
    if _ocr_instance is None:
        # Disable MKLDNN to bypass PIR compatibility issues on CPU in PaddlePaddle 3.x
        # Also set memory allocation strategy to auto_growth to prevent RAM lockups
        import os
        os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "0"
        os.environ["FLAGS_allocator_strategy"] = "auto_growth"
        os.environ["FLAGS_fraction_of_gpu_memory_to_use"] = "0.1"
        
        logger.info("Initializing PaddleOCR (first run may download models)…")
        _ocr_instance = PaddleOCR(
            lang="ar",                        # Arabic — also handles English mixed text
            use_textline_orientation=True,     # PaddleOCR 3.x param (replaces use_angle_cls)
            use_doc_orientation_classify=False, # Skip full-page rotation detection for speed
            use_doc_unwarping=False,           # Skip document unwarping for speed
            enable_mkldnn=False,               # Disable MKLDNN to prevent PIR errors
        )
        logger.info("PaddleOCR ready.")
    return _ocr_instance



def _is_arabic(text: str) -> bool:
    """Heuristic: check if the text contains Arabic characters."""
    for ch in text:
        if "\u0600" <= ch <= "\u06FF" or "\u0750" <= ch <= "\u077F":
            return True
    return False


def _parse_ocr_result(raw_results) -> list[dict]:
    """Parse PaddleOCR results into a uniform list of dicts.

    Handles both PaddleOCR v2 list-of-lists format and PaddleOCR v3 (PaddleX) 
    OCRResult dict-like format.
    """
    structured: list[dict] = []

    if not raw_results:
        return structured

    for page in raw_results:
        if not page:
            continue
            
        # PaddleOCR v3 (PaddleX) format
        if isinstance(page, dict) or hasattr(page, "keys"):
            dt_polys = page.get("dt_polys", [])
            rec_texts = page.get("rec_texts", [])
            rec_scores = page.get("rec_scores", [])
            
            for bbox, text, score in zip(dt_polys, rec_texts, rec_scores):
                try:
                    bbox_list = bbox.tolist()
                except AttributeError:
                    bbox_list = bbox

                structured.append({
                    "text": text,
                    "bbox": bbox_list,
                    "confidence": float(score),
                })
        else:
            # PaddleOCR v2 format
            for line in page:
                bbox = line[0]
                text = line[1][0]
                confidence = float(line[1][1])

                structured.append({
                    "text": text,
                    "bbox": bbox,
                    "confidence": confidence,
                })

    return structured


# ── Public API ───────────────────────────────────────────────────────────────

def extract_text(image_path: str) -> list[dict]:
    """Run OCR on an image and return structured results.

    Parameters
    ----------
    image_path : str
        Absolute or relative path to the document image.

    Returns
    -------
    list[dict]
        Each element:
        {
            "text": str,            # Recognised text
            "bbox": list[list],     # 4-point bounding box [[x1,y1], …, [x4,y4]]
            "confidence": float,    # 0-1
        }
    """
    ocr = _get_ocr()

    # Use the .ocr() method for v2-compatible output format
    raw_results = ocr.ocr(image_path)
    structured = _parse_ocr_result(raw_results)

    if not structured:
        logger.warning("PaddleOCR returned no results for %s", image_path)

    logger.info("Extracted %d text regions from %s", len(structured), image_path)
    return structured


def results_to_plain_text(ocr_results: list[dict]) -> str:
    """Concatenate OCR results into a single plain-text string.

    Sorts results top-to-bottom, left-to-right by the top-left corner of
    each bounding box so the text reads in natural document order.
    """
    if not ocr_results:
        return ""

    # Sort by Y first (top→bottom), then X (left→right)
    sorted_results = sorted(
        ocr_results,
        key=lambda r: (
            min(pt[1] for pt in r["bbox"]),   # top Y
            min(pt[0] for pt in r["bbox"]),   # left X
        ),
    )
    return "\n".join(r["text"] for r in sorted_results)
