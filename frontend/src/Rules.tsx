import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { Icon } from "./Icon";
import { Loading, Notice } from "./Feedback";
import type { RuleMetric, Ruleset, DimensionInfo } from "./types";

type DraftMetric = RuleMetric & { _expanded?: boolean };

export function RulesPage() {
  const [rulesets, setRulesets] = useState<Ruleset[] | null>(null);
  const [latest, setLatest] = useState<Ruleset | null>(null);
  const [dimensions, setDimensions] = useState<DimensionInfo[]>([]);
  const [drafts, setDrafts] = useState<DraftMetric[]>([]);
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  const load = async () => {
    setError(null);
    try {
      const [list, units] = await Promise.all([
        api.get<{ items: Ruleset[] }>("/api/rulesets"),
        api.get<{ dimensions: DimensionInfo[] }>("/api/units"),
      ]);
      setRulesets(list.items);
      setDimensions(units.dimensions);
      const current = list.items[0] ?? null;
      setLatest(current);
      if (current) {
        setDrafts(current.metrics.map((metric) => ({ ...metric, aliases: { ...metric.aliases } })));
        setName(current.name);
      } else {
        // first run: pull the seeded defaults
        try {
          const seeded = await api.post<Ruleset>("/api/seed/default-rules");
          setLatest(seeded);
          setDrafts(seeded.metrics.map((metric) => ({ ...metric, aliases: { ...metric.aliases } })));
          setName(seeded.name);
          const list2 = await api.get<{ items: Ruleset[] }>("/api/rulesets");
          setRulesets(list2.items);
        } catch {
          /* noop */
        }
      }
    } catch (err) {
      setError((err as Error).message);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const unitMeta = useMemo(() => {
    const map: Record<string, { display: string; dimension: string; dimensionLabel: string }> = {};
    for (const dimension of dimensions) {
      for (const unit of dimension.units) {
        map[unit.code] = {
          display: unit.display,
          dimension: dimension.key,
          dimensionLabel: dimension.label,
        };
      }
    }
    return map;
  }, [dimensions]);

  const update = (index: number, patch: Partial<RuleMetric>) => {
    setDrafts((current) =>
      current.map((metric, position) => (position === index ? { ...metric, ...patch } : metric)),
    );
  };

  const removeAlias = (index: number, alias: string) => {
    setDrafts((current) =>
      current.map((metric, position) => {
        if (position !== index) return metric;
        const next = { ...metric.aliases };
        delete next[alias];
        return { ...metric, aliases: next };
      }),
    );
  };

  const addAlias = (index: number, alias: string, units: string[]) => {
    if (!alias.trim() || units.length === 0) return;
    setDrafts((current) =>
      current.map((metric, position) => {
        if (position !== index) return metric;
        return { ...metric, aliases: { ...metric.aliases, [alias.trim()]: units } };
      }),
    );
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const payload = {
        name: name || "计量规则",
        metrics: drafts.map((metric) => ({
          key: metric.key,
          label: metric.label,
          target_unit: metric.target_unit,
          precision: metric.precision,
          min_value: metric.min_value,
          max_value: metric.max_value,
          aliases: metric.aliases,
        })),
      };
      const created = await api.post<Ruleset>("/api/rulesets", payload);
      setSuccess(`已保存规则 v${created.version}`);
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const targetCandidates = (metric: DraftMetric) => {
    const dimension = unitMeta[metric.target_unit]?.dimension;
    return dimensions.find((item) => item.key === dimension)?.units ?? [];
  };

  if (!rulesets) {
    return error ? <Notice tone="danger">{error}</Notice> : <Loading label="正在读取规则…" />;
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <div className="eyebrow">规则维护</div>
          <h1>
            指标规则 <span className="thin">· 版本 {latest ? `v${latest.version}` : "—"}</span>
          </h1>
          <div className="sub">
            每个规则版本一经保存即不可更改。调整后保存为新版本，已有批次继续引用旧版本，
            结果不会漂移。
          </div>
        </div>
        <div className="row">
          <input
            className="input"
            style={{ width: 180 }}
            value={name}
            onChange={(event) => setName(event.target.value)}
            aria-label="规则集名称"
          />
          <button className="btn btn-accent" onClick={save} disabled={saving}>
            {saving ? <span className="spinner" style={{ width: 13, height: 13 }} /> : <Icon name="check" size={15} />}
            保存为新版本
          </button>
        </div>
      </div>

      {error ? <Notice tone="danger" icon="alert">{error}</Notice> : null}
      {success ? <Notice tone="good" icon="check">{success}</Notice> : null}
      {latest?.warnings?.length ? (
        <Notice tone="warn" icon="alert">
          <b>当前规则有需要注意的别名：</b>
          <ul style={{ margin: "5px 0 0 18px", padding: 0 }}>
            {latest.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </Notice>
      ) : null}

      <div className="stack" style={{ marginTop: 18 }}>
        {drafts.map((metric, index) => {
          const ambiguous = Object.entries(metric.aliases).filter(([, units]) => units.length > 1);
          const isOpen = expanded === metric.key;
          return (
            <div className="metric-card" key={metric.key}>
              <div className="metric-head">
                <div className="m-name">
                  <span className="m-key">{metric.label}</span>
                  <span className="m-sub">目标 {metric.target_unit}</span>
                  {ambiguous.length ? (
                    <span className="chip chip-warn">
                      <Icon name="alert" size={11} />
                      {ambiguous.length} 个待确认别名
                    </span>
                  ) : (
                    <span className="chip chip-good">
                      <Icon name="check" size={11} /> 别名明确
                    </span>
                  )}
                </div>
                <button className="btn btn-sm btn-ghost" onClick={() => setExpanded(isOpen ? null : metric.key)}>
                  {isOpen ? "收起" : "展开"} <Icon name="chevron" size={13} style={{ transform: isOpen ? "rotate(90deg)" : "rotate(-90deg)" }} />
                </button>
              </div>
              {isOpen ? (
                <div className="metric-body">
                  <div className="rule-grid">
                    <label className="field">
                      <span className="field-label">目标单位</span>
                      <select
                        className="select"
                        value={metric.target_unit}
                        onChange={(event) => update(index, { target_unit: event.target.value })}
                      >
                        {targetCandidates(metric).map((unit) => (
                          <option key={unit.code} value={unit.code}>
                            {unit.display} ({unit.code})
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="field">
                      <span className="field-label">输出精度</span>
                      <input
                        className="input num"
                        type="number"
                        min={0}
                        max={8}
                        value={metric.precision}
                        onChange={(event) =>
                          update(index, {
                            precision: Number(event.target.value),
                          })
                        }
                      />
                    </label>
                    <label className="field">
                      <span className="field-label">合理下限</span>
                      <input
                        className="input num"
                        value={metric.min_value ?? ""}
                        placeholder="可留空"
                        onChange={(event) => update(index, { min_value: event.target.value || null })}
                      />
                    </label>
                    <label className="field">
                      <span className="field-label">合理上限</span>
                      <input
                        className="input num"
                        value={metric.max_value ?? ""}
                        placeholder="可留空"
                        onChange={(event) => update(index, { max_value: event.target.value || null })}
                      />
                    </label>
                  </div>
                  <div className="muted" style={{ fontSize: 11.5 }}>
                    合理范围按换算后的 {metric.target_unit} 精确值判定，在舍入之前比较。
                  </div>
                  <div>
                    <div className="section-label">来源单位别名</div>
                    <div className="aliases">
                      {Object.entries(metric.aliases).map(([alias, units]) => (
                        <div key={alias} className="row row-wrap" style={{ gap: 6 }}>
                          <span className={`alias-tag ${units.length > 1 ? "ambiguous" : ""}`}>
                            {alias}
                            <span className="alias-target">→ {units.join(" / ")}</span>
                            <button className="x" onClick={() => removeAlias(index, alias)} aria-label="删除别名">
                              <Icon name="x" size={11} />
                            </button>
                          </span>
                          <span className="muted" style={{ fontSize: 10.5 }}>
                            {units.map((code) => unitMeta[code]?.display ?? code).join("、")}
                          </span>
                        </div>
                      ))}
                    </div>
                    <AliasAdder
                      options={targetCandidates(metric).map((unit) => ({
                        code: unit.code,
                        label: `${unit.code} · ${unit.display}`,
                      }))}
                      onAdd={(alias, units) => addAlias(index, alias, units)}
                    />
                  </div>
                  <div>
                    <div className="section-label">已允许的来源单位</div>
                    <div className="row row-wrap">
                      {metric.accepted_units.map((code) => (
                        <span key={code} className="chip chip-outline">
                          <span className="mono">{code}</span>
                          <span style={{ fontWeight: 500 }}>{unitMeta[code]?.display}</span>
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>

      <div className="card" style={{ marginTop: 22 }}>
        <div className="card-head">
          <div className="card-title">
            <Icon name="clock" size={15} /> 规则版本
          </div>
          <span className="card-hint">新版本只在保存时创建</span>
        </div>
        <div className="version-list">
          {rulesets.map((ruleset, index) => (
            <div className={`version-item ${index === 0 ? "current" : ""}`} key={ruleset.id}>
              <div className="row" style={{ gap: 12 }}>
                <span className="mono" style={{ fontWeight: 650 }}>v{ruleset.version}</span>
                <span style={{ fontWeight: 560 }}>{ruleset.name}</span>
                {index === 0 ? <span className="chip chip-info">当前</span> : null}
              </div>
              <div className="row" style={{ gap: 14, color: "var(--ink-3)", fontSize: 11.5 }}>
                <span>{ruleset.metrics.length} 个指标</span>
                <span>{ruleset.batches ?? 0} 个批次引用</span>
                <span>{formatDateShort(ruleset.created_at)}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function AliasAdder({
  options,
  onAdd,
}: {
  options: { code: string; label: string }[];
  onAdd: (alias: string, units: string[]) => void;
}) {
  const [alias, setAlias] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  return (
    <div className="alias-add" style={{ marginTop: 10 }}>
      <input
        className="input mono"
        placeholder="新别名，如 g"
        value={alias}
        onChange={(event) => setAlias(event.target.value)}
        aria-label="新别名"
        style={{ maxWidth: 160 }}
      />
      <select
        className="select"
        multiple
        value={selected}
        onChange={(event) => {
          const values = Array.from(event.target.selectedOptions, (option) => option.value);
          setSelected(values);
        }}
        aria-label="别名指向单位"
        style={{ minHeight: 32, maxWidth: 190 }}
      >
        {options.map((option) => (
          <option key={option.code} value={option.code}>
            {option.label}
          </option>
        ))}
      </select>
      <button
        className="btn btn-sm"
        disabled={!alias.trim() || selected.length === 0}
        onClick={() => {
          onAdd(alias, selected);
          setAlias("");
          setSelected([]);
        }}
      >
        <Icon name="plus" size={13} /> 添加
      </button>
      <span className="muted" style={{ fontSize: 11 }}>
        选择多个单位即为「待确认」别名
      </span>
    </div>
  );
}

function formatDateShort(iso?: string) {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}
