from __future__ import annotations

import io
import re
from decimal import Decimal
from typing import Any

import fitz
import pdfplumber
import pytesseract
from PIL import Image

OCR_FALLBACK_THRESHOLD = Decimal("0.80")


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
            confidence = _native_text_confidence(text, words)
            has_native = confidence >= OCR_FALLBACK_THRESHOLD
            
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
                "confidence": confidence,
                "fallback_required": confidence < OCR_FALLBACK_THRESHOLD,
            }
            
            # Extract tables using pdfplumber
            tables = _extract_tables_pdfplumber(content, page_number)
            page_dict["tables"] = tables
            if tables:
                page_dict["table_confidence"] = max(table["confidence"] for table in tables)
            
            pages.append(page_dict)
    
    # Apply OCR fallback for low-confidence pages
    pages = _apply_ocr_fallback(content, pages)
    
    return pages


def _native_text_confidence(text: str, words: list[dict[str, Any]]) -> Decimal:
    """Estimate whether native extraction is sufficient to avoid OCR."""
    if not text or not words:
        return Decimal(0)
    if len(words) >= 3 and len(text) >= 20:
        return Decimal("0.85")
    word_score = min(Decimal(len(words)) / Decimal(20), Decimal(1))
    text_score = min(Decimal(len(text)) / Decimal(200), Decimal(1))
    return ((word_score + text_score) / Decimal(2)).quantize(Decimal("0.01"))


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
                strategy = "lines"
                if not detected_tables:
                    detected_tables = page.find_tables(
                        table_settings={
                            "vertical_strategy": "text",
                            "horizontal_strategy": "text",
                            "min_words_vertical": 2,
                            "min_words_horizontal": 1,
                            "intersection_tolerance": 5,
                            "text_tolerance": 3,
                        }
                    )
                    strategy = "text"
                
                for table_idx, table in enumerate(detected_tables):
                    cells = []
                    confidence = Decimal("0.95") if strategy == "lines" else Decimal("0.82")
                    
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
                                "confidence": confidence,
                            })
                    
                    if cells:
                        tables.append({
                            "table_index": table_idx,
                            "page": page_number,
                            "cells": cells,
                            "extraction_method": f"pdfplumber_{strategy}",
                            "confidence": confidence,
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
            
            if page_dict["confidence"] < OCR_FALLBACK_THRESHOLD:
                try:
                    # Render page to image and run OCR
                    page = document[page_num]
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    
                    ocr = pytesseract.image_to_data(
                        img, output_type=pytesseract.Output.DICT
                    )
                    ocr_words, ocr_confidence = _ocr_words(ocr, scale=2)
                    ocr_text = " ".join(word["text"] for word in ocr_words)
                    if ocr_text and ocr_confidence > page_dict["confidence"]:
                        page_dict["text"] = ocr_text
                        page_dict["words"] = ocr_words
                        page_dict["extraction_method"] = "ocr"
                        page_dict["has_native_text"] = False
                        page_dict["confidence"] = ocr_confidence
                        page_dict["fallback_required"] = (
                            ocr_confidence < OCR_FALLBACK_THRESHOLD
                        )
                    page_dict["ocr_attempted"] = True
                    page_dict["ocr_confidence"] = ocr_confidence
                except Exception:
                    # OCR failed; keep native extraction
                    page_dict["ocr_attempted"] = True
                    page_dict["ocr_confidence"] = Decimal(0)
            
            result.append(page_dict)
    
    return result


def _ocr_words(data: dict[str, list[Any]], *, scale: int) -> tuple[list[dict[str, Any]], Decimal]:
    words: list[dict[str, Any]] = []
    confidences: list[Decimal] = []
    for index, raw_text in enumerate(data.get("text", [])):
        text = str(raw_text).strip()
        try:
            confidence = Decimal(str(data.get("conf", [])[index]))
        except (IndexError, ValueError):
            continue
        if not text or confidence < 0:
            continue
        left = int(data["left"][index]) / scale
        top = int(data["top"][index]) / scale
        width = int(data["width"][index]) / scale
        height = int(data["height"][index]) / scale
        words.append(
            {
                "text": text,
                "x0": left,
                "y0": top,
                "x1": left + width,
                "y1": top + height,
                "block_number": data.get("block_num", [0] * len(data["text"]))[index],
                "line_number": data.get("line_num", [0] * len(data["text"]))[index],
                "word_number": data.get("word_num", [0] * len(data["text"]))[index],
            }
        )
        confidences.append(confidence)
    if not confidences:
        return words, Decimal(0)
    mean = sum(confidences, Decimal(0)) / Decimal(len(confidences)) / Decimal(100)
    return words, min(Decimal(1), mean.quantize(Decimal("0.01")))


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
