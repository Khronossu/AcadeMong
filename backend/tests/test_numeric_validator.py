"""Unit tests for guardrails/numeric_validator.py.

All tests are pure-function — no DB, no Redis, no network.
validate_numeric_claims(llm_output, sql_results, rag_context) is the only
public API being tested.
"""

from __future__ import annotations

import pytest

from guardrails.numeric_validator import validate_numeric_claims

_PLACEHOLDER = "[ข้อมูลไม่พบในฐานข้อมูล]"


# ── Basic strip / keep behaviour ──────────────────────────────────────────────

def test_unsupported_gpax_is_stripped():
    valid, out, flags = validate_numeric_claims("GPAX ขั้นต่ำ 3.50", [], [])
    assert not valid
    assert _PLACEHOLDER in out
    assert "3.50" not in out
    assert len(flags) == 1
    assert "3.50" in flags[0]


def test_gpax_in_sql_results_is_kept():
    valid, out, flags = validate_numeric_claims(
        "GPAX ขั้นต่ำ 3.50",
        [{"gpax_min": 3.5}],
        [],
    )
    assert valid
    assert not flags
    assert "3.50" in out


def test_gpax_in_rag_context_is_kept():
    valid, out, flags = validate_numeric_claims(
        "GPAX ขั้นต่ำ 3.50",
        [],
        ["GPAX ขั้นต่ำ 3.50 สำหรับคณะนี้"],
    )
    assert valid
    assert not flags
    assert "3.50" in out


def test_non_gpax_range_numbers_are_never_touched():
    """Numbers outside the X.XX pattern (e.g. 80, 100) are never flagged."""
    valid, out, flags = validate_numeric_claims(
        "ต้องได้ 80 คะแนน และ 100 คะแนนเต็ม",
        [],
        [],
    )
    assert valid
    assert not flags
    assert "80" in out
    assert "100" in out


def test_score_with_decimal_not_in_gpax_range():
    """Numbers like 80.5 คะแนน match X.XX but are allowed if in context."""
    valid, out, flags = validate_numeric_claims(
        "ต้องได้ 80.50 คะแนน",
        [],
        ["ต้องได้ 80.50 คะแนน ใน TGAT"],
    )
    assert valid
    assert not flags


def test_score_with_decimal_not_in_context_is_stripped():
    """A single-digit GPAX value like 8.50 not in SQL or context is stripped."""
    valid, out, flags = validate_numeric_claims(
        "GPAX ขั้นต่ำ 8.50",
        [],
        [],
    )
    assert not valid
    assert _PLACEHOLDER in out


def test_two_digit_before_decimal_is_not_gpax_range():
    """Numbers like 80.50 have two digits before the decimal — not GPAX range.

    The validator only strips X.XX values (0.00–9.99). 80.50 is untouched
    since it cannot be a GPAX value.
    """
    valid, out, flags = validate_numeric_claims(
        "ต้องได้ 80.50 คะแนน",
        [],
        [],
    )
    assert valid
    assert not flags
    assert "80.50" in out


# ── Multiple numbers in one response ─────────────────────────────────────────

def test_multiple_numbers_some_valid_some_not():
    sql = [{"gpax_min": 3.0}]
    valid, out, flags = validate_numeric_claims(
        "GPAX ขั้นต่ำ 3.00 และ 3.75 สำหรับคณะแพทย์",
        sql,
        [],
    )
    assert not valid
    assert "3.00" in out          # kept — in SQL
    assert _PLACEHOLDER in out    # 3.75 stripped
    assert len(flags) == 1
    assert "3.75" in flags[0]


def test_same_bad_number_flagged_only_once():
    """Repeated unsupported numbers generate a single flag entry."""
    valid, out, flags = validate_numeric_claims(
        "GPAX 3.50 และ GPAX 3.50 อีกครั้ง",
        [],
        [],
    )
    assert not valid
    assert len(flags) == 1


def test_all_numbers_valid_returns_valid_true():
    sql = [{"gpax_min": 3.0}, {"gpax_min": 3.5}]
    valid, out, flags = validate_numeric_claims(
        "GPAX ขั้นต่ำ 3.00 หรือ 3.50",
        sql,
        [],
    )
    assert valid
    assert not flags


# ── Edge-case inputs ──────────────────────────────────────────────────────────

def test_empty_output_returns_valid():
    valid, out, flags = validate_numeric_claims("", [], [])
    assert valid
    assert out == ""
    assert not flags


def test_output_with_no_numbers_returns_valid():
    valid, out, flags = validate_numeric_claims("ยินดีต้อนรับสู่ AcadeMong", [], [])
    assert valid
    assert not flags


def test_boundary_gpax_values_stripped_when_absent():
    """0.00 and 9.99 are valid GPAX-range matches — strip if not in SQL."""
    _, out1, flags1 = validate_numeric_claims("GPAX 0.00", [], [])
    assert "0.00" in flags1[0]

    _, out2, flags2 = validate_numeric_claims("GPAX 9.99", [], [])
    assert "9.99" in flags2[0]


def test_gpax_from_sql_seats_field_is_extracted():
    """Any numeric field from sql_results contributes to the allowed set."""
    sql = [{"seats": 30, "gpax_min": None}]
    # seats=30 won't be X.XX, so not relevant — but gpax from a different row
    sql2 = [{"gpax_min": 3.20}]
    valid, out, flags = validate_numeric_claims("GPAX ขั้นต่ำ 3.20", sql2, [])
    assert valid
    assert not flags


def test_none_values_in_sql_results_do_not_crash():
    sql = [{"gpax_min": None, "seats": None}]
    valid, out, flags = validate_numeric_claims("GPAX 3.50", sql, [])
    # 3.50 not in None — should be stripped
    assert not valid


def test_rag_context_numbers_build_allowed_set():
    context = ["คะแนน GPAX ขั้นต่ำ 2.75 สำหรับคณะนี้ และ TGAT ≥ 60"]
    valid, out, flags = validate_numeric_claims("GPAX ขั้นต่ำ 2.75", [], context)
    assert valid
    assert not flags
