"""CSV parsing: encoding detection, delimiter detection, physical line tracking."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass


@dataclass
class ParsedCsv:
    header: list[str]
    rows: list[tuple[int, list[str]]]  # (1-based physical line number, cells)
    delimiter: str
    encoding: str
    extra_columns: dict[int, str] | None = None


def _decode(raw: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return raw.decode(encoding), encoding
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8 (按替换解码)"


def _sniff_delimiter(text: str) -> str:
    first_line = ""
    for line in text.splitlines():
        if line.strip():
            first_line = line
            break
    best, best_count = ",", 0
    for candidate in (",", ";", "\t", "|"):
        count = first_line.count(candidate)
        if count > best_count:
            best, best_count = candidate, count
    return best


def parse_csv(raw: bytes) -> ParsedCsv:
    text, encoding = _decode(raw)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        raise ValueError("文件为空")
    delimiter = _sniff_delimiter(text)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    line = 1
    header: list[str] | None = None
    rows: list[tuple[int, list[str]]] = []
    try:
        for record in reader:
            start_line = line
            # csv.reader keeps embedded newlines inside quoted fields.
            line += 1 + sum(field.count("\n") for field in record)
            if header is None:
                header = [cell.strip() for cell in record]
                continue
            if not any(cell.strip() for cell in record):
                continue  # skip blank records, but the line counter already moved
            rows.append((start_line, record))
    except csv.Error as exc:
        raise ValueError(f"CSV 解析失败（第 {line} 行附近）：{exc}") from exc
    if header is None:
        raise ValueError("文件为空")
    if not any(header):
        raise ValueError("CSV 首行表头为空")
    return ParsedCsv(header, rows, delimiter, encoding)
