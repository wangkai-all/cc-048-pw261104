"""Processing engine: parse values+units, convert exactly, check ranges, round.

Everything upstream of rounding is exact (Fraction). A single rounding step is
applied at output time. The result payload carries a full trace so the UI can
explain unit recognition, formula substitution and rounding for every row.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Any

from .rounding import exact_decimal_text, format_fixed, fraction_text, round_half_up
from .rules import MetricRule
from .units import (
    DIMENSIONS,
    UNITS,
    affine,
    formula_text,
    normalise_alias,
    resolve_global_alias,
)

CATEGORY_LABELS: dict[str, str] = {
    "ok": "正常",
    "empty": "空值",
    "parse_error": "解析失败",
    "unknown_unit": "单位不明",
    "ambiguous_unit": "单位待确认",
    "dimension_mismatch": "维度不匹配",
    "out_of_range": "超出合理范围",
}

CATEGORY_HINTS: dict[str, str] = {
    "ok": "已换算并舍入",
    "empty": "单元格为空或为缺失占位符",
    "parse_error": "无法解析出数值",
    "unknown_unit": "单位不在规则别名表中",
    "ambiguous_unit": "别名同时指向多个单位，需要确认",
    "dimension_mismatch": "来源单位与目标指标维度不同，不能换算",
    "out_of_range": "换算后的目标单位数值超出规则范围",
}

MISSING_MARKERS = {"-", "—", "–", "n/a", "na", "null", "none", "nil", "."}

NUMBER_PATTERN = (
    r"[+-]?(?:(?:(?:\d{1,3}(?:,\d{3})+)|\d+)(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
)

LENGTH_UNITS = {"m", "cm", "mm", "km"}
AREA_UNITS = {"m2", "cm2"}


@dataclass
class CellIssue:
    category: str
    message: str


@dataclass
class ParsedValue:
    value: Fraction
    unit_text: str | None
    number_text: str
    normalized: str


def parse_number_and_unit(cell: str) -> ParsedValue | CellIssue:
    raw = cell.strip()
    if raw == "":
        return CellIssue("empty", "单元格为空")
    if raw.lower() in MISSING_MARKERS:
        return CellIssue("empty", f"占位符 {raw!r} 视为空值")
    normalized_cell = unicodedata.normalize("NFKC", raw)
    match = re.match(rf"^(?P<num>{NUMBER_PATTERN})(?P<rest>.*)$", normalized_cell)
    if not match:
        return CellIssue("parse_error", f"无法从 {raw!r} 中解析数值")
    num_text = match.group("num")
    rest = match.group("rest").strip()
    if rest and rest[0] in ",.0123456789+-":
        return CellIssue("parse_error", f"数字后出现无法识别的内容 {rest!r}")
    clean = num_text.replace(",", "")
    try:
        dec = Decimal(clean)
    except InvalidOperation:
        return CellIssue("parse_error", f"数值 {num_text!r} 不是合法数字")
    if not dec.is_finite():
        return CellIssue("parse_error", f"数值 {num_text!r} 不是有限数")
    return ParsedValue(Fraction(dec), rest or None, num_text, normalise_alias(num_text))


def header_unit_hint(header: str) -> str | None:
    """Extract a unit hint from a header such as '重量（kg）' or 'temp[F]'."""
    match = re.search(r"[（(\[]([^）)\]]+)[）)\]]", unicodedata.normalize("NFKC", header))
    if not match:
        return None
    return match.group(1).strip() or None


def alias_key(metric: str, alias: str) -> str:
    return f"{metric}:{alias}"


def recognise_unit(
    unit_text: str | None,
    rule: MetricRule,
    default_unit: str | None,
    header_default: str | None,
    confirmations: dict[str, str],
    source: str,
) -> dict[str, Any]:
    """Resolve a unit text into a registered unit code, or an issue.

    Precedence: token in the cell > unit column > column default > header default.
    """
    token = unit_text
    if token is None:
        if default_unit:
            token, source = default_unit, "column_default"
        elif header_default:
            token, source = header_default, "header_default"
        else:
            return {
                "code": None,
                "source": None,
                "alias": None,
                "matches": [],
                "via": None,
                "issue": "unknown_unit",
                "message": "未提供单位（单元格、单位列和默认单位均为空）",
            }

    normalized = normalise_alias(token)
    matches = list(rule.aliases.get(normalized, []))
    if not matches:
        other = [code for code in resolve_global_alias(normalized) if code in UNITS]
        if other and all(
            UNITS[code].dimension != UNITS[rule.target_unit].dimension for code in other
        ):
            dimensions = sorted(
                {DIMENSIONS.get(UNITS[code].dimension, UNITS[code].dimension) for code in other}
            )
            return {
                "code": None,
                "source": source,
                "alias": token,
                "matches": other,
                "via": None,
                "issue": "dimension_mismatch",
                "message": (
                    f"单位 {token!r} 是{'/'.join(dimensions)}单位，"
                    f"与指标「{rule.label}」的{DIMENSIONS.get(UNITS[rule.target_unit].dimension, '')}"
                    f"维度不同，不能换算"
                ),
            }
        return {
            "code": None,
            "source": source,
            "alias": token,
            "matches": [],
            "via": None,
            "issue": "unknown_unit",
            "message": f"单位 {token!r} 未在指标「{rule.label}」的别名表中配置",
        }
    if len(matches) > 1:
        confirmed = confirmations.get(alias_key(rule.key, normalized))
        if confirmed and confirmed in matches:
            return {
                "code": confirmed,
                "source": source,
                "alias": token,
                "matches": matches,
                "via": "confirmation",
                "issue": None,
                "message": f"别名 {token!r} 已由用户确认为 {confirmed}",
            }
        return {
            "code": None,
            "source": source,
            "alias": token,
            "matches": matches,
            "via": None,
            "issue": "ambiguous_unit",
            "message": f"别名 {token!r} 同时指向 {', '.join(matches)}，需要确认",
        }
    return {
        "code": matches[0],
        "source": source,
        "alias": token,
        "matches": matches,
        "via": "unambiguous",
        "issue": None,
        "message": f"别名 {token!r} 唯一匹配 {matches[0]}（{UNITS[matches[0]].display}）",
    }


def evaluate_cell(
    *,
    cell: str,
    unit_text: str | None,
    unit_source: str,
    rule: MetricRule,
    confirmations: dict[str, str],
    default_unit: str | None,
    header_default: str | None,
    row_no: int,
) -> dict[str, Any]:
    """Evaluate one (row, metric) pair. Never raises for data problems."""
    base: dict[str, Any] = {
        "row_no": row_no,
        "metric": rule.key,
        "metric_label": rule.label or rule.key,
        "target_unit": rule.target_unit,
        "precision": rule.precision,
        "range": {
            "min": fraction_text(rule.min_value) if rule.min_value is not None else None,
            "max": fraction_text(rule.max_value) if rule.max_value is not None else None,
            "unit": rule.target_unit,
            "basis": "换算后的目标单位（精确值，未舍入）",
        },
        "raw_cell": cell,
        "raw_unit": unit_text,
    }

    parsed = parse_number_and_unit(cell)
    if isinstance(parsed, CellIssue):
        return {
            **base,
            "status": "exception",
            "category": parsed.category,
            "message": parsed.message,
            "raw_value": cell.strip(),
            "raw_value_text": cell.strip(),
            "recognized": None,
            "trace": [{"step": "解析单元格", "detail": parsed.message, "ok": False}],
        }

    effective_token = parsed.unit_text if parsed.unit_text is not None else unit_text
    effective_source = "in_cell" if parsed.unit_text is not None else unit_source
    unit = recognise_unit(
        unit_text=effective_token,
        rule=rule,
        default_unit=default_unit,
        header_default=header_default,
        confirmations=confirmations,
        source=effective_source,
    )
    if parsed.unit_text:
        parse_detail = f"{cell.strip()!r} → 数值 {parsed.number_text}，单位文本 {parsed.unit_text!r}"
    else:
        parse_detail = f"{cell.strip()!r} → 数值 {parsed.number_text}，无单位文本"
    trace: list[dict[str, Any]] = [{"step": "解析单元格", "detail": parse_detail, "ok": True}]
    base["raw_value"] = parsed.number_text
    base["raw_value_text"] = cell.strip()
    base["recognized"] = unit

    if unit["issue"]:
        trace.append({"step": "识别单位", "detail": unit["message"], "ok": False})
        return {
            **base,
            "status": "exception",
            "category": unit["issue"],
            "message": unit["message"],
            "trace": trace,
        }

    source_code = unit["code"]
    trace.append(
        {
            "step": "识别单位",
            "detail": f"来源 {_SOURCE_LABELS.get(unit['source'], unit['source'])}，"
            f"别名 {unit['alias']!r} → {source_code}（{UNITS[source_code].display}）",
            "ok": True,
        }
    )

    source_unit = UNITS[source_code]
    target_unit = UNITS[rule.target_unit]
    if source_unit.dimension != target_unit.dimension:
        message = (
            f"{DIMENSIONS.get(source_unit.dimension, source_unit.dimension)}（{source_code}）"
            f"与目标指标{DIMENSIONS.get(target_unit.dimension, target_unit.dimension)}"
            f"（{rule.target_unit}）维度不同，不能换算"
        )
        trace.append({"step": "维度检查", "detail": message, "ok": False})
        return {
            **base,
            "status": "exception",
            "category": "dimension_mismatch",
            "message": message,
            "trace": trace,
            "source_unit": source_code,
            "source_value": fraction_text(parsed.value),
        }
    trace.append(
        {
            "step": "维度检查",
            "detail": f"{DIMENSIONS.get(source_unit.dimension, source_unit.dimension)} → 同维度，可以换算",
            "ok": True,
        }
    )

    a, b = affine(source_code, rule.target_unit)
    formula = formula_text(source_code, rule.target_unit)
    trace.append({"step": "换算公式", "detail": formula, "ok": True})

    # Range check runs on the exact converted value in the target unit.
    exact = a * parsed.value + b
    range_passed, range_message = _range_check(rule, exact)
    range_outcome: dict[str, Any] | None = None
    if rule.min_value is not None or rule.max_value is not None:
        range_outcome = {"step": "合理范围", "detail": range_message, "ok": range_passed}

    substitution = _substitution_text(formula, a, b, parsed.value, exact)
    trace.append({"step": "代入计算", "detail": substitution, "ok": True})
    if range_outcome:
        trace.append(range_outcome)

    rounded = round_half_up(exact, rule.precision)
    formatted = format_fixed(rounded, rule.precision)
    delta = exact - rounded
    tie = _is_tie(exact, rule.precision)
    rounding = {
        "precision": rule.precision,
        "exact_value": exact_decimal_text(exact),
        "exact_fraction": fraction_text(exact),
        "rounded_value": fraction_text(rounded),
        "formatted": formatted,
        "delta": fraction_text(delta) if delta != 0 else "0",
        "delta_decimal": exact_decimal_text(delta),
        "changed": rounded != exact,
        "half_tie": tie,
        "unit": rule.target_unit,
        "method": "四舍五入（远离零）",
        "detail": _rounding_detail(exact, rounded, delta, rule.precision, tie, formatted),
    }
    trace.append({"step": "舍入输出", "detail": rounding["detail"], "ok": True})

    status, category, message = "ok", "ok", "换算成功"
    if range_passed is False:
        status, category, message = "exception", "out_of_range", range_message

    return {
        **base,
        "status": status,
        "category": category,
        "message": message,
        "source_unit": source_code,
        "source_unit_display": source_unit.display,
        "source_value": fraction_text(parsed.value),
        "source_value_decimal": exact_decimal_text(parsed.value),
        "formula": formula,
        "formula_coefficients": {"a": fraction_text(a), "b": fraction_text(b)},
        "substitution": substitution,
        "exact_result": fraction_text(exact),
        "exact_result_decimal": exact_decimal_text(exact),
        "rounded_result": fraction_text(rounded),
        "formatted_result": formatted,
        "rounding": rounding,
        "range": {**base["range"], "passed": range_passed, "message": range_message},
        "trace": trace,
    }


_SOURCE_LABELS = {
    "in_cell": "单元格内",
    "unit_column": "单位列",
    "column_default": "列默认单位",
    "header_default": "表头提示",
}


def _is_tie(value: Fraction, precision: int) -> bool:
    scaled = value * 10**precision
    numerator, denominator = scaled.numerator, scaled.denominator
    _, remainder = divmod(abs(numerator), denominator)
    return 2 * remainder == denominator


def _range_check(rule: MetricRule, exact: Fraction) -> tuple[bool | None, str]:
    if rule.min_value is None and rule.max_value is None:
        return None, "该指标未配置合理范围"
    below = rule.min_value is not None and exact < rule.min_value
    above = rule.max_value is not None and exact > rule.max_value
    passed = not (below or above)
    bounds: list[str] = []
    if rule.min_value is not None:
        bounds.append(f"≥ {_bound_text(rule.min_value)}")
    if rule.max_value is not None:
        bounds.append(f"≤ {_bound_text(rule.max_value)}")
    unit_display = f"{UNITS[rule.target_unit].display}({rule.target_unit})"
    if passed:
        return True, (
            f"换算值 {exact_decimal_text(exact)} {rule.target_unit} 在 "
            f"{', '.join(bounds)} {unit_display} 内"
        )
    reason = "低于下限" if below else "高于上限"
    return False, (
        f"换算值 {exact_decimal_text(exact)} {rule.target_unit} {reason}，"
        f"合理范围为 {', '.join(bounds)} {unit_display}"
    )


def _bound_text(value: Fraction) -> str:
    """Prefer the exact decimal form for finite expansions, else the fraction."""
    text = exact_decimal_text(value)
    return text if "…" not in text else fraction_text(value)


def _substitution_text(formula: str, a: Fraction, b: Fraction, x: Fraction, y: Fraction) -> str:
    parts: list[str] = []
    parts.append(fraction_text(x) if a == 1 else f"{fraction_text(a)} · {fraction_text(x)}")
    if b != 0:
        parts.append(f"+ {fraction_text(b)}" if b > 0 else f"- {fraction_text(-b)}")
    expression = " ".join(parts)
    return (
        f"{formula}；代入 x = {fraction_text(x)}（即 {exact_decimal_text(x)}）："
        f"y = {expression} = {exact_decimal_text(y)}"
    )


def _rounding_detail(
    exact: Fraction,
    rounded: Fraction,
    delta: Fraction,
    precision: int,
    tie: bool,
    formatted: str,
) -> str:
    exact_text = exact_decimal_text(exact)
    if delta == 0:
        return (
            f"精确值 {exact_text} 恰好是 {precision} 位小数，输出 {formatted}（未发生舍入）"
        )
    direction = "进位" if delta > 0 else "退位"
    text = (
        f"精确值 {exact_text} 四舍五入保留 {precision} 位小数，{direction}到 {formatted}"
        f"（舍入增量 {fraction_text(delta)}）"
    )
    if tie:
        text += "；最低位恰为半值，按四舍五入（远离零）进位"
    return text


def preview_unit_conflicts(
    parsed_rows: list[tuple[int, list[str]]],
    header: list[str],
    column_map: dict[str, dict[str, Any]],
    rules: list[MetricRule],
    confirmations: dict[str, str],
) -> list[dict[str, Any]]:
    """Collect aliases that map to multiple units, with counts and examples."""
    index = {name: position for position, name in enumerate(header)}
    rule_by_key = {rule.key: rule for rule in rules}
    found: dict[tuple[str, str], dict[str, Any]] = {}
    for row_no, cells in parsed_rows:
        for metric, mapping in column_map.items():
            rule = rule_by_key.get(metric)
            if rule is None:
                continue
            value_position = index.get(mapping.get("value_column") or "")
            if value_position is None:
                continue
            cell = cells[value_position] if value_position < len(cells) else ""
            unit_position = index.get(mapping.get("unit_column") or "")
            unit_cell = (
                cells[unit_position]
                if unit_position is not None and unit_position < len(cells)
                else None
            )
            parsed = parse_number_and_unit(cell)
            if isinstance(parsed, CellIssue):
                continue
            token = parsed.unit_text
            if token is None and unit_cell and unit_cell.strip():
                token = unit_cell
            if token is None:
                token = mapping.get("default_unit")
            if token is None:
                token = header_unit_hint(header[value_position])
            if token is None:
                continue
            normalized = normalise_alias(token)
            matches = rule.aliases.get(normalized, [])
            if len(matches) <= 1:
                continue
            if confirmations.get(alias_key(metric, normalized)) in matches:
                continue
            key = (metric, normalized)
            entry = found.setdefault(
                key,
                {
                    "metric": metric,
                    "metric_label": rule.label or metric,
                    "alias": normalized,
                    "raw_alias": token,
                    "units": matches,
                    "count": 0,
                    "examples": [],
                },
            )
            entry["count"] += 1
            if len(entry["examples"]) < 4:
                entry["examples"].append(
                    {"row_no": row_no, "cell": cell, "unit_cell": unit_cell}
                )
    return sorted(found.values(), key=lambda item: (item["metric"], item["alias"]))


def parse_confirmations(raw: Any) -> dict[str, str]:
    if not raw:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("confirmations 必须是对象")
    out: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(value, str) or not value:
            raise ValueError("confirmations 的值必须是单位代码")
        out[str(key)] = value
    return out


def file_hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()
