"""End-to-end API tests against a temporary SQLite database."""

from __future__ import annotations

import csv
import io
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.batches as batches_module
import backend.db as db_module


SAMPLE = """序号,重量,温度,长度,备注
1,1.2kg,21.5C,120cm,ok
2,350g,-5F,1.5m,ok
3,1,2,3,no unit
4,,,,
5,-2.5t,32F,200cm,
6,abc,100C,x,,
7,1kg,100度,1m,ambiguous
8,0.0005kg,-40F,1000mm,low
9,500.5g,0度,,round half
10,2.0005kg,33.3333C,,round half
11,4000000g,0K,1km,big in g
12,1Kg,20C,1m,case alias
"""


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_db = tmp_path / "test.db"
    test_datasets = tmp_path / "datasets"
    monkeypatch.setattr(db_module, "DB_PATH", test_db)
    monkeypatch.setattr(batches_module, "storage_root", lambda: test_datasets)
    from backend.app import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def seeded(client):
    response = client.post("/api/seed/default-rules")
    assert response.status_code == 200
    return response.json()


def _upload(client, path, data, mapping=None, confirmations=None, ruleset_id=None, name="批次"):
    files = {"file": ("sample.csv", data.encode("utf-8"), "text/csv")}
    form = {"name": name}
    if mapping is not None:
        form["mapping"] = json.dumps(mapping, ensure_ascii=False)
    if confirmations is not None:
        form["confirmations"] = json.dumps(confirmations, ensure_ascii=False)
    if ruleset_id is not None:
        form["ruleset_id"] = str(ruleset_id)
    return client.post(path, files=files, data=form)


def test_health(client):
    assert client.get("/api/health").json() == {"ok": True}


def test_units_catalog_lists_dimensions(client):
    body = client.get("/api/units").json()
    keys = [dimension["key"] for dimension in body["dimensions"]]
    assert {"mass", "temperature", "length", "area"} <= set(keys)


def test_seed_and_ruleset_versions(seeded, client):
    assert seeded["version"] == 1
    assert seeded["warnings"] and "度" in seeded["warnings"][0]
    metrics = seeded["metrics"]
    assert any(m["key"] == "重量" and m["target_unit"] == "kg" for m in metrics)
    new_rules = []
    for metric in metrics:
        metric = dict(metric)
        if metric["key"] == "温度":
            metric["precision"] = 0
            metric["target_unit"] = "F"
        new_rules.append(metric)
    created = client.post("/api/rulesets", json={"name": "调整温度", "metrics": new_rules})
    assert created.status_code == 200
    assert created.json()["version"] == 2
    versions = [item["version"] for item in client.get("/api/rulesets").json()["items"]]
    assert versions == [2, 1]


def test_rejects_cross_dimension_alias(client, seeded):
    bad = [dict(m) for m in seeded["metrics"]]
    for metric in bad:
        if metric["key"] == "重量":
            metric["aliases"] = {**metric["aliases"], "米": ["m"]}
    response = client.post("/api/rulesets", json={"name": "坏规则", "metrics": bad})
    assert response.status_code == 422
    assert "维度不同" in response.json()["detail"]["message"]


def test_preview_reports_ambiguous_alias(client, seeded):
    response = _upload(client, "/api/batches/preview", SAMPLE)
    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    conflicts = body["unit_conflicts"]
    assert any(item["alias"] == "度" and item["units"] == ["C", "F"] for item in conflicts)
    assert body["skipped_metrics"] == ["面积"]


def test_create_without_confirmation_is_rejected(client, seeded):
    preview = _upload(client, "/api/batches/preview", SAMPLE).json()
    response = _upload(client, "/api/batches", SAMPLE, mapping=preview["validated_mapping"])
    assert response.status_code == 409
    assert "待确认" in response.json()["detail"]["message"]


def test_create_with_confirmation_and_exception_categories(client, seeded):
    preview = _upload(client, "/api/batches/preview", SAMPLE).json()
    response = _upload(
        client,
        "/api/batches",
        SAMPLE,
        mapping=preview["validated_mapping"],
        confirmations={"温度:度": "C"},
    )
    assert response.status_code == 200
    batch = response.json()
    cells = batch["summary"]["cells"]
    assert cells["ambiguous_unit"] == 0
    assert cells["parse_error"] == 2
    assert cells["unknown_unit"] == 4  # row 4 all three + row 12 "Kg"
    assert cells["empty"] >= 1
    assert cells["out_of_range"] == 3  # -2.5t, 0.0005kg, 0K
    detail = client.get(f"/api/batches/{batch['id']}/results?limit=100").json()
    by_row = {(item["row_no"], item["metric"]): item for item in detail["items"]}
    # g -> kg
    assert by_row[(2, "重量")]["formatted_result"] == "1.200"
    # F -> C exact repeating, rounded to 1 dp (-5 F = -20.6 C)
    assert by_row[(3, "温度")]["formatted_result"] == "-20.6"
    # rounding half-up (500.5 g on physical line 10)
    assert by_row[(10, "重量")]["rounding"]["half_tie"] is True
    # range checked on converted target unit: 4000000 g = 4000 kg -> ok
    assert by_row[(12, "重量")]["category"] == "ok"
    assert by_row[(12, "重量")]["formatted_result"] == "4000.000"
    # 0K = -273.15C -> below -60
    assert by_row[(12, "温度")]["category"] == "out_of_range"
    # case-sensitive alias
    assert by_row[(13, "重量")]["category"] == "unknown_unit"
    # out-of-range rows: -2.5t (line 6), 0.0005kg (line 9), 0K (line 12)
    assert by_row[(6, "重量")]["category"] == "out_of_range"
    assert by_row[(9, "重量")]["category"] == "out_of_range"


