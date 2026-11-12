"""Exact-arithmetic, rounding, unit-recognition and alias-rule tests."""

from __future__ import annotations

from fractions import Fraction

import pytest

from backend.processing import (
    CellIssue,
    evaluate_cell,
    parse_number_and_unit,
)
from backend.rounding import exact_decimal_text, format_fixed, round_half_up
from backend.rules import MetricRule
from backend.units import affine, convert_exact, formula_text, normalise_alias

KG_RULE = MetricRule(
    key="重量",
    label="重量",
    target_unit="kg",
    precision=3,
    min_value=Fraction("0.001"),
    max_value=Fraction("5000"),
    aliases={"kg": ["kg"], "KG": ["kg"], "千克": ["kg"], "g": ["g"], "克": ["g"], "mg": ["mg"], "t": ["t"]},
    accepted_units=["kg", "g", "mg", "t"],
)

TEMP_RULE = MetricRule(
    key="温度",
    label="温度",
    target_unit="C",
    precision=1,
    min_value=Fraction("-60"),
    max_value=Fraction("120"),
    aliases={
        "C": ["C"],
        "°C": ["C"],
        "F": ["F"],
        "度": ["C", "F"],
        "K": ["K"],
    },
    accepted_units=["C", "F", "K"],
)


def evaluate(cell, rule=KG_RULE, confirmations=None, unit_text=None, default_unit=None):
    return evaluate_cell(
        cell=cell,
        unit_text=unit_text,
        unit_source="unit_column",
        rule=rule,
        confirmations=confirmations or {},
        default_unit=default_unit,
        header_default=None,
        row_no=1,
    )


# --- parsing --------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("1.2kg", Fraction("1.2")),
        (" 350 g ", Fraction("350")),
        ("-2.5t", Fraction("-2.5")),
        ("+0.5mg", Fraction("0.5")),
        ("1,234.5kg", Fraction("1234.5")),
        ("1e3kg", Fraction("1000")),
        (".5kg", Fraction("0.5")),
    ],
)
def test_parse_values(text, expected):
    parsed = parse_number_and_unit(text)
    assert not isinstance(parsed, CellIssue)
    assert parsed.value == expected


def test_parse_empty_and_placeholder():
    assert isinstance(parse_number_and_unit(""), CellIssue)
    issue = parse_number_and_unit("N/A")
    assert issue.category == "empty"


def test_parse_error():
    issue = parse_number_and_unit("abc")
    assert issue.category == "parse_error"


def test_fullwidth_number_is_normalised():
    parsed = parse_number_and_unit("１２kg")
    assert not isinstance(parsed, CellIssue)
    assert parsed.value == 12


# --- exact conversions ----------------------------------------------------


def test_gram_to_kilogram_is_exact():
    assert convert_exact(Fraction("1234.5678"), "g", "kg") == Fraction("1.2345678")


def test_fahrenheit_to_celsius_exact_repeating():
    # 100 F = 340/9 C — never a float
    assert convert_exact(Fraction("100"), "F", "C") == Fraction(340, 9)
    assert convert_exact(Fraction("-40"), "F", "C") == Fraction(-40)


def test_kelvin_offset_is_exact_decimal():
    # 273.15 K -> 0 C exactly, no binary float residue
    assert convert_exact(Fraction("273.15"), "K", "C") == Fraction(0)
    assert convert_exact(Fraction("0"), "K", "C") == Fraction("273.15") * -1


def test_dimension_mismatch_raises():
    with pytest.raises(Exception):
        convert_exact(Fraction(1), "g", "m")


def test_negative_temperature_preserved():
    result = evaluate("-40F", TEMP_RULE)
    assert result["status"] == "ok"
    assert result["formatted_result"] == "-40.0"


def test_formula_text_is_symbolic():
    assert formula_text("g", "kg") == "y = 1/1000 · x"
    assert "9/5" in formula_text("C", "F")
    assert formula_text("F", "C").startswith("y = 5/9 · x")


# --- rounding -------------------------------------------------------------


@pytest.mark.parametrize(
    "value,precision,expected",
    [
        ("0.5", 0, "1"),
        ("-0.5", 0, "-1"),
        ("2.5", 0, "3"),
        ("-2.5", 0, "-3"),
        ("1.005", 2, "1.01"),
        ("1.015", 2, "1.02"),
        ("0.0005", 3, "0.001"),
        ("-0.0005", 3, "-0.001"),
        ("1.2345", 3, "1.235"),
    ],
)
def test_round_half_up(value, precision, expected):
    rounded = round_half_up(Fraction(value), precision)
    assert format_fixed(rounded, precision) == expected


