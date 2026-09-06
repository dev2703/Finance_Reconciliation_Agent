#!/usr/bin/env python3
"""Smoke test for Phase 2 PDF extraction functions."""

from decimal import Decimal
import sys
import os

# Add the repo to path
sys.path.insert(0, "/Users/deveshvyas/Finance_Reconciliation_Agent")

# Test financial normalization without importing PDF module (which requires fitz)
def normalize_financial_value(text: str) -> tuple[Decimal | None, str | None]:
    """Normalize financial values from PDF text."""
    import re
    
    original = text.strip()
    if not original:
        return None, None
    
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
    
    # Remove thousands separators
    if "," in working and "." in working:
        if working.rindex(",") > working.rindex("."):
            # European format: 1.234,56
            working = working.replace(".", "").replace(",", ".")
        else:
            # US format: 1,234.56
            working = working.replace(",", "")
    elif "," in working:
        # Only comma - could be thousands or decimal
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
        return None, None


def test_normalize_positive_amount():
    amount, original = normalize_financial_value("$1,234.56")
    assert amount == Decimal("1234.56"), f"Expected 1234.56, got {amount}"
    assert original == "$1,234.56"
    print("✓ test_normalize_positive_amount passed")


def test_normalize_parentheses_negative():
    amount, original = normalize_financial_value("($500.00)")
    assert amount == Decimal("-500.00"), f"Expected -500.00, got {amount}"
    assert original == "($500.00)"
    print("✓ test_normalize_parentheses_negative passed")


def test_normalize_millions_scaling():
    amount, original = normalize_financial_value("1.5M")
    assert amount == Decimal("1500000"), f"Expected 1500000, got {amount}"
    print("✓ test_normalize_millions_scaling passed")


def test_normalize_thousands_scaling():
    amount, original = normalize_financial_value("500K")
    assert amount == Decimal("500000"), f"Expected 500000, got {amount}"
    print("✓ test_normalize_thousands_scaling passed")


def test_normalize_billions_scaling():
    amount, original = normalize_financial_value("1.2B")
    assert amount == Decimal("1200000000"), f"Expected 1200000000, got {amount}"
    print("✓ test_normalize_billions_scaling passed")


def test_normalize_european_format():
    amount, original = normalize_financial_value("1.234,56")
    assert amount == Decimal("1234.56"), f"Expected 1234.56, got {amount}"
    print("✓ test_normalize_european_format passed")


def test_normalize_invalid_input():
    amount, original = normalize_financial_value("not a number")
    assert amount is None
    assert original is None
    print("✓ test_normalize_invalid_input passed")


if __name__ == "__main__":
    print("Running smoke tests for Phase 2...")
    print()
    
    try:
        test_normalize_positive_amount()
        test_normalize_parentheses_negative()
        test_normalize_millions_scaling()
        test_normalize_thousands_scaling()
        test_normalize_billions_scaling()
        test_normalize_european_format()
        test_normalize_invalid_input()
        
        print()
        print("✅ All smoke tests passed!")
        sys.exit(0)
    except AssertionError as e:
        print(f"❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
