"""Rule model: metric definitions, alias resolution, range checks.

A ruleset is versioned and immutable once created. Every rule adjustment
creates a new ruleset version; batches pin the exact ruleset they were processed
with (rules_snapshot), so historical results never move.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from .units import UNITS, DIMENSIONS, normalise_alias


class RuleError(ValueError):
    pass


@dataclass
class MetricRule:
    key: str                     # metric/column identifier in the CSV
    label: str | None = None
    target_unit: str = "kg"
    precision: int = 2
    min_value: Fraction | None = None
    max_value: Fraction | None = None
    aliases: dict[str, list[str]] = field(default_factory=dict)
    # aliases: alias string -> list of unit codes it may mean (len > 1 == ambiguous)
    accepted_units: list[str] = field(default_factory=list)  # derived
    max_rounding_delta: Fraction | None = None  # informational only

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label or self.key,
            "target_unit": self.target_unit,
            "precision": self.precision,
            "min_value": _frac_out(self.min_value),
            "max_value": _frac_out(self.max_value),
            "aliases": {k: list(v) for k, v in self.aliases.items()},
            "accepted_units": list(self.accepted_units),
            "max_rounding_delta": _frac_out(self.max_rounding_delta),
        }

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> "MetricRule":
        return MetricRule(
            key=raw["key"],
            label=raw.get("label") or raw["key"],
            target_unit=raw["target_unit"],
            precision=int(raw["precision"]),
            min_value=_frac_in(raw.get("min_value")),
            max_value=_frac_in(raw.get("max_value")),
            aliases={k: list(v) for k, v in raw.get("aliases", {}).items()},
            accepted_units=list(raw.get("accepted_units", [])),
            max_rounding_delta=_frac_in(raw.get("max_rounding_delta")),
        )


@dataclass
class Ruleset:
    id: int
    name: str
    version: int
    metrics: list[MetricRule]

    def metric(self, key: str) -> MetricRule | None:
        for rule in self.metrics:
            if rule.key == key:
                return rule
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "metrics": [m.to_dict() for m in self.metrics],
        }


def _frac_out(value: Fraction | None) -> str | None:
    if value is None:
        return None
    return f"{value.numerator}/{value.denominator}" if value.denominator != 1 else str(value.numerator)


def _frac_in(value: Any) -> Fraction | None:
    if value is None or value == "":
        return None
    return Fraction(str(value))


@dataclass
class AliasIssue:
    metric: str
    alias: str
    units: list[str]

    @property
    def ambiguous(self) -> bool:
        return len(self.units) > 1


def validate_metric(raw: dict[str, Any]) -> tuple[MetricRule, list[str]]:
    """Validate a metric rule payload, returning (rule, warnings)."""
    warnings: list[str] = []
    key = str(raw.get("key") or "").strip()
    if not key:
        raise RuleError("指标名不能为空")
    target = str(raw.get("target_unit") or "").strip()
    if target not in UNITS:
        raise RuleError(f"指标 {key}: 目标单位 {target!r} 未注册")
    try:
        precision = int(raw.get("precision", 2))
    except (TypeError, ValueError):
        raise RuleError(f"指标 {key}: 输出精度必须是整数")
    if precision < 0 or precision > 8:
        raise RuleError(f"指标 {key}: 输出精度必须在 0–8 之间")

    min_raw = raw.get("min_value")
    max_raw = raw.get("max_value")
    min_value = _frac_in(min_raw) if min_raw not in (None, "") else None
    max_value = _frac_in(max_raw) if max_raw not in (None, "") else None
    if min_value is not None and max_value is not None and min_value > max_value:
        raise RuleError(f"指标 {key}: 合理范围下限不能大于上限")
    try:
        if min_raw not in (None, ""):
            Fraction(str(min_raw))
        if max_raw not in (None, ""):
            Fraction(str(max_raw))
    except (ValueError, ZeroDivisionError):
        raise RuleError(f"指标 {key}: 合理范围必须是数字")

    aliases_raw = raw.get("aliases") or {}
    if not isinstance(aliases_raw, dict):
        raise RuleError(f"指标 {key}: aliases 必须是 别名 -> 单位列表 的对象")
    aliases: dict[str, list[str]] = {}
    accepted: list[str] = []
    for alias, targets in aliases_raw.items():
        if isinstance(targets, str):
            targets = [targets]
        if not isinstance(targets, list) or not targets:
            raise RuleError(f"指标 {key}: 别名 {alias!r} 未指向任何单位")
        norm = normalise_alias(str(alias))
        if not norm:
            raise RuleError(f"指标 {key}: 存在空别名")
        unit_codes = []
        for target_code in targets:
            code = str(target_code).strip()
            if code not in UNITS:
                raise RuleError(f"指标 {key}: 别名 {alias!r} 指向未注册单位 {code!r}")
            if UNITS[code].dimension != UNITS[target].dimension:
                raise RuleError(
                    f"指标 {key}: 别名 {alias!r} 指向 {code}，与目标单位 {target} 维度不同"
                    f"（{DIMENSIONS.get(UNITS[code].dimension)} vs {DIMENSIONS.get(UNITS[target].dimension)}）"
                )
            if code not in unit_codes:
                unit_codes.append(code)
        if norm in aliases and aliases[norm] != unit_codes:
            raise RuleError(f"指标 {key}: 别名 {norm!r} 重复且指向不同单位")
        aliases[norm] = unit_codes
        for code in unit_codes:
            if code not in accepted:
                accepted.append(code)
        if len(unit_codes) > 1:
            warnings.append(
                f"指标 {key}: 别名 {norm!r} 同时指向 {', '.join(unit_codes)}，导入时需要用户确认"
            )

    if not aliases:
        raise RuleError(f"指标 {key}: 至少需要一个来源单位别名")

    rule = MetricRule(
        key=key,
        label=str(raw.get("label") or key),
        target_unit=target,
        precision=precision,
        min_value=min_value,
        max_value=max_value,
        aliases=aliases,
        accepted_units=accepted,
        max_rounding_delta=_frac_in(raw.get("max_rounding_delta")),
    )
    return rule, warnings


def validate_ruleset(raw_metrics: list[dict[str, Any]]) -> tuple[list[MetricRule], list[str]]:
    if not raw_metrics:
        raise RuleError("至少需要配置一个指标")
    rules: list[MetricRule] = []
    warnings: list[str] = []
    keys: set[str] = set()
    for raw in raw_metrics:
        rule, warn = validate_metric(raw)
        if rule.key in keys:
            raise RuleError(f"指标 {rule.key} 重复")
        keys.add(rule.key)
        rules.append(rule)
        warnings.extend(warn)
    return rules, warnings


DEFAULT_METRICS: list[dict[str, Any]] = [
    {
        "key": "重量",
        "label": "重量",
        "target_unit": "kg",
        "precision": 3,
        "min_value": "0.001",
        "max_value": "5000",
        "aliases": {
            "kg": ["kg"], "KG": ["kg"], "千克": ["kg"], "公斤": ["kg"],
            "g": ["g"], "克": ["g"],
            "mg": ["mg"], "毫克": ["mg"],
            "t": ["t"], "吨": ["t"],
        },
    },
    {
        "key": "温度",
        "label": "温度",
        "target_unit": "C",
        "precision": 1,
        "min_value": "-60",
        "max_value": "120",
        "aliases": {
            "C": ["C"], "°C": ["C"], "℃": ["C"], "摄氏度": ["C"],
            "F": ["F"], "°F": ["F"], "华氏度": ["F"],
            "K": ["K"], "开尔文": ["K"],
            # Deliberately ambiguous: bare "度" could be C or F and must be
            # confirmed by the user before import.
            "度": ["C", "F"],
        },
    },
    {
        "key": "长度",
        "label": "长度",
        "target_unit": "m",
        "precision": 2,
        "min_value": "0",
        "max_value": "10000",
        "aliases": {
            "m": ["m"], "米": ["m"],
            "cm": ["cm"], "厘米": ["cm"],
            "mm": ["mm"], "毫米": ["mm"],
            "km": ["km"], "千米": ["km"], "公里": ["km"],
        },
    },
    {
        "key": "面积",
        "label": "面积",
        "target_unit": "m2",
        "precision": 2,
        "min_value": "0.0001",
        "max_value": "1000000",
        "aliases": {
            "m2": ["m2"], "m²": ["m2"], "平方米": ["m2"],
            "cm2": ["cm2"], "cm²": ["cm2"], "平方厘米": ["cm2"],
        },
    },
]