def test_row_detail_explains_steps(client, seeded):
    preview = _upload(client, "/api/batches/preview", SAMPLE).json()
    batch = _upload(
        client, "/api/batches", SAMPLE,
        mapping=preview["validated_mapping"],
        confirmations={"温度:度": "C"},
    ).json()
    detail = client.get(f"/api/batches/{batch['id']}/rows/3").json()
    assert detail["row_no"] == 3
    assert detail["raw_line"].startswith("2,350g")
    weight = next(item for item in detail["metrics"] if item["metric"] == "重量")
    steps = {step["step"]: step for step in weight["trace"]}
    assert "换算公式" in steps and "舍入输出" in steps
    assert weight["recognized"]["source"] == "in_cell"
    assert weight["formula"] == "y = 1/1000 · x"
    assert weight["rounding"]["detail"]
    assert weight["raw_cell"] == "350g"


def test_exports_carry_source_line_numbers(client, seeded):
    preview = _upload(client, "/api/batches/preview", SAMPLE).json()
    batch = _upload(
        client, "/api/batches", SAMPLE,
        mapping=preview["validated_mapping"],
        confirmations={"温度:度": "C"},
    ).json()
    detail = client.get(f"/api/batches/{batch['id']}/export/detail")
    assert detail.status_code == 200
    reader = list(csv.reader(io.StringIO(detail.text.lstrip("﻿"))))
    header = reader[0]
    assert header[0] == "原始行号"
    assert "换算公式" in header
    assert "规则版本" in header
    row_numbers = {int(row[0]) for row in reader[1:]}
    assert row_numbers == set(range(2, 14))
    exceptions = client.get(f"/api/batches/{batch['id']}/export/exceptions")
    assert exceptions.status_code == 200
    reader = list(csv.reader(io.StringIO(exceptions.text.lstrip("﻿"))))
    assert reader[0][0] == "原始行号"
    assert all(row[0] != "2" for row in reader[1:])  # row 2 (1.2kg/21.5C/120cm) was OK


def test_recompute_creates_new_batch_and_preserves_published(client, seeded):
    preview = _upload(client, "/api/batches/preview", SAMPLE).json()
    batch = _upload(
        client, "/api/batches", SAMPLE,
        mapping=preview["validated_mapping"],
        confirmations={"温度:度": "C"},
        name="原始批次",
    ).json()
    # publish the first batch
    published = client.post(f"/api/batches/{batch['id']}/publish").json()
    assert published["status"] == "published"
    assert published["published_at"]
    frozen = client.get(f"/api/batches/{batch['id']}/results?limit=3").json()
    # new ruleset: temperature to F with 0 dp, weight precision 1
    rules = [dict(m) for m in seeded["metrics"]]
    for metric in rules:
        if metric["key"] == "温度":
            metric["target_unit"] = "F"
            metric["precision"] = 0
        if metric["key"] == "重量":
            metric["precision"] = 1
    new_rules = client.post("/api/rulesets", json={"name": "新规则", "metrics": rules}).json()
    # recompute endpoint expects only ruleset_id via form, not a file
    response = client.post(
        f"/api/batches/{batch['id']}/recompute",
        data={"ruleset_id": str(new_rules["id"]), "name": "规则调整批次"},
    )
    assert response.status_code == 200
    derived = response.json()
    assert derived["parent_batch_id"] == batch["id"]
    assert derived["rules_version"] == new_rules["version"]
    again = client.get(f"/api/batches/{batch['id']}/results?limit=3").json()
    assert again["items"] == frozen["items"]
    compare = client.get(f"/api/batches/{batch['id']}/compare/{derived['id']}").json()
    assert compare["rows_compared"] > 0
    assert compare["changed_total"] > 0
    change = next(c for c in compare["changes"] if c["metric"] == "温度" and c["row_no"] == 2)
    assert change["old"]["formatted_result"] == "21.5"
    assert change["new"]["formatted_result"] == "71"
    change2 = next(c for c in compare["changes"] if c["metric"] == "温度" and c["row_no"] == 3)
    assert change2["old"]["formatted_result"] == "-20.6"
    assert change2["new"]["formatted_result"] == "-5"


