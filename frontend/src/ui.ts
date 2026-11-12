import type { ResultRow } from "./types";

export const CATEGORY_STYLES: Record<
  string,
  { className: string; color: string; label: string }
> = {
  ok: { className: "chip-good", color: "var(--good)", label: "正常" },
  empty: { className: "chip-empty", color: "var(--ink-3)", label: "空值" },
  parse_error: { className: "chip-warn", color: "var(--warn)", label: "解析失败" },
  unknown_unit: { className: "chip-serious", color: "var(--serious)", label: "单位不明" },
  ambiguous_unit: { className: "chip-info", color: "var(--info)", label: "单位待确认" },
  dimension_mismatch: {
    className: "chip-critical",
    color: "var(--critical)",
    label: "维度不匹配",
  },
  out_of_range: { className: "chip-critical", color: "var(--critical)", label: "超出范围" },
};

export function categoryStyle(category: string) {
  return (
    CATEGORY_STYLES[category] ?? {
      className: "chip-outline",
      color: "var(--ink-3)",
      label: category,
    }
  );
}

export const CATEGORY_ORDER = [
  "ok",
  "empty",
  "parse_error",
  "unknown_unit",
  "ambiguous_unit",
  "dimension_mismatch",
  "out_of_range",
];

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso ?? "—";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`;
}

export function signedDelta(row: ResultRow): string {
  const delta = row.rounding?.delta;
  if (!delta || delta === "0") return "0";
  return delta.startsWith("-") ? delta : `+${delta}`;
}

export function describeSource(source: string | null | undefined): string {
  switch (source) {
    case "in_cell":
      return "单元格内";
    case "unit_column":
      return "单位列";
    case "column_default":
      return "列默认单位";
    case "header_default":
      return "表头提示";
    default:
      return source ?? "—";
  }
}

export function statusLabel(status: string | null | undefined): string {
  switch (status) {
    case "published":
      return "已发布";
    case "ready":
      return "工作副本";
    default:
      return status ?? "—";
  }
}
