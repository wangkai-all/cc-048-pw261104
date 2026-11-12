"""FastAPI application. Thin HTTP layer over batches/rules services."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from . import batches, rules as rules_module
from .db import session
from .rules import RuleError
from .units import DIMENSIONS, UNITS

BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "data" / "datasets"
STATIC_DIR = BASE_DIR / "frontend" / "dist"

app = FastAPI(title="单位换算与校验", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class RulesetIn(BaseModel):
    name: str = "默认规则"
    metrics: list[dict[str, Any]]


class PublishIn(BaseModel):
    note: str | None = None


def _error(status: int, message: str, **extra):
    raise HTTPException(status_code=status, detail={"message": message, **extra})


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/units")
def list_units():
    return {
        "dimensions": [
            {
                "key": key,
                "label": label,
                "units": [
                    {"code": code, "display": unit.display}
                    for code, unit in UNITS.items()
                    if unit.dimension == key
                ],
            }
            for key, label in DIMENSIONS.items()
        ],
        "dimension_labels": DIMENSIONS,
    }


@app.get("/api/rulesets")
def list_rulesets():
    with session() as conn:
        rows = conn.execute("SELECT * FROM rulesets ORDER BY version DESC").fetchall()
        items = []
        for row in rows:
            items.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "version": row["version"],
                    "created_at": row["created_at"],
                    "metrics": json.loads(row["metrics"]),
                    "warnings": json.loads(row["warnings"] or "[]"),
                    "batches": conn.execute(
                        "SELECT COUNT(*) FROM batches WHERE ruleset_id = ?", (row["id"],)
                    ).fetchone()[0],
                }
            )
        return {"items": items}


@app.get("/api/rulesets/latest")
def get_latest_ruleset():
    with session() as conn:
        ruleset = batches.latest_ruleset(conn)
        if ruleset is None:
            _error(404, "尚无规则集，请先保存默认规则")
        return batches.ruleset_public(conn, ruleset)


@app.get("/api/rulesets/{ruleset_id}")
def get_ruleset(ruleset_id: int):
    with session() as conn:
        try:
            ruleset = batches.get_ruleset(conn, ruleset_id)
        except batches.NotFound as exc:
            _error(404, str(exc))
        return batches.ruleset_public(conn, ruleset)


@app.post("/api/rulesets")
def create_ruleset(payload: RulesetIn):
    try:
        metrics, warnings = rules_module.validate_ruleset(payload.metrics)
    except RuleError as exc:
        _error(422, str(exc))
    with session() as conn:
        ruleset = batches.save_ruleset(conn, payload.name.strip() or "默认规则", metrics, warnings)
        return batches.ruleset_public(conn, ruleset)


@app.post("/api/seed/default-rules")
def seed_default_rules():
    with session() as conn:
        existing = batches.latest_ruleset(conn)
        if existing is not None:
            return batches.ruleset_public(conn, existing)
        try:
            metrics, warnings = rules_module.validate_ruleset(rules_module.DEFAULT_METRICS)
        except RuleError as exc:
            _error(422, str(exc))
        ruleset = batches.save_ruleset(conn, "默认计量规则", metrics, warnings)
        return batches.ruleset_public(conn, ruleset)


@app.post("/api/batches/preview")
async def preview_batch(
    file: UploadFile = File(...),
    mapping: str | None = Form(None),
    confirmations: str | None = Form(None),
):
    raw = await file.read()
    if not raw:
        _error(422, "上传文件为空")
    try:
        mapping_parsed = json.loads(mapping) if mapping else None
        confirmations_parsed = json.loads(confirmations) if confirmations else None
    except json.JSONDecodeError:
        _error(422, "mapping/confirmations 不是合法 JSON")
    with session() as conn:
        ruleset = batches.latest_ruleset(conn)
        if ruleset is None:
            _error(409, "尚无规则集，请先在规则页保存规则")
    try:
        return batches.preview_batch(
            raw=raw,
            ruleset=ruleset,
            mapping=mapping_parsed,
            confirmations=confirmations_parsed,
        )
    except ValueError as exc:
        _error(422, str(exc))


@app.post("/api/batches")
async def create_batch(
    file: UploadFile = File(...),
    name: str = Form("导入批次"),
    ruleset_id: int | None = Form(None),
    mapping: str = Form(...),
    confirmations: str | None = Form(None),
):
    raw = await file.read()
    if not raw:
        _error(422, "上传文件为空")
    try:
        mapping_parsed = json.loads(mapping)
        confirmations_parsed = json.loads(confirmations) if confirmations else None
    except json.JSONDecodeError:
        _error(422, "mapping/confirmations 不是合法 JSON")
    with session() as conn:
        ruleset = batches.get_ruleset(conn, ruleset_id) if ruleset_id else batches.latest_ruleset(conn)
        if ruleset is None:
            _error(409, "尚无规则集，请先在规则页保存规则")
        try:
            batch = batches.create_batch(
                conn,
                name=name.strip() or "导入批次",
                raw=raw,
                filename=file.filename or "upload.csv",
                ruleset=ruleset,
                mapping=mapping_parsed,
                confirmations=confirmations_parsed,
            )
        except batches.Conflict as exc:
            _error(409, str(exc))
        except ValueError as exc:
            _error(422, str(exc))
    return batch


@app.get("/api/batches")
def list_batches():
    with session() as conn:
        return {"items": batches.list_batches(conn)}


@app.get("/api/batches/{batch_id}")
def get_batch(batch_id: str):
    with session() as conn:
        try:
            return batches.get_batch(conn, batch_id)
        except batches.NotFound as exc:
            _error(404, str(exc))


@app.get("/api/batches/{batch_id}/results")
def batch_results(
    batch_id: str,
    metric: str | None = None,
    category: str | None = None,
    search: str | None = None,
    row_no: int | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    with session() as conn:
        try:
            return batches.query_results(
                conn,
                batch_id,
                metric=metric,
                category=category,
                search=search,
                row_no=row_no,
                limit=limit,
                offset=offset,
            )
        except batches.NotFound as exc:
            _error(404, str(exc))


@app.get("/api/batches/{batch_id}/rows/{row_no}")
def row_detail(batch_id: str, row_no: int):
    with session() as conn:
        try:
            return batches.get_row_detail(conn, batch_id, row_no)
        except batches.NotFound as exc:
            _error(404, str(exc))


@app.post("/api/batches/{batch_id}/publish")
def publish_batch(batch_id: str, payload: PublishIn | None = None):
    with session() as conn:
        try:
            return batches.publish_batch(conn, batch_id)
        except batches.NotFound as exc:
            _error(404, str(exc))


@app.post("/api/batches/{batch_id}/recompute")
async def recompute_batch(
    batch_id: str,
    ruleset_id: int = Form(...),
    name: str | None = Form(None),
):
    with session() as conn:
        try:
            parent = batches.batch_record(conn, batch_id)
            ruleset = batches.get_ruleset(conn, ruleset_id)
        except batches.NotFound as exc:
            _error(404, str(exc))
        try:
            batch = batches.create_derived_batch(
                conn,
                parent_id=batch_id,
                ruleset=ruleset,
                mapping=None,
                confirmations=None,
                name=name,
            )
        except batches.Conflict as exc:
            _error(409, str(exc))
        except ValueError as exc:
            _error(422, str(exc))
    return {
        **batch,
        "parent": {
            "id": parent["id"],
            "name": parent["name"],
            "rules_version": parent["rules_version"],
            "status": parent["status"],
            "published_at": parent["published_at"],
        },
    }


@app.get("/api/batches/{batch_id}/compare/{other_id}")
def compare_batches(batch_id: str, other_id: str):
    with session() as conn:
        try:
            return batches.compare_batches(conn, batch_id, other_id)
        except batches.NotFound as exc:
            _error(404, str(exc))


@app.get("/api/batches/{batch_id}/export/{kind}")
def export_batch(batch_id: str, kind: str):
    with session() as conn:
        try:
            filename, content, status_value = batches.build_export(conn, batch_id, kind)
        except batches.NotFound as exc:
            _error(404, str(exc))
        except ValueError as exc:
            _error(422, str(exc))
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        "X-Batch-Status": status_value,
    }
    return Response(
        content=content.encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers=headers,
    )


if STATIC_DIR.exists():

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/{path:path}")
    def static_files(path: str):
        candidate = (STATIC_DIR / path).resolve()
        if candidate.is_file() and str(candidate).startswith(str(STATIC_DIR.resolve())):
            return FileResponse(candidate)
        return FileResponse(STATIC_DIR / "index.html")