UNIT_COLUMN_SAMPLE = """样品编号,重量,重量单位,温度,温度单位,备注
A-01,1250,g,18,F,冷冻样品
A-02,0.85,kg,21.5,C,常温
A-03,2.5,kg,-3.2,C,冷藏
A-04,,kg,,C,缺失值
A-05,abc,g,99,C,重量解析失败
A-06,12,度,30,C,重量单位不明
A-07,1000,mg,310,K,毫克与开尔文
"""


def test_separate_unit_columns_are_detected_and_used(client, seeded):
    files = {"file": ("units.csv", UNIT_COLUMN_SAMPLE.encode("utf-8"), "text/csv")}
    preview = client.post("/api/batches/preview", files=files).json()
    # no in-cell units: the unit column must be paired automatically
    assert preview["validated_mapping"]["重量"]["unit_column"] == "重量单位"
    assert preview["validated_mapping"]["温度"]["unit_column"] == "温度单位"
    assert preview["skipped_metrics"] == ["长度", "面积"]
    # "度" in the weight unit column is unknown there, not ambiguous
    assert preview["unit_conflicts"] == []

    files = {"file": ("units.csv", UNIT_COLUMN_SAMPLE.encode("utf-8"), "text/csv")}
    batch = client.post(
        "/api/batches",
        files=files,
        data={
            "name": "单位列批次",
            "mapping": json.dumps(preview["validated_mapping"], ensure_ascii=False),
        },
    )
    assert batch.status_code == 200
    body = batch.json()
    assert body["summary"]["processed_metrics"] == ["重量", "温度"]
    items = client.get(f"/api/batches/{body['id']}/results?limit=100").json()["items"]
    by_row = {(item["row_no"], item["metric"]): item for item in items}
    # 1250 g, unit taken from the separate column
    assert by_row[(2, "重量")]["recognized"]["source"] == "unit_column"
    assert by_row[(2, "重量")]["recognized"]["alias"] == "g"
    assert by_row[(2, "重量")]["formatted_result"] == "1.250"
    # 18 F -> -7.777… C, 1 dp (default rules) -> -7.8
    assert by_row[(2, "温度")]["formatted_result"] == "-7.8"
    # 310 K -> 36.85 C lands exactly on the half at 1 dp -> 36.9 (half away from zero)
    assert by_row[(8, "温度")]["formatted_result"] == "36.9"
    assert by_row[(8, "温度")]["rounding"]["half_tie"] is True
    # unit column "度" is unknown for weight; temperature side is fine
    assert by_row[(7, "重量")]["category"] == "unknown_unit"
    assert by_row[(7, "温度")]["category"] == "ok"
    # empty value with a unit still counts as empty, not parse error
    assert by_row[(5, "重量")]["category"] == "empty"
    assert by_row[(6, "重量")]["category"] == "parse_error"


def test_compare_is_read_only_and_reports_identical_batches(client, seeded):
    preview = _upload(client, "/api/batches/preview", SAMPLE).json()
    mapping = preview["validated_mapping"]
    confirmations = {"温度:度": "C"}
    first = _upload(
        client, "/api/batches", SAMPLE,
        mapping=mapping, confirmations=confirmations, name="A",
    ).json()
    second = _upload(
        client, "/api/batches", SAMPLE,
        mapping=mapping, confirmations=confirmations, name="B",
    ).json()
    compare = client.get(f"/api/batches/{first['id']}/compare/{second['id']}").json()
    assert compare["identical"] is True
    assert compare["changed_total"] == 0
    assert compare["rows_compared"] == 36
    # comparing must not mutate either batch
    assert client.get(f"/api/batches/{first['id']}").json()["status"] == "ready"
    assert client.get(f"/api/batches/{second['id']}").json()["status"] == "ready"


def test_published_batch_snapshot_stays_fixed_after_new_version(client, seeded):
    preview = _upload(client, "/api/batches/preview", SAMPLE).json()
    batch = _upload(
        client, "/api/batches", SAMPLE,
        mapping=preview["validated_mapping"],
        confirmations={"温度:度": "C"},
        name="冻结批次",
    ).json()
    client.post(f"/api/batches/{batch['id']}/publish")
    frozen = client.get(f"/api/batches/{batch['id']}").json()
    frozen_rows = client.get(f"/api/batches/{batch['id']}/results?limit=100").json()["items"]
    frozen_detail = client.get(f"/api/batches/{batch['id']}/export/detail").text

    rules = [dict(m) for m in seeded["metrics"]]
    for metric in rules:
        if metric["key"] == "重量":
            metric["precision"] = 0
    client.post("/api/rulesets", json={"name": "新版本", "metrics": rules})

    after = client.get(f"/api/batches/{batch['id']}").json()
    assert after["rules_snapshot"] == frozen["rules_snapshot"]
    assert after["rules_version"] == frozen["rules_version"]
    assert client.get(f"/api/batches/{batch['id']}/results?limit=100").json()["items"] == frozen_rows
    assert client.get(f"/api/batches/{batch['id']}/export/detail").text == frozen_detail
