export interface RuleMetric {
  key: string;
  label: string;
  target_unit: string;
  precision: number;
  min_value: string | null;
  max_value: string | null;
  aliases: Record<string, string[]>;
  accepted_units: string[];
}

export interface Ruleset {
  id: number;
  name: string;
  version: number;
  metrics: RuleMetric[];
  warnings: string[];
  created_at?: string;
  batches?: number;
}

export interface UnitInfo {
  code: string;
  display: string;
}

export interface DimensionInfo {
  key: string;
  label: string;
  units: UnitInfo[];
}

export interface BatchSummary {
  row_count: number;
  rows_ok: number;
  rows_exception: number;
  cells: Record<string, number>;
  total_cells: number;
  by_metric: Record<string, Record<string, number>>;
  category_labels: Record<string, string>;
  category_hints: Record<string, string>;
  skipped_metrics?: string[];
  processed_metrics?: string[];
}

export interface Batch {
  id: string;
  name: string;
  status: "ready" | "published" | string;
  rules_version: number;
  rules_snapshot: Ruleset;
  dataset_filename: string;
  dataset_hash_short: string;
  dataset_rows: number;
  column_map: Record<
    string,
    { value_column: string; unit_column: string | null; default_unit: string | null }
  >;
  confirmations: Record<string, string>;
  summary: BatchSummary;
  created_at: string;
  published_at: string | null;
  parent_batch_id: string | null;
  comparisons_with: string[];
}

export interface BatchListItem {
  id: string;
  name: string;
  status: string;
  rules_version: number;
  dataset_filename: string;
  dataset_rows: number;
  created_at: string;
  published_at: string | null;
  parent_batch_id: string | null;
  row_count: number;
  rows_ok: number;
  rows_exception: number;
  cells: Record<string, number>;
}

export interface Recognized {
  code: string | null;
  source: string | null;
  alias: string | null;
  matches: string[];
  via: string | null;
  issue: string | null;
  message: string;
}

export interface TraceStep {
  step: string;
  detail: string;
  ok: boolean;
}

export interface RoundingInfo {
  precision: number;
  exact_value: string;
  exact_fraction: string;
  rounded_value: string;
  formatted: string;
  delta: string;
  delta_decimal: string;
  changed: boolean;
  half_tie: boolean;
  unit: string;
  method: string;
  detail: string;
}

export interface ResultRow {
  row_no: number;
  metric: string;
  metric_label: string;
  target_unit: string;
  precision: number;
  raw_cell: string;
  raw_unit: string | null;
  raw_value?: string;
  raw_value_text?: string;
  status: "ok" | "exception";
  category: string;
  message: string;
  recognized: Recognized | null;
  source_unit?: string;
  source_unit_display?: string;
  source_value?: string;
  source_value_decimal?: string;
  formula?: string;
  substitution?: string;
  exact_result?: string;
  exact_result_decimal?: string;
  rounded_result?: string;
  formatted_result?: string;
  rounding?: RoundingInfo;
  range?: {
    min: string | null;
    max: string | null;
    unit: string;
    basis: string;
    passed: boolean | null;
    message: string;
  };
  trace: TraceStep[];
}

export interface ResultsResponse {
  batch: Batch;
  total: number;
  limit: number;
  offset: number;
  items: ResultRow[];
}

export interface RowDetail {
  batch: Batch;
  row_no: number;
  metrics: ResultRow[];
  raw_line: string | null;
  raw_filename: string;
  column_map: Record<string, unknown>;
}

export interface UnitConflict {
  metric: string;
  metric_label: string;
  alias: string;
  raw_alias: string;
  units: string[];
  count: number;
  examples: { row_no: number; cell: string; unit_cell: string | null }[];
}

export interface PreviewResult {
  header: string[];
  delimiter: string;
  encoding: string;
  row_count: number;
  suggested_mapping: Record<string, { value_column: string | null; unit_column: string | null; default_unit: string | null }>;
  validated_mapping: Record<string, { value_column: string; unit_column: string | null; default_unit: string | null }> | null;
  skipped_metrics: string[];
  notes: string[];
  unit_conflicts: UnitConflict[];
  confirmations: Record<string, string>;
  metrics: RuleMetric[];
  sample_rows: { row_no: number; cells: string[] }[];
  error: string | null;
}

export interface CompareChange {
  row_no: number;
  metric: string;
  metric_label: string;
  change: string;
  old: {
    raw_cell: string;
    source_unit: string | null;
    formatted_result: string | null;
    category: string;
    message: string;
    formula: string;
  } | null;
  new: {
    raw_cell: string;
    source_unit: string | null;
    formatted_result: string | null;
    category: string;
    message: string;
    formula: string;
  } | null;
  detail: string;
}

export interface CompareResult {
  left: { id: string; name: string; rules_version: number; status: string; created_at: string; published_at: string | null };
  right: { id: string; name: string; rules_version: number; status: string; created_at: string; published_at: string | null };
  rows_compared: number;
  counts: Record<string, number>;
  changes: CompareChange[];
  changed_total: number;
  truncated: boolean;
  identical: boolean;
}
