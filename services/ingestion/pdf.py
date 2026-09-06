from __future__ import annotations

import io
import re
from decimal import Decimal
from typing import Any

import fitz
import pdfplumber
import pytesseract
from PIL import Image


def extract_pdf(content: bytes, *, source_name: str) -> list[dict[str, Any]]:
    """Extract native PDF page text, tables, and word coordinates for later parsing.
    
    Returns list of page dicts with:
    - page_number, width, height, text, words, tables, source_name
    - extraction_method ("native_text", "ocr", "hybrid")
    - has_native_text, confidence score
    """
    pages: list[dict[str, Any]] = []
    
    with fitz.open(stream=content, filetype="pdf") as document:
        for page_number, page in enumerate(document, start=1):
            # Extract native text and coordinates
            words = [
                {
                    "text": word[4],
                    "x0": word[0],
                    "y0": word[1],
                    "x1": word[2],
                    "y1": word[3],
                    "block_number": word[5],
                    "line_number": word[6],
                    "word_number": word[7],
                }
                for word in page.get_text("words", sort=True)
            ]
            
            text = page.get_text("text").strip()
            has_native = bool(words) and len(text) > 10
            
            # Try to extract tables
            page_dict = {
                "page_number": page_number,
                "width": page.rect.width,
                "height": page.rect.height,
                "text": text,
                "words": words,
                "source_name": source_name,
                "extraction_method": "native_text",
                "has_native_text": has_native,
                "confidence": Decimal("1.0") if has_native else Decimal("0.0"),
            }
            
            # Extract tables using pdfplumber
            tables = _extract_tables_pdfplumber(content, page_number)
            if tables:
                page_dict["tables"] = tables
            
            pages.append(page_dict)
    
    # Apply OCR fallback for low-confidence pages
    pages = _apply_ocr_fallback(content, pages)
    
    return pages


def _extract_tables_pdfplumber(content: bytes, page_number: int) -> list[dict[str, Any]]:
    """Extract tables from a specific PDF page using pdfplumber.
    
    Returns normalized cell representation with bbox, row/column indices, text.
    """
    tables = []
    
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            if page_number <= len(pdf.pages):
                page = pdf.pages[page_number - 1]
                detected_tables = page.find_tables()
                
                for table_idx, table in enumerate(detected_tables):
                    cells = []
                    
                    # Extract cells with coordinates. pdfplumber exposes rows
                    # separately; table.cells is a flat list of bounding boxes.
                    for row_idx, row in enumerate(table.rows):
                        for col_idx, cell_bbox in enumerate(row.cells):
                            if cell_bbox is None:
                                continue
                            
                            # Extract text within cell bbox
                            x0, top, x1, bottom = cell_bbox
                            cell_text = page.crop((x0, top, x1, bottom)).extract_text() or ""
                            
                            cells.append({
                                "page": page_number,
                                "table_index": table_idx,
                                "row_index": row_idx,
                                "column_index": col_idx,
                                "bbox": {
                                    "x0": x0,
                                    "y0": top,
                                    "x1": x1,
                                    "y1": bottom,
                                },
                                "text": cell_text.strip(),
                                "cell_type": "header" if row_idx == 0 else "data",
                                "confidence": Decimal("0.95"),
                            })
                    
                    if cells:
                        tables.append({
                            "table_index": table_idx,
                            "page": page_number,
                            "cells": cells,
                            "extraction_method": "pdfplumber",
                            "confidence": Decimal("0.95"),
                        })
    except Exception:
        # pdfplumber extraction failed; will fall back to OCR
        pass
    
    return tables


def _apply_ocr_fallback(content: bytes, pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply OCR to pages with low native-text confidence.
    
    Updates extraction_method and confidence for pages where OCR provides better text.
    """
    result = []
    
    with fitz.open(stream=content, filetype="pdf") as document:
        for page_dict in pages:
            page_num = page_dict["page_number"] - 1
            if page_num >= len(document):
                result.append(page_dict)
                continue
            
            # Only apply OCR if native text is weak (< 20 words or very short)
            word_count = len(page_dict.get("words", []))
            text_length = len(page_dict.get("text", ""))
            
            if word_count < 5 or text_length < 50:
                try:
                    # Render page to image and run OCR
                    page = document[page_num]
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    
                    ocr_text = pytesseract.image_to_string(img)
                    if ocr_text.strip():
                        page_dict["text"] = ocr_text.strip()
                        page_dict["extraction_method"] = "ocr"
                        page_dict["has_native_text"] = False
                        page_dict["confidence"] = Decimal("0.75")  # OCR is less reliable
                except Exception:
                    # OCR failed; keep native extraction
                    pass
            
            result.append(page_dict)
    
    return result


def normalize_financial_value(text: str) -> tuple[Decimal | None, str | None]:
    """Normalize financial values from PDF text.
    
    Handles:
    - Parentheses negatives: (123) → -123
    - Currency symbols: $123.45 → 123.45
    - Thousands separators: 1,234.56 → 1234.56
    - Millions scaling: 1.5M → 1500000
    - Multiple spaces/non-ASCII whitespace
    
    Returns (amount, original_text) or (None, text) if not recognized as financial.
    """
    original = text.strip()
    if not original:
        return None, None
    
    # Preserve original for debugging
    working = original
    
    # Handle parentheses negatives
    is_negative = False
    if working.startswith("(") and working.endswith(")"):
        is_negative = True
        working = working[1:-1]
    
    # Remove currency symbols and whitespace
    working = re.sub(r"[$€£¥₹\s]", "", working)
    
    # Handle scaling (M=million, K=thousand)
    multiplier = Decimal(1)
    if working.lower().endswith("m"):
        multiplier = Decimal(1_000_000)
        working = working[:-1]
    elif working.lower().endswith("k"):
        multiplier = Decimal(1_000)
        working = working[:-1]
    elif working.lower().endswith("b"):
        multiplier = Decimal(1_000_000_000)
        working = working[:-1]
    
    # Remove thousands separators (comma, period as separator in some locales)
    # Be careful: 1,234.56 vs 1.234,56
    # Use last occurrence of separator to determine decimal point
    if "," in working and "." in working:
        if working.rindex(",") > working.rindex("."):
            # European format: 1.234,56
            working = working.replace(".", "").replace(",", ".")
        else:
            # US format: 1,234.56
            working = working.replace(",", "")
    elif "," in working:
        # Only comma - could be thousands or decimal
        # If only one comma and after at least 2 digits, likely thousands
        if working.count(",") == 1 and len(working.split(",")[-1]) >= 2:
            # Likely thousands separator
            working = working.replace(",", "")
        else:
            # Likely decimal separator
            working = working.replace(",", ".")
    
    # Try to parse as decimal
    try:
        amount = Decimal(working) * multiplier
        if is_negative:
            amount = -amount
        return amount, original
    except Exception:
        # Not a valid number
        return None, None


def is_repeated_header(text: str, previous_texts: list[str], threshold: float = 0.85) -> bool:
    """Check if text is a repeated header row (appears multiple times in document).
    
    Used to filter out headers that repeat across pages/sections.
    """
    if not text.strip():
        return False
    
    text_lower = text.lower().strip()
    matches = sum(1 for prev in previous_texts if prev.lower().strip() == text_lower)
    
    return matches >= 2


def is_subtotal_or_total(text: str) -> bool:
    """Detect if a row is a subtotal/total row that should be marked specially."""
    lower = text.lower().strip()
    return any(
        keyword in lower
        for keyword in [
            "total",
            "subtotal",
            "sum",
            "grand total",
            "net",
            "balance",
        ]
    )
