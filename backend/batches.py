"""Batch orchestration: mapping, preview, processing, comparison, export."""

from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import datetime, timezone
from fractions import Fraction
from typing import Any, Iterable

from .csvio import ParsedCsv, parse_csv
from .db import loads, row_to_dict, session
from .processing import (
    CATEGORY_HINTS,
    CATEGORY_LABELS,
    alias_key,
    evaluate_cell,
    file_hash,
    header_unit_hint,
    parse_confirmations,
    preview_unit_conflicts,
)
from .rounding import format_fixed, fraction_text, round_half_up
from .rules import MetricRule, Ruleset, _frac_in
from .units import UNITS, normalise_alias


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def storage_root() -> "Path":
    from pathlib import Path

    return Path(__file__).resolve().parent.parent / "data" / "datasets"


# --- rulesets -------------------------------------------------------------


def save_ruleset(conn, name: str, metrics: list[MetricRule], warnings: list[str]) -> Ruleset:
    version = conn.execute("SELECT COALESCE(MAX(version), 0) + 1 FROM rulesets").fetchone()[0]
    cur = conn.execute(
        "INSERT INTO rulesets (name, version, metrics, warnings, created_at) VALUES (?,?,?,?,?)",
        (
            name,
            version,
            json.dumps([m.to_dict() for m in metrics], ensure_ascii=False),
            json.dumps(warnings, ensure_ascii=False),
            now_iso(),
        ),
    )
    conn.commit()
    return Ruleset(id=cur.lastrowid, name=name, version=version, metrics=metrics)


def latest_ruleset(conn) -> Ruleset | None:
    row = conn.execute("SELECT * FROM rulesets ORDER BY version DESC LIMIT 1").fetchone()
    return _ruleset_from_row(row) if row else None


def get_ruleset(conn, ruleset_id: int) -> Ruleset:
    row = conn.execute("SELECT * FROM rulesets WHERE id = ?", (ruleset_id,)).fetchone()
    if row is None:
        raise NotFound(f"规则集 {ruleset_id} 不存在")
    return _ruleset_from_row(row)


def _ruleset_from_row(row) -> Ruleset:
    metrics = [MetricRule.from_dict(item) for item in loads(row["metrics"], [])]
    return Ruleset(id=row["id"], name=row["name"], version=row["version"], metrics=metrics)


def ruleset_public(conn, ruleset: Ruleset) -> dict[str, Any]:
    row = conn.execute("SELECT warnings FROM rulesets WHERE id = ?", (ruleset.id,)).fetchone()
    return {
        **ruleset.to_dict(),
        "warnings": loads(row["warnings"], []) if row else [],
    }


# --- column mapping -------------------------------------------------------

