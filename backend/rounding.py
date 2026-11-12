"""Exact rounding helpers.

Values are carried as fractions.Fraction end-to-end. Rounding happens exactly
once, at output time, using round-half-away-from-zero ("四舍五入", which is the
same as Decimal's ROUND_HALF_UP). Rounding is never applied to intermediate
values.
"""

from __future__ import annotations

from fractions import Fraction


def round_half_up(value: Fraction, precision: int) -> Fraction:
    """Round an exact rational to `precision` decimal places, half away from zero."""
    if precision < 0:
        raise ValueError("precision must be >= 0")
    scale = 10**precision
    scaled = value * scale
    numerator, denominator = scaled.numerator, scaled.denominator
    negative = numerator < 0
    quotient, remainder = divmod(abs(numerator), denominator)
    if 2 * remainder >= denominator:
        quotient += 1
    result = Fraction(quotient, scale)
    return -result if negative else result


def format_fixed(value: Fraction, precision: int) -> str:
    """Render an exactly-rounded value with a fixed number of decimal places."""
    scale = 10**precision
    scaled = value * scale
    if scaled.denominator != 1:
        raise ValueError("format_fixed requires an already rounded value")
    integer = scaled.numerator
    sign = "-" if integer < 0 else ""
    digits = str(abs(integer))
    if precision == 0:
        return sign + digits
    digits = digits.rjust(precision + 1, "0")
    return f"{sign}{digits[:-precision]}.{digits[-precision:]}"


def exact_decimal_text(value: Fraction, max_places: int = 14) -> str:
    """Plain decimal expansion of an exact rational; '…' marks a recurring tail."""
    negative = value < 0
    numerator = abs(value.numerator)
    denominator = value.denominator
    integer, remainder = divmod(numerator, denominator)
    digits: list[str] = []
    for _ in range(max_places):
        if remainder == 0:
            break
        remainder *= 10
        digit, remainder = divmod(remainder, denominator)
        digits.append(str(digit))
    text = str(integer)
    if digits:
        text += "." + "".join(digits)
    if remainder != 0:
        text += "…"
    else:
        text = text.rstrip("0").rstrip(".") if "." in text else text
    return ("-" + text) if negative and text != "0" else text


def fraction_text(value: Fraction) -> str:
    if value.denominator == 1:
        return str(value.numerator)
    return f"{value.numerator}/{value.denominator}"
