"""
Configuration module for the Document Extraction application.
Loads environment variables and defines application-wide settings.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ── Directories ──────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent

# Load .env file explicitly from the project directory
load_dotenv(BASE_DIR / ".env")
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
STATIC_DIR = BASE_DIR / "static"

# Ensure directories exist
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# ── OpenRouter ───────────────────────────────────────────────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "google/gemini-2.5-flash")

# ── Server ───────────────────────────────────────────────────────────────────
PORT = int(os.getenv("PORT", "8000"))

# ── Application ──────────────────────────────────────────────────────────────
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".webp"}
MAX_FILE_SIZE_MB = 20
