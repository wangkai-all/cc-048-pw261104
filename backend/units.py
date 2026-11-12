"""Unit registry: dimensions, units, exact affine conversions and aliases.

All arithmetic is exact (fractions.Fraction). A conversion between two units of
the same dimension is the affine map

    y = a * x + b

where y is the target value and x the source value. Examples:
  * g -> kg :  y = x * 1/1000
  * F -> C  :  y = 9/5 * x - 160/9   (i.e. 5/9 * (x - 32))
  * C -> F  :  y = 9/5 * x + 32

Every unit therefore declares its relation to its dimension's base unit as
    value_in_base = value * to_base_scale + to_base_offset

Alias rules:
  * Matching is exact after whitespace trimming and Unicode width normalisation
    (NFKC). Case is NEVER folded. "C" and "c" are distinct strings; a unit that
    should accept both spellings must list both explicitly.
  * An alias may point to more than one unit (e.g. a bare "度" can mean Celsius
    or Fahrenheit). Such aliases are reported as ambiguous and are never
    auto-resolved: the user must confirm which unit is meant.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from fractions import Fraction

DIMENSIONS: dict[str, str] = {
    "mass": "重量",
    "temperature": "温度",
    "length": "长度",
    "area": "面积",
    "volume": "体积",
    "time": "时间",
    "speed": "速度",
}


def fraction_text(value: Fraction) -> str:
    """Format an exact rational as a plain string ('1/1000' or '32')."""
    if value.denominator == 1:
        return str(value.numerator)
    return f"{value.numerator}/{value.denominator}"


@dataclass(frozen=True)
class Unit:
    code: str
    dimension: str
    to_base_scale: Fraction
    to_base_offset: Fraction
    display: str

    def to_base(self, value: Fraction) -> Fraction:
        return value * self.to_base_scale + self.to_base_offset

    def from_base(self, value: Fraction) -> Fraction:
        return (value - self.to_base_offset) / self.to_base_scale


UNITS: dict[str, Unit] = {}


def _add(code: str, dimension: str, scale: str, offset: str, display: str) -> None:
    UNITS[code] = Unit(code, dimension, Fraction(scale), Fraction(offset), display)


# mass, base = kg
_add("kg", "mass", "1", "0", "千克")
_add("g", "mass", "1/1000", "0", "克")
_add("mg", "mass", "1/1000000", "0", "毫克")
_add("t", "mass", "1000", "0", "吨")

# temperature, base = °C
_add("C", "temperature", "1", "0", "摄氏度")
_add("F", "temperature", "5/9", "-160/9", "华氏度")
_add("K", "temperature", "1", "-273.15", "开尔文")

# length, base = m
_add("m", "length", "1", "0", "米")
_add("cm", "length", "1/100", "0", "厘米")
_add("mm", "length", "1/1000", "0", "毫米")
_add("km", "length", "1000", "0", "千米")

# area, base = m²
_add("m2", "area", "1", "0", "平方米")
_add("cm2", "area", "1/10000", "0", "平方厘米")

# volume, base = L
_add("l", "volume", "1", "0", "升")
_add("ml", "volume", "1/1000", "0", "毫升")

# time, base = s
_add("s", "time", "1", "0", "秒")
_add("min", "time", "60", "0", "分钟")
_add("h", "time", "3600", "0", "小时")

# speed, base = m/s
_add("m/s", "speed", "1", "0", "米每秒")
_add("km/h", "speed", "1000/3600", "0", "千米每小时")


# Default alias table used to pre-fill rule configuration. Case is significant,
# so both "l" and "L" are listed for litre, while "KG" is listed but "kG" is not.
DEFAULT_ALIASES: dict[str, list[str]] = {
    "kg": ["kg", "KG", "千克", "公斤"],
    "g": ["g", "克"],
    "mg": ["mg", "毫克"],
    "t": ["t", "吨"],
    "C": ["C", "°C", "℃", "摄氏度", "degC"],
    "F": ["F", "°F", "华氏度", "degF"],
    "K": ["K", "开尔文"],
    "m": ["m", "米"],
    "cm": ["cm", "厘米"],
    "mm": ["mm", "毫米"],
    "km": ["km", "千米", "公里"],
    "m2": ["m2", "m²", "平方米"],
    "cm2": ["cm2", "cm²", "平方厘米"],
    "l": ["l", "L", "升"],
    "ml": ["ml", "mL", "毫升"],
    "s": ["s", "秒"],
    "min": ["min", "分钟"],
    "h": ["h", "小时"],
    "m/s": ["m/s", "米每秒"],
    "km/h": ["km/h", "千米每小时"],
}


def normalise_alias(raw: str) -> str:
    """Trim, NFKC-normalise, drop internal whitespace. Never changes case."""
    text = unicodedata.normalize("NFKC", raw.strip())
    return "".join(text.split())


def global_alias_index() -> dict[str, list[str]]:
    """Alias index over all registered units, independent of metric rules.

    Used only to distinguish 'unit belongs to another dimension' from 'unit not
    recognised at all'. Metric rules still decide what is accepted for a metric.
    """
    index: dict[str, list[str]] = {}
    for code, aliases in DEFAULT_ALIASES.items():
        if code not in UNITS:
            continue
        for alias in aliases:
            norm = normalise_alias(alias)
            index.setdefault(norm, [])
            if code not in index[norm]:
                index[norm].append(code)
    return index


_GLOBAL_ALIASES: dict[str, list[str]] | None = None


def resolve_global_alias(raw: str) -> list[str]:
    global _GLOBAL_ALIASES
    if _GLOBAL_ALIASES is None:
        _GLOBAL_ALIASES = global_alias_index()
    return list(_GLOBAL_ALIASES.get(normalise_alias(raw), []))


def affine(source: str, target: str) -> tuple[Fraction, Fraction]:
    """Return (a, b) so that target_value = a * source_value + b, exactly."""
    src = UNITS[source]
    dst = UNITS[target]
    if src.dimension != dst.dimension:
        raise DimensionMismatch(src.dimension, dst.dimension)
    a = src.to_base_scale / dst.to_base_scale
    b = (src.to_base_offset - dst.to_base_offset) / dst.to_base_scale
    return a, b


def formula_text(source: str, target: str) -> str:
    """Human-readable symbolic formula, e.g. 'y = 9/5 · x - 160/9'."""
    a, b = affine(source, target)
    parts: list[str] = []
    if a == 1:
        parts.append("x")
    elif a == -1:
        parts.append("-x")
    else:
        parts.append(f"{fraction_text(a)} · x")
    if b != 0:
        if b > 0:
            parts.append(f"+ {fraction_text(b)}")
        else:
            parts.append(f"- {fraction_text(-b)}")
    elif not parts:
        parts.append("0")
    return "y = " + " ".join(parts)


def convert_exact(value: Fraction, source: str, target: str) -> Fraction:
    a, b = affine(source, target)
    return a * value + b


class DimensionMismatch(ValueError):
    def __init__(self, src: str, dst: str):
        self.src = src
        self.dst = dst
        super().__init__(
            f"维度不匹配：{DIMENSIONS.get(src, src)} 与 {DIMENSIONS.get(dst, dst)} 不能换算"
        )