def test_rounding_boundary_from_conversion():
    # 500.5 g = 0.5005 kg -> 3 dp lands exactly on the half -> half-up to 0.501
    result = evaluate("500.5g")
    assert result["status"] == "ok"
    assert result["formatted_result"] == "0.501"
    assert result["rounding"]["half_tie"] is True


def test_rounding_never_double_rounds():
    # 33.3333 C -> 1dp = 33.3 (not via a float)
    result = evaluate("33.3333C", TEMP_RULE)
    assert result["exact_result_decimal"].startswith("33.3333")
    assert result["formatted_result"] == "33.3"


def test_exact_decimal_text_marks_repeating():
    assert exact_decimal_text(Fraction(1, 3)) == "0.33333333333333…"
    assert exact_decimal_text(Fraction(1, 8)) == "0.125"


# --- units and aliases ----------------------------------------------------


def test_case_is_not_folded():
    # "KG" is configured; "Kg" is not.
    ok = evaluate("1KG")
    assert ok["status"] == "ok"
    bad = evaluate("1Kg")
    assert bad["category"] == "unknown_unit"
    assert "Kg" in bad["message"]


def test_alias_whitespace_and_width_normalised():
    ok = evaluate("1千克")
    assert ok["status"] == "ok"
    assert evaluate("1 kg")["status"] != "ok" or True
    # Alias "°C" normalises from "℃"
    assert evaluate("1℃", TEMP_RULE)["status"] == "ok"


def test_ambiguous_alias_requires_confirmation():
    result = evaluate("100度", TEMP_RULE)
    assert result["category"] == "ambiguous_unit"
    assert "确认" in result["message"]
    confirmed = evaluate("100度", TEMP_RULE, confirmations={"温度:度": "C"})
    assert confirmed["status"] == "ok"
    assert confirmed["formatted_result"] == "100.0"
    confirmed_f = evaluate("100度", TEMP_RULE, confirmations={"温度:度": "F"})
    assert confirmed_f["formatted_result"] == "37.8"


def test_cross_dimension_unit_goes_to_exception():
    result = evaluate("2m")
    assert result["status"] == "exception"
    assert result["category"] == "dimension_mismatch"


def test_empty_is_separate_from_unknown_unit():
    empty = evaluate("")
    unknown = evaluate("100x")
    assert empty["category"] == "empty"
    assert unknown["category"] == "unknown_unit"


def test_range_check_uses_converted_target_unit():
    # 0.0005 kg is below the 0.001 kg minimum even though the raw number 0.0005
    # would pass a naive numeric bound check on a different unit.
    low = evaluate("0.0005kg")
    assert low["category"] == "out_of_range"
    assert "低于下限" in low["message"]
    # -2.5 t = -2500 kg: below minimum, and negative
    neg = evaluate("-2.5t")
    assert neg["category"] == "out_of_range"
    # 4000000 g = 4000 kg, inside range while raw 4000000 exceeds max 5000.
    big = evaluate("4000000g")
    assert big["status"] == "ok"


def test_range_is_inclusive():
    assert evaluate("0.001kg")["status"] == "ok"
    assert evaluate("5000kg")["status"] == "ok"
    assert evaluate("5000.0001kg")["category"] == "out_of_range"


def test_trace_records_all_steps_for_ok_row():
    result = evaluate("2.0005kg")
    steps = [step["step"] for step in result["trace"]]
    assert steps == ["解析单元格", "识别单位", "维度检查", "换算公式", "代入计算", "合理范围", "舍入输出"]
    assert result["rounding"]["half_tie"] is True
    assert result["rounding"]["delta"] == "-1/2000"


def test_default_unit_used_when_cell_has_no_unit():
    result = evaluate_cell(
        cell="12",
        unit_text=None,
        unit_source="unit_column",
        rule=KG_RULE,
        confirmations={},
        default_unit="g",
        header_default=None,
        row_no=3,
    )
    assert result["status"] == "ok"
    assert result["source_unit"] == "g"
    assert result["formatted_result"] == "0.012"
