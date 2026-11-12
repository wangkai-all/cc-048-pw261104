import type { PreviewResult, UnitConflict, RuleMetric } from "./types";
import { Icon } from "./Icon";
import { Notice } from "./Feedback";

export function MappingEditor({
  header,
  preview,
  mapping,
  onChange,
}: {
  header: string[];
  preview: PreviewResult;
  mapping: Record<string, { value_column: string; unit_column: string | null; default_unit: string | null }>;
  onChange: (next: typeof mapping) => void;
}) {
  const metrics = preview.metrics;
  return (
    <div>
      <table className="map-table">
        <thead>
          <tr>
            <th style={{ width: "26%" }}>指标</th>
            <th>数值列</th>
            <th>单位列（可选）</th>
            <th>列默认单位（可选）</th>
          </tr>
        </thead>
        <tbody>
          {metrics.map((metric: RuleMetric) => {
            const entry = mapping[metric.key] ?? {
              value_column: "",
              unit_column: null,
              default_unit: null,
            };
            const aliases = Object.keys(metric.aliases);
            return (
              <tr key={metric.key}>
                <td>
                  <div style={{ fontWeight: 600 }}>{metric.label}</div>
                  <div className="muted" style={{ fontSize: 11 }}>
                    目标 {metric.target_unit} · {metric.precision} 位小数
                  </div>
                </td>
                <td>
                  <select
                    className="select"
                    value={entry.value_column}
                    onChange={(event) =>
                      onChange({
                        ...mapping,
                        [metric.key]: { ...entry, value_column: event.target.value },
                      })
                    }
                  >
                    <option value="">— 跳过此指标 —</option>
                    {header.map((name) => (
                      <option key={name} value={name}>
                        {name}
                      </option>
                    ))}
                  </select>
                </td>
                <td>
                  <select
                    className="select"
                    value={entry.unit_column ?? ""}
                    disabled={!entry.value_column}
                    onChange={(event) =>
                      onChange({
                        ...mapping,
                        [metric.key]: { ...entry, unit_column: event.target.value || null },
                      })
                    }
                  >
                    <option value="">— 无 —</option>
                    {header.map((name) => (
                      <option key={name} value={name}>
                        {name}
                      </option>
                    ))}
                  </select>
                </td>
                <td>
                  <select
                    className="select"
                    value={entry.default_unit ?? ""}
                    disabled={!entry.value_column}
                    onChange={(event) =>
                      onChange({
                        ...mapping,
                        [metric.key]: { ...entry, default_unit: event.target.value || null },
                      })
                    }
                  >
                    <option value="">— 无 —</option>
                    {aliases.slice(0, 60).map((alias) => (
                      <option key={alias} value={alias}>
                        {alias}
                      </option>
                    ))}
                  </select>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function SampleTable({
  preview,
  mapping,
}: {
  preview: PreviewResult;
  mapping: Record<string, { value_column: string; unit_column: string | null; default_unit: string | null }>;
}) {
  const highlighted = new Set(
    Object.values(mapping)
      .filter((entry) => entry.value_column)
      .map((entry) => entry.value_column),
  );
  return (
    <div className="sample-wrap">
      <table className="sample-table">
        <thead>
          <tr>
            <th className="ln">行号</th>
            {preview.header.map((name) => (
              <th key={name} style={highlighted.has(name) ? { color: "var(--accent)" } : undefined}>
                {name}
                {highlighted.has(name) ? " ·" : ""}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {preview.sample_rows.map((row) => (
            <tr key={row.row_no}>
              <td className="ln">{row.row_no}</td>
              {preview.header.map((_, index) => (
                <td key={index}>{row.cells[index] ?? ""}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ConflictPanel({
  conflicts,
  confirmations,
  onChange,
  unitLabels,
}: {
  conflicts: UnitConflict[];
  confirmations: Record<string, string>;
  onChange: (next: Record<string, string>) => void;
  unitLabels: Record<string, string>;
}) {
  if (!conflicts.length) return null;
  const unresolved = conflicts.filter(
    (conflict) => !confirmations[`${conflict.metric}:${conflict.alias}`],
  );
  return (
    <div className="stack">
      {conflicts.map((conflict) => {
        const key = `${conflict.metric}:${conflict.alias}`;
        const chosen = confirmations[key];
        return (
          <div className="conflict" key={key}>
            <div className="conflict-head">
              <Icon name="alert" size={15} />
              指标「{conflict.metric_label}」的别名「{conflict.alias}」指向多个单位
              <span className="muted" style={{ fontWeight: 500, marginLeft: "auto", fontSize: 11.5 }}>
                {conflict.count} 处待确认
              </span>
            </div>
            <div className="conflict-body">
              一个别名同时出现在 {conflict.units.length} 个单位下，系统不会自动选择，请指定本次导入的含义。
              示例：{conflict.examples.map((example) => `第 ${example.row_no} 行「${example.cell || example.unit_cell}」`).join("、")}
            </div>
            <div className="alias-options">
              {conflict.units.map((unit) => (
                <button
                  key={unit}
                  type="button"
                  className={`option ${chosen === unit ? "selected" : ""}`}
                  onClick={() =>
                    onChange({
                      ...confirmations,
                      [key]: unit,
                    })
                  }
                >
                  <b>{unit}</b>
                  <span>{unitLabels[unit] ?? "已注册单位"}</span>
                </button>
              ))}
            </div>
          </div>
        );
      })}
      {unresolved.length ? (
        <Notice tone="warn" icon="alert">
          还有 {unresolved.length} 个别名未确认，确认后才能生成批次。
        </Notice>
      ) : null}
    </div>
  );
}
