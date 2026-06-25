"""
LLM Service — integrates OpenRouter (OpenAI-compatible) for document classification
and key-value extraction, with a Vision fallback for direct image reading.
"""

import json
import logging
import base64
from typing import Optional

from pydantic import BaseModel, Field

from openai import OpenAI

import config

logger = logging.getLogger(__name__)

# ── Pydantic schemas for structured output ───────────────────────────────────


class KeyValuePair(BaseModel):
    """A single extracted field from the document."""
    key: str = Field(description="The field name or label (e.g. 'Invoice Number', 'Date', 'Total')")
    value: str = Field(description="The field value")


class DocumentData(BaseModel):
    """Structured extraction result for a financial document."""
    document_type: str = Field(
        description="Type of document: invoice, receipt, contract, bank_statement, tax_form, purchase_order, or other"
    )
    language: str = Field(description="Primary language of the document (e.g. 'Arabic', 'English')")
    fields: list[KeyValuePair] = Field(
        description="All extracted key-value pairs from the document"
    )


# ── OpenRouter client (lazy) ────────────────────────────────────────────────

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not config.OPENROUTER_API_KEY:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set. "
                "Copy .env.example → .env and add your key from https://openrouter.ai/"
            )
        _client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=config.OPENROUTER_API_KEY,
        )
        logger.info("OpenRouter client initialised (model=%s)", config.LLM_MODEL)
    return _client


# ── Prompts ──────────────────────────────────────────────────────────────────

_CLASSIFY_AND_EXTRACT_PROMPT = """\
You are an expert financial document analyst. You receive OCR-extracted text
from a document image. Your job is to:

1. **Classify** the document type (invoice, receipt, contract, bank_statement,
   tax_form, purchase_order, or other).
2. **Extract every key-value pair** you can find — dates, amounts, names,
   addresses, reference numbers, line items, totals, taxes, etc.

Rules:
- Preserve the original language of values (Arabic, English, mixed).
- For monetary amounts, include the currency symbol/code if visible.
- For dates, keep the original format found in the document.
- If a field appears multiple times (e.g. line items), number them
  (e.g. "Item 1 Description", "Item 1 Amount").
- Be exhaustive — extract every piece of structured information.
- Return ONLY valid JSON matching the exact schema requested.

OCR Text:
{ocr_text}
"""

_VISION_FALLBACK_PROMPT = """\
You are an expert financial document analyst. The previous OCR extraction
was inaccurate, so you are now reading the original document image directly.

Please:
1. **Classify** the document type (invoice, receipt, contract, bank_statement,
   tax_form, purchase_order, or other).
2. **Extract every key-value pair** visible in this document — dates, amounts,
   names, addresses, reference numbers, line items, totals, taxes, etc.

Rules:
- Preserve the original language of values (Arabic, English, mixed).
- For monetary amounts, include the currency symbol/code if visible.
- For dates, keep the original format found in the document.
- If a field appears multiple times (e.g. line items), number them
  (e.g. "Item 1 Description", "Item 1 Amount").
- Be exhaustive — extract every piece of structured information.
- Return ONLY valid JSON matching the exact schema requested.
"""


# ── Public API ───────────────────────────────────────────────────────────────


def classify_and_extract(ocr_text: str) -> DocumentData:
    """Send OCR text to LLM and get structured document data.

    Parameters
    ----------
    ocr_text : str
        Plain-text output from PaddleOCR.

    Returns
    -------
    DocumentData
        Classified document type + extracted key-value pairs.
    """
    client = _get_client()
    prompt = _CLASSIFY_AND_EXTRACT_PROMPT.format(ocr_text=ocr_text)

    logger.info("Sending OCR text to OpenRouter for classification…")
    
    # We use client.beta.chat.completions.parse which requires models supporting structured outputs.
    # Alternatively, for broader compatibility on OpenRouter, we can use JSON format and validate via Pydantic.
    schema_hint = json.dumps(DocumentData.model_json_schema(), indent=2)
    system_msg = (
        "You are an expert financial document analyst. "
        "Always respond with valid JSON matching this schema:\n"
        f"{schema_hint}"
    )
    
    response = client.chat.completions.create(
        model=config.LLM_MODEL,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"}
    )

    content = response.choices[0].message.content.strip()
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()

    try:
        data = DocumentData.model_validate_json(content)
    except Exception as e:
        logger.error(f"Failed to parse LLM output. Raw content: {content}")
        raise ValueError(f"LLM returned invalid JSON: {str(e)}")

    logger.info(
        "LLM classified document as '%s' with %d fields",
        data.document_type,
        len(data.fields),
    )
    return data



def vision_extract(image_path: str) -> DocumentData:
    """Read the document image directly with Gemini Vision and extract data.

    Parameters
    ----------
    image_path : str
        Path to the document image.

    Returns
    -------
    DocumentData
        Classified document type + extracted key-value pairs.
    """
    client = _get_client()
    
    # Read and encode image
    with open(image_path, "rb") as f:
        encoded_image = base64.b64encode(f.read()).decode('utf-8')
        
    mime_type = "image/jpeg"
    if image_path.lower().endswith(".png"):
        mime_type = "image/png"
    elif image_path.lower().endswith(".webp"):
        mime_type = "image/webp"

    schema_hint = json.dumps(DocumentData.model_json_schema(), indent=2)
    system_msg = (
        "You are an expert financial document analyst. "
        "Always respond with valid JSON matching this schema:\n"
        f"{schema_hint}"
    )

    vision_prompt = """\
You are an expert financial document analyst. Read this document image directly.

Please:
1. **Classify** the document type (invoice, receipt, contract, bank_statement,
   tax_form, purchase_order, or other).
2. **Extract every key-value pair** visible in this document — dates, amounts,
   names, addresses, reference numbers, line items, totals, taxes, etc.

Rules:
- Preserve the original language of values (Arabic, English, mixed).
- For monetary amounts, include the currency symbol/code if visible.
- For dates, keep the original format found in the document.
- If a field appears multiple times (e.g. line items), number them
  (e.g. "Item 1 Description", "Item 1 Amount").
- Be exhaustive — extract every piece of structured information.
- Return ONLY valid JSON matching the exact schema requested.
"""

    logger.info("Sending image to Gemini Vision via OpenRouter: %s", image_path)
    
    response = client.chat.completions.create(
        model=config.LLM_MODEL,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": system_msg},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": vision_prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{encoded_image}"
                        }
                    }
                ]
            }
        ],
        response_format={"type": "json_object"}
    )

    content = response.choices[0].message.content.strip()
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()

    try:
        data = DocumentData.model_validate_json(content)
    except Exception as e:
        logger.error(f"Failed to parse Gemini Vision output. Raw content: {content}")
        raise ValueError(f"Gemini Vision returned invalid JSON: {str(e)}")

    logger.info(
        "Gemini Vision extracted '%s' with %d fields",
        data.document_type,
        len(data.fields),
    )
    return data