def suggest_mapping(
    header: list[str],
    rules: list[MetricRule],
    sample_rows: list[tuple[int, list[str]]],
    column_map: dict[str, dict[str, Any]] | None = None,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Suggest value/unit columns for each metric. Explicit mapping wins."""
    user_map = dict(column_map or {})
    result: dict[str, dict[str, Any]] = {}
    notes: list[str] = []
    rule_by_key = {rule.key: rule for rule in rules}

    def provided(metric: str) -> dict[str, Any] | None:
        candidate = user_map.get(metric)
        if isinstance(candidate, dict) and candidate.get("value_column"):
            return candidate
        return None

    # direct name match first
    for rule in rules:
        if provided(rule.key):
            continue
        matches = [h for h in header if h == rule.key or h == (rule.label or rule.key)]
        if len(matches) == 1:
            result[rule.key] = {"value_column": matches[0], "unit_column": None, "default_unit": None}
    # then header hints like "重量（kg）"
    for rule in rules:
        if rule.key in result or provided(rule.key):
            continue
        for name in header:
            hint = header_unit_hint(name)
            if hint and normalise_alias(hint) in rule.aliases and name != rule.key:
                result[rule.key] = {"value_column": name, "unit_column": None, "default_unit": None}
                notes.append(f"指标 {rule.key}: 依据表头单位提示选择列 {name!r}")
                break

    # find a unit column used by multiple metrics
    unit_columns = [h for h in header if h.lower() in {"unit", "单位", "units", "uom"}]
    for rule in rules:
        if rule.key in result and not provided(rule.key):
            continue
        if provided(rule.key):
            entry = {
                "value_column": provided(rule.key)["value_column"],
                "unit_column": provided(rule.key).get("unit_column"),
                "default_unit": provided(rule.key).get("default_unit"),
            }
            if entry["unit_column"] not in header:
                raise ValueError(f"指标 {rule.key}: 单位列 {entry['unit_column']!r} 不在表头中")
            if entry["value_column"] not in header:
                raise ValueError(f"指标 {rule.key}: 数值列 {entry['value_column']!r} 不在表头中")
            result[rule.key] = entry
            continue
        if len(unit_columns) == 1:
            result.setdefault(rule.key, {"value_column": None, "unit_column": unit_columns[0], "default_unit": None})
        else:
            result.setdefault(rule.key, {"value_column": None, "unit_column": None, "default_unit": None})

    # pair each metric with a dedicated unit column: 重量单位, 温度单位, ...
    for rule in rules:
        entry = result.get(rule.key) or {}
        if not entry.get("value_column") or entry.get("unit_column"):
            continue
        candidates = [
            h
            for h in header
            if h not in {v.get("value_column") for v in result.values()}
            and (rule.key in h or (rule.label or rule.key) in h)
            and any(word in h.lower() for word in ("unit", "单位", "uom"))
        ]
        if len(candidates) == 1 and not _column_has_units(sample_rows, header, candidates[0], rule):
            # a unit column holds bare aliases, not values with trailing units
            entry["unit_column"] = candidates[0]
            result[rule.key] = entry
            notes.append(f"指标 {rule.key}: 找到独立单位列 {candidates[0]!r}")

    # remaining unmatched columns: infer by sampling alias-looking cells
    unmatched = [h for h in header if h not in {v.get("value_column") for v in result.values()}]
    for rule in rules:
        if rule.key in result and result[rule.key]["value_column"]:
            continue
        for name in unmatched:
            position = header.index(name)
            hits = 0
            samples = 0
            for _, cells in sample_rows[:40]:
                if position >= len(cells):
                    continue
                cell = cells[position].strip()
                if not cell or cell.lower() in {"-", "n/a", "na", "null"}:
                    continue
                samples += 1
                parsed_unit = _trailing_alias(cell, rule)
                if parsed_unit:
                    hits += 1
            if samples and hits / samples >= 0.6:
                existing = result.get(rule.key, {})
                if not existing.get("value_column"):
                    result[rule.key] = {
                        "value_column": name,
                        "unit_column": existing.get("unit_column"),
                        "default_unit": existing.get("default_unit"),
                    }
                    notes.append(f"指标 {rule.key}: 抽样 {hits}/{samples} 个单元格含可识别单位，推断列 {name!r}")
                break

    for rule in rules:
        entry = result.setdefault(
            rule.key, {"value_column": None, "unit_column": None, "default_unit": None}
        )
        if entry.get("default_unit"):
            normalized = normalise_alias(entry["default_unit"])
            if normalized not in rule.aliases:
                raise ValueError(
                    f"指标 {rule.key}: 默认单位 {entry['default_unit']!r} 不在别名表中"
                )
            entry["default_unit"] = normalized
    return result, notes


def _column_has_units(
    rows: list[tuple[int, list[str]]],
    header: list[str],
    column: str,
    rule: MetricRule,
) -> bool:
    position = header.index(column)
    for _, cells in rows[:40]:
        if position >= len(cells):
            continue
        cell = cells[position].strip()
        if not cell:
            continue
        parsed = _trailing_alias(cell, rule)
        if parsed:
            return True
    return False


def _trailing_alias(cell: str, rule: MetricRule) -> str | None:
    import re

    match = re.match(r"^[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\s*(.*)$", cell)
    if not match:
        return None
    tail = normalise_alias(match.group(1))
    if tail and tail in rule.aliases:
        return tail
    if not tail and any(normalise_alias(a) in rule.aliases for a in ["kg"]):
        return None
    return None


def validate_mapping(
    header: list[str], rules: list[MetricRule], mapping: dict[str, Any]
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Validate a column mapping. Metrics with no value column are skipped."""
    if not isinstance(mapping, dict):
        raise ValueError("column_map 必须是对象")
    value_columns: dict[str, str] = {}
    result: dict[str, dict[str, Any]] = {}
    skipped: list[str] = []
    for rule in rules:
        entry = mapping.get(rule.key) or {}
        if not isinstance(entry, dict):
            raise ValueError(f"指标 {rule.key}: 映射必须是对象")
        value_column = entry.get("value_column")
        if not value_column:
            skipped.append(rule.key)
            continue
        if value_column not in header:
            raise ValueError(f"指标 {rule.key}: 数值列 {value_column!r} 不在表头中")
        if value_column in value_columns:
            raise ValueError(
                f"数值列 {value_column!r} 被指标 {value_columns[value_column]} 与 {rule.key} 同时使用"
            )
        value_columns[value_column] = rule.key
        unit_column = entry.get("unit_column") or None
        if unit_column and unit_column not in header:
            raise ValueError(f"指标 {rule.key}: 单位列 {unit_column!r} 不在表头中")
        if unit_column == value_column:
            raise ValueError(f"指标 {rule.key}: 单位列不能与数值列相同")
        default_unit = entry.get("default_unit") or None
        if default_unit:
            normalized = normalise_alias(default_unit)
            if normalized not in rule.aliases:
                raise ValueError(
                    f"指标 {rule.key}: 默认单位 {default_unit!r} 不在指标「{rule.label}」的别名表中"
                )
            default_unit = normalized
        result[rule.key] = {
            "value_column": value_column,
            "unit_column": unit_column,
            "default_unit": default_unit,
        }
    if not result:
        raise ValueError("至少需要为一个指标映射数值列")
    return result, skipped


# --- batches --------------------------------------------------------------


def preview_batch(
    *,
    raw: bytes,
    ruleset: Ruleset,
    mapping: dict[str, Any] | None,
    confirmations: dict[str, Any] | None,
) -> dict[str, Any]:
    parsed = parse_csv(raw)
    if not parsed.rows:
        raise ValueError("CSV 没有数据行（仅表头）")
    suggested, notes = suggest_mapping(parsed.header, ruleset.metrics, parsed.rows[:60], mapping)
    confirmed = parse_confirmations(confirmations)
    validated = None
    error = None
    conflicts: list[dict[str, Any]] = []
    skipped: list[str] = []
    try:
        validated, skipped = validate_mapping(parsed.header, ruleset.metrics, suggested)
        conflicts = preview_unit_conflicts(
            parsed.rows, parsed.header, validated, ruleset.metrics, confirmed
        )
    except ValueError as exc:
        error = str(exc)
    if skipped:
        notes = [
            *notes,
            f"以下指标未映射数值列，本次导入将跳过：{', '.join(skipped)}",
        ]
    sample = [{"row_no": row_no, "cells": cells} for row_no, cells in parsed.rows[:8]]
    return {
        "header": parsed.header,
        "delimiter": parsed.delimiter,
        "encoding": parsed.encoding,
        "row_count": len(parsed.rows),
        "suggested_mapping": suggested,
        "validated_mapping": validated,
        "skipped_metrics": skipped,
        "notes": notes,
        "unit_conflicts": conflicts,
        "confirmations": confirmed,
        "metrics": [m.to_dict() for m in ruleset.metrics],
        "sample_rows": sample,
        "error": error,
    }


def create_batch(
    conn,
    *,
    name: str,
    raw: bytes,
    filename: str,
    ruleset: Ruleset,
    mapping: dict[str, Any],
    confirmations: dict[str, Any] | None,
) -> dict[str, Any]:
    parsed = parse_csv(raw)
    if not parsed.rows:
        raise ValueError("CSV 没有数据行（仅表头）")
    clean_mapping, skipped = validate_mapping(parsed.header, ruleset.metrics, mapping)
    confirmations_parsed = parse_confirmations(confirmations)
    conflicts = preview_unit_conflicts(
        parsed.rows, parsed.header, clean_mapping, ruleset.metrics, confirmations_parsed
    )
    if conflicts:
        raise Conflict(
            "存在待确认的单位别名，请先确认再导入："
            + "；".join(f"{c['alias']} → {', '.join(c['units'])}" for c in conflicts)
        )
    if skipped:
        ruleset = Ruleset(
            id=ruleset.id,
            name=ruleset.name,
            version=ruleset.version,
            metrics=[rule for rule in ruleset.metrics if rule.key in clean_mapping],
        )

    batch_id = uuid.uuid4().hex[:12]
    target_dir = storage_root()
    target_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = target_dir / f"{batch_id}.csv"
    dataset_path.write_bytes(raw)

    header_index = {name: position for position, name in enumerate(parsed.header)}
    rows: list[dict[str, Any]] = []
    counter: dict[str, int] = {category: 0 for category in CATEGORY_LABELS}
    counter["total"] = 0
    counter["rows_ok"] = 0
    counter["rows_exception"] = 0
    by_metric: dict[str, dict[str, int]] = {}
    for row_no, cells in parsed.rows:
        metric_entries: list[dict[str, Any]] = []
        for rule in ruleset.metrics:
            entry = clean_mapping[rule.key]
            value_position = header_index[entry["value_column"]]
            cell = cells[value_position] if value_position < len(cells) else ""
            unit_position = header_index.get(entry.get("unit_column") or "")
            unit_cell = (
                cells[unit_position]
                if unit_position is not None and unit_position < len(cells)
                else None
            )
            unit_cell = unit_cell.strip() if unit_cell else None
            header_hint = header_unit_hint(entry["value_column"])
            metric_entries.append(
                evaluate_cell(
                    cell=cell,
                    unit_text=unit_cell,
                    unit_source="unit_column",
                    rule=rule,
                    confirmations=confirmations_parsed,
                    default_unit=entry.get("default_unit"),
                    header_default=header_hint,
                    row_no=row_no,
                )
            )
        all_ok = all(item["status"] == "ok" for item in metric_entries)
        for item in metric_entries:
            counter[item["category"]] = counter.get(item["category"], 0) + 1
            counter["total"] += 1
            stats = by_metric.setdefault(item["metric"], {"total": 0})
            stats["total"] += 1
            stats[item["category"]] = stats.get(item["category"], 0) + 1
        counter["rows_ok" if all_ok else "rows_exception"] += 1
        rows.append(
            {
                "row_no": row_no,
                "cells": cells,
                "metrics": metric_entries,
                "status": "ok" if all_ok else "exception",
            }
        )

    summary = {
        "row_count": len(parsed.rows),
        "rows_ok": counter["rows_ok"],
        "rows_exception": counter["rows_exception"],
        "cells": {key: counter.get(key, 0) for key in CATEGORY_LABELS},
        "total_cells": counter["total"],
        "by_metric": by_metric,
        "category_labels": CATEGORY_LABELS,
        "category_hints": CATEGORY_HINTS,
        "skipped_metrics": skipped,
        "processed_metrics": [rule.key for rule in ruleset.metrics],
    }

    conn.execute(
        """
        INSERT INTO batches (id, name, ruleset_id, rules_version, rules_snapshot,
            dataset_path, dataset_filename, dataset_hash, dataset_rows, column_map,
            confirmations, status, summary, created_at, note)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            batch_id,
            name,
            ruleset.id,
            ruleset.version,
            json.dumps(ruleset_public(conn, ruleset), ensure_ascii=False),
            str(dataset_path),
            filename,
            file_hash(raw),
            len(parsed.rows),
            json.dumps(clean_mapping, ensure_ascii=False),
            json.dumps(confirmations_parsed, ensure_ascii=False),
            "ready",
            json.dumps(summary, ensure_ascii=False),
            now_iso(),
            None,
        ),
    )
    seq = 0
    for row in rows:
        for item in row["metrics"]:
            seq += 1
            conn.execute(
                "INSERT INTO rows (batch_id, seq, row_no, metric, status, category, payload)"
                " VALUES (?,?,?,?,?,?,?)",
                (
                    batch_id,
                    seq,
                    row["row_no"],
                    item["metric"],
                    item["status"],
                    item["category"],
                    json.dumps(item, ensure_ascii=False),
                ),
            )
    conn.commit()
    return get_batch(conn, batch_id)


def batch_record(conn, batch_id: str):
    row = conn.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
    if row is None:
        raise NotFound(f"批次 {batch_id} 不存在")
    return row


def get_batch(conn, batch_id: str) -> dict[str, Any]:
    row = batch_record(conn, batch_id)
    data = row_to_dict(row)
    data["summary"] = loads(row["summary"], {})
    data["rules_snapshot"] = loads(row["rules_snapshot"], {})
    data["column_map"] = loads(row["column_map"], {})
    data["confirmations"] = loads(row["confirmations"], {})
    data["rules_version"] = row["rules_version"]
    data["dataset_hash_short"] = row["dataset_hash"][:10]
    data.pop("dataset_path", None)
    data["published"] = row["status"] == "published"
    # comparison linkage
    data["comparisons_with"] = [
        item[0]
        for item in conn.execute(
            "SELECT id FROM batches WHERE parent_batch_id = ? ORDER BY created_at",
            (batch_id,),
        ).fetchall()
    ]
    return data


def list_batches(conn) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM batches ORDER BY created_at DESC, id").fetchall()
    items = []
    for row in rows:
        summary = loads(row["summary"], {})
        items.append(
            {
                "id": row["id"],
                "name": row["name"],
                "status": row["status"],
                "rules_version": row["rules_version"],
                "dataset_filename": row["dataset_filename"],
                "dataset_rows": row["dataset_rows"],
                "created_at": row["created_at"],
                "published_at": row["published_at"],
                "parent_batch_id": row["parent_batch_id"],
                "row_count": summary.get("row_count", 0),
                "rows_ok": summary.get("rows_ok", 0),
                "rows_exception": summary.get("rows_exception", 0),
                "cells": summary.get("cells", {}),
            }
        )
    return items


def query_results(
    conn,
    batch_id: str,
    *,
    metric: str | None = None,
    category: str | None = None,
    search: str | None = None,
    row_no: int | None = None,
    precision: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    batch = get_batch(conn, batch_id)
    where = ["batch_id = ?"]
    params: list[Any] = [batch_id]
    if metric:
        where.append("metric = ?")
        params.append(metric)
    if category == "exception":
        where.append("category != 'ok'")
    elif category:
        where.append("category = ?")
        params.append(category)
    if row_no is not None:
        where.append("row_no = ?")
        params.append(row_no)
    clause = " AND ".join(where)
    total = conn.execute(f"SELECT COUNT(*) FROM rows WHERE {clause}", params).fetchone()[0]
    if search:
        # Exact-ish search over raw + formatted payload; done in Python for
        # JSON payloads, with a bounded window.
        matching: list[dict[str, Any]] = []
        for row in conn.execute(
            f"SELECT row_no, metric, status, category, payload FROM rows WHERE {clause}"
            " ORDER BY seq",
            params,
        ):
            payload = loads(row["payload"], {})
            haystack = " ".join(
                str(payload.get(key, ""))
                for key in (
                    "raw_cell", "raw_value_text", "formatted_result", "formula",
                    "exact_result_decimal", "message",
                )
            )
            if search.lower() in haystack.lower():
                matching.append(payload)
        total = len(matching)
        return {
            "batch": batch,
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": matching[offset : offset + limit],
        }
    rows = conn.execute(
        f"SELECT row_no, metric, status, category, payload FROM rows WHERE {clause}"
        " ORDER BY seq LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    items = [loads(row["payload"], {}) for row in rows]
    return {"batch": batch, "total": total, "limit": limit, "offset": offset, "items": items}


def get_row_detail(conn, batch_id: str, row_no: int) -> dict[str, Any]:
    batch = get_batch(conn, batch_id)
    records = conn.execute(
        "SELECT payload FROM rows WHERE batch_id = ? AND row_no = ? ORDER BY seq",
        (batch_id, row_no),
    ).fetchall()
    if not records:
        raise NotFound(f"行号 {row_no} 不在批次 {batch_id} 中")
    dataset = conn.execute(
        "SELECT dataset_path, dataset_filename, column_map FROM batches WHERE id = ?",
        (batch_id,),
    ).fetchone()
    return {
        "batch": batch,
        "row_no": row_no,
        "metrics": [loads(record["payload"], {}) for record in records],
        "raw_line": _raw_line(dataset["dataset_path"], row_no),
        "raw_filename": dataset["dataset_filename"],
        "column_map": loads(dataset["column_map"], {}),
    }


def _raw_line(path: str, row_no: int) -> str | None:
    from pathlib import Path

    file_path = Path(path)
    if not file_path.exists():
        return None
    try:
        with file_path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            for number, line in enumerate(handle, start=1):
                if number == row_no:
                    return line.rstrip("\r\n")
    except OSError:
        return None
    return None


def publish_batch(conn, batch_id: str) -> dict[str, Any]:
    row = batch_record(conn, batch_id)
    if row["status"] == "published":
        return get_batch(conn, batch_id)
    now = now_iso()
    conn.execute(
        "UPDATE batches SET status = 'published', published_at = ? WHERE id = ?",
        (now, batch_id),
    )
    conn.commit()
    return get_batch(conn, batch_id)


def update_note(conn, batch_id: str, note: str | None) -> dict[str, Any]:
    row = batch_record(conn, batch_id)
    if row["status"] == "published":
        raise Conflict("已发布的批次不能修改，请从该批次创建新批次")
    conn.execute("UPDATE batches SET note = ? WHERE id = ?", (note, batch_id))
    conn.commit()
    return get_batch(conn, batch_id)


def create_derived_batch(
    conn,
    *,
    parent_id: str,
    ruleset: Ruleset,
    mapping: dict[str, Any] | None,
    confirmations: dict[str, Any] | None,
    name: str | None,
) -> dict[str, Any]:
    parent = batch_record(conn, parent_id)
    raw = open(parent["dataset_path"], "rb").read()
    merged_mapping = mapping or loads(parent["column_map"], {})
    merged_confirmations = confirmations if confirmations is not None else loads(
        parent["confirmations"], {}
    )
    batch = create_batch(
        conn,
        name=name or f"{parent['name']} · v{ruleset.version}",
        raw=raw,
        filename=parent["dataset_filename"],
        ruleset=ruleset,
        mapping=merged_mapping,
        confirmations=merged_confirmations,
    )
    conn.execute(
        "UPDATE batches SET parent_batch_id = ? WHERE id = ?", (parent_id, batch["id"])
    )
    conn.commit()
    return get_batch(conn, batch["id"])


def compare_batches(conn, left_id: str, right_id: str) -> dict[str, Any]:
    left = batch_record(conn, left_id)
    right = batch_record(conn, right_id)

    def snapshot(batch_id: str) -> dict[tuple[int, str], dict[str, Any]]:
        records = conn.execute(
            "SELECT row_no, metric, payload FROM rows WHERE batch_id = ?",
            (batch_id,),
        ).fetchall()
        return {
            (record["row_no"], record["metric"]): loads(record["payload"], {})
            for record in records
        }

    left_rows = snapshot(left_id)
    right_rows = snapshot(right_id)
    keys = sorted(set(left_rows) | set(right_rows), key=lambda item: (item[0], item[1]))
    changes: list[dict[str, Any]] = []
    for key in keys:
        old = left_rows.get(key)
        new = right_rows.get(key)
        state = _classify_change(old, new)
        if state["category"] != "same":
            changes.append(
                {
                    "row_no": key[0],
                    "metric": key[1],
                    "metric_label": (new or old or {}).get("metric_label", key[1]),
                    "change": state["category"],
                    "old": _brief(old),
                    "new": _brief(new),
                    "detail": state["detail"],
                }
            )
    counts = {"changed": 0, "only_left": 0, "only_right": 0, "moved": 0, "same": 0}
    for change in changes:
        if change["change"] in counts:
            counts[change["change"]] += 1
    changed = [change for change in changes if change["change"] != "same"]
    return {
        "left": {
            "id": left["id"],
            "name": left["name"],
            "rules_version": left["rules_version"],
            "status": left["status"],
            "created_at": left["created_at"],
            "published_at": left["published_at"],
        },
        "right": {
            "id": right["id"],
            "name": right["name"],
            "rules_version": right["rules_version"],
            "status": right["status"],
            "created_at": right["created_at"],
            "published_at": right["published_at"],
        },
        "rows_compared": len(keys),
        "counts": {**counts, "same": len(keys) - len(changed)},
        "changes": changed[:500],
        "changed_total": len(changed),
        "truncated": len(changed) > 500,
        "identical": len(changed) == 0,
    }


def _classify_change(old: dict[str, Any] | None, new: dict[str, Any] | None) -> dict[str, Any]:
    if old is None:
        return {"changed": True, "category": "only_right", "detail": "仅新批次包含该单元格"}
    if new is None:
        return {"changed": True, "category": "only_left", "detail": "仅旧批次包含该单元格"}
    old_key = (old.get("category"), old.get("formatted_result"), old.get("source_unit"))
    new_key = (new.get("category"), new.get("formatted_result"), new.get("source_unit"))
    if old_key == new_key:
        return {"changed": False, "category": "same", "detail": "结果未变"}
    if old.get("category") == "ok" and new.get("category") == "ok":
        if old.get("formatted_result") != new.get("formatted_result"):
            return {
                "changed": True,
                "category": "changed",
                "detail": f"{old.get('formatted_result')} → {new.get('formatted_result')}"
                f"（精度 {old.get('precision')} → {new.get('precision')}）",
            }
        return {"changed": True, "category": "moved", "detail": "来源单位或公式变化"}
    if old.get("category") != new.get("category"):
        return {
            "changed": True,
            "category": "changed",
            "detail": f"{CATEGORY_LABELS.get(old.get('category'), old.get('category'))}"
            f" → {CATEGORY_LABELS.get(new.get('category'), new.get('category'))}",
        }
    if old.get("formatted_result") != new.get("formatted_result"):
        return {
            "changed": True,
            "category": "changed",
            "detail": f"{old.get('formatted_result')} → {new.get('formatted_result')}",
        }
    return {"changed": True, "category": "moved", "detail": "异常原因或来源单位变化"}


def _brief(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    return {
        "raw_cell": payload.get("raw_cell"),
        "raw_unit": payload.get("raw_unit"),
        "source_unit": payload.get("source_unit"),
        "formatted_result": payload.get("formatted_result"),
        "exact_result_decimal": payload.get("exact_result_decimal"),
        "precision": payload.get("precision"),
        "category": payload.get("category"),
        "message": payload.get("message"),
        "formula": payload.get("formula"),
    }


# --- exports --------------------------------------------------------------

DETAIL_HEADERS = [
    ("row_no", "原始行号"),
    ("metric", "指标"),
    ("metric_label", "指标名称"),
    ("raw_value_text", "原始字符串"),
    ("source_unit", "识别来源单位"),
    ("source_unit_display", "来源单位名称"),
    ("target_unit", "目标单位"),
    ("target_unit_display", "目标单位名称"),
    ("formula", "换算公式"),
    ("substitution", "代入过程"),
    ("exact_result_decimal", "精确换算值"),
    ("precision", "输出精度"),
    ("formatted_result", "换算结果"),
    ("rounding_delta", "舍入增量"),
    ("category", "类别"),
    ("category_label", "类别说明"),
    ("message", "说明"),
    ("rules_version", "规则版本"),
]

EXCEPTION_HEADERS = [
    ("row_no", "原始行号"),
    ("metric", "指标"),
    ("metric_label", "指标名称"),
    ("raw_value_text", "原始字符串"),
    ("raw_unit", "原始单位文本"),
    ("category", "异常类型"),
    ("category_label", "异常类别"),
    ("message", "提示"),
    ("suggestion", "处理建议"),
    ("rules_version", "规则版本"),
]


def _target_display(unit_code: str) -> str:
    unit = UNITS.get(unit_code)
    return f"{unit.display}({unit_code})" if unit else unit_code


def build_export(conn, batch_id: str, kind: str) -> tuple[str, str, str]:
    batch = batch_record(conn, batch_id)
    if kind not in {"detail", "exceptions"}:
        raise ValueError("导出类型必须是 detail 或 exceptions")
    records = conn.execute(
        "SELECT payload FROM rows WHERE batch_id = ? ORDER BY seq", (batch_id,)
    ).fetchall()
    payloads = [loads(record["payload"], {}) for record in records]
    if kind == "exceptions":
        payloads = [item for item in payloads if item.get("category") != "ok"]
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    headers = DETAIL_HEADERS if kind == "detail" else EXCEPTION_HEADERS
    writer.writerow([label for _, label in headers])
    version_row = batch["rules_version"]
    for item in payloads:
        row = []
        for key, _label in headers:
            if key == "category_label":
                value = CATEGORY_LABELS.get(item.get("category"), item.get("category", ""))
            elif key == "target_unit_display":
                value = _target_display(item.get("target_unit", ""))
            elif key == "rounding_delta":
                value = (item.get("rounding") or {}).get("delta", "")
            elif key == "suggestion":
                value = CATEGORY_HINTS.get(item.get("category"), "")
            elif key == "rules_version":
                value = version_row
            elif key == "substitution":
                value = item.get("substitution", "")
            else:
                value = item.get(key, "")
                if value is None:
                    value = ""
            row.append(value)
        writer.writerow(row)
    conn.execute(
        "DELETE FROM exports WHERE batch_id = ? AND kind = ?", (batch_id, kind)
    )
    conn.execute(
        "INSERT INTO exports (batch_id, kind, content, created_at) VALUES (?,?,?,?)",
        (batch_id, kind, output.getvalue(), now_iso()),
    )
    conn.commit()
    filename = f"{batch['name']}_{'明细' if kind == 'detail' else '异常清单'}_{batch['id']}.csv"
    return filename, output.getvalue(), batch["status"]
