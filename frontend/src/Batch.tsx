import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "./api";
import { useToast } from "./Feedback";
import { Icon } from "./Icon";
import { PageHead } from "./Shell";
import type { Batch, ResultRow, ResultsResponse, RowDetail } from "./types";
import { categoryStyle, CATEGORY_ORDER, formatDate, signedDelta } from "./ui";

const PAGE_SIZE = 40;

export function BatchPage() {
  const { batchId } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const [batch, setBatch] = useState<Batch | null>(null);
  const [results, setResults] = useState<ResultsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [category, setCategory] = useState<string>("all");
  const [metric, setMetric] = useState<string>("all");
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<ResultRow | null>(null);
  const [detail, setDetail] = useState<RowDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [rulesets, setRulesets] = useState<{ id: number; version: number; name: string }[]>([]);
  const [targetRuleset, setTargetRuleset] = useState<number | "">("");
  const [showComparePicker, setShowComparePicker] = useState(false);
  const [otherBatches, setOtherBatches] = useState<{ id: string; name: string; rules_version: number }[]>([]);

  useEffect(() => {
    if (!batchId) return;
    setLoading(true);
    Promise.all([
      api.get<Batch>(`/api/batches/${batchId}`),
      api.get<{ items: { id: number; version: number; name: string }[] }>("/api/rulesets"),
      api.get<{ items: { id: string; name: string; rules_version: number }[] }>("/api/batches"),
    ])
      .then(([batchData, rules, batches]) => {
        setBatch(batchData);
        setRulesets(rules.items);
        const current = rules.items.find((item) => item.version !== batchData.rules_version);
        setTargetRuleset(current?.id ?? rules.items[0]?.id ?? "");
        setOtherBatches(
          batches.items.filter((item) => item.id !== batchData.id && item.id !== batchData.parent_batch_id),
        );
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [batchId]);

  useEffect(() => {
    if (!batchId) return;
    const params = new URLSearchParams();
    if (category !== "all") params.set("category", category);
    if (metric !== "all") params.set("metric", metric);
    if (search) params.set("search", search);
    params.set("limit", String(PAGE_SIZE));
    params.set("offset", String(offset));
    api
      .get<ResultsResponse>(`/api/batches/${batchId}/results?${params.toString()}`)
      .then(setResults)
      .catch((err: Error) => setError(err.message));
  }, [batchId, category, metric, search, offset]);

  const openDetail = async (row: ResultRow) => {
    if (!batchId) return;
    setSelected(row);
    setDetail(null);
    try {
      const data = await api.get<RowDetail>(`/api/batches/${batchId}/rows/${row.row_no}`);
      setDetail(data);
    } catch (err) {
      toast.show((err as Error).message, "error");
    }
  };

  const publish = async () => {
    if (!batchId) return;
    setBusy(true);
    try {
      const updated = await api.post<Batch>(`/api/batches/${batchId}/publish`, {});
      setBatch(updated);
      toast.show("批次已发布，结果与导出文件已锁定");
    } catch (err) {
      toast.show((err as Error).message, "error");
    } finally {
      setBusy(false);
    }
  };

  const stats = batch ? batch.summary : null;
  const metricKeys = useMemo(() => Object.keys(stats?.by_metric ?? {}), [stats]);

  if (loading) {
    return (
      <div className="loading-block">
        <span className="spinner" /> 正在读取批次…
      </div>
    );
  }
  if (error || !batch) {
    return <div className="notice notice-danger">{error ?? "批次不存在"}</div>;
  }

  const totalPages = results ? Math.max(1, Math.ceil(results.total / PAGE_SIZE)) : 1;
  const page = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <div>
      <PageHead
        eyebrow="批次详情"
        title={
          <span className="row" style={{ gap: 10, flexWrap: "wrap" }}>
            {batch.name}
            {batch.status === "published" ? (
              <span className="chip chip-good">
                <Icon name="lock" size={11} /> 已发布
              </span>
            ) : (
              <span className="chip chip-outline">工作副本</span>
            )}
            {batch.parent_batch_id ? (
              <button
                className="chip chip-info"
                style={{ border: 0, cursor: "pointer" }}
                onClick={() => navigate(`/batches/${batch.parent_batch_id}`)}
              >
                来自旧批次 <Icon name="chevron" size={11} />
              </button>
            ) : null}
          </span>
        }
        sub={
          <>
            规则 v{batch.rules_version} · 数据 {batch.dataset_filename} · sha256 {batch.dataset_hash_short}
            {batch.published_at ? ` · 发布于 ${formatDate(batch.published_at)}` : ""}
          </>
        }
        actions={
          <>
            <a className="btn" href={api.downloadUrl(`/api/batches/${batch.id}/export/detail`)}>
              <Icon name="download" size={14} /> 下载明细
            </a>
            <a className="btn" href={api.downloadUrl(`/api/batches/${batch.id}/export/exceptions`)}>
              <Icon name="download" size={14} /> 异常清单
            </a>
            {batch.status !== "published" ? (
              <button className="btn btn-primary" onClick={publish} disabled={busy}>
                <Icon name="lock" size={14} /> 发布并锁定
              </button>
            ) : null}
          </>
        }
      />

      {batch.status === "published" ? (
        <div className="notice notice-info" style={{ marginBottom: 16 }}>
          <Icon name="lock" size={15} className="icon" />
          <div>
            该批次已发布：结果文件与导出内容保持原样。需要调整规则时，请基于它生成新批次并与旧结果比较。
          </div>
        </div>
      ) : null}

      <div className="meta-bar" style={{ marginBottom: 16 }}>
        <div className="meta-cell">
          <div className="k">规则版本</div>
          <div className="v mono">v{batch.rules_version}</div>
        </div>
        <div className="meta-cell">
          <div className="k">数据行</div>
          <div className="v mono">{batch.summary.row_count}</div>
        </div>
        <div className="meta-cell">
          <div className="k">全部正常</div>
          <div className="v mono" style={{ color: "var(--good)" }}>
            {batch.summary.rows_ok}
          </div>
        </div>
        <div className="meta-cell">
          <div className="k">含异常</div>
          <div className="v mono" style={{ color: batch.summary.rows_exception ? "var(--critical)" : "var(--ink)" }}>
            {batch.summary.rows_exception}
          </div>
        </div>
        <div className="meta-cell">
          <div className="k">创建于</div>
          <div className="v mono" style={{ fontSize: 12 }}>{formatDate(batch.created_at)}</div>
        </div>
        <div className="meta-cell">
          <div className="k">单元格</div>
          <div className="v mono">{batch.summary.total_cells}</div>
        </div>
      </div>

      <div className="stats" style={{ marginBottom: 16 }}>
        {CATEGORY_ORDER.map((key) => {
          const count = batch.summary.cells[key] ?? 0;
          if (key !== "ok" && count === 0 && category !== key) return null;
          const style = categoryStyle(key);
          return (
            <button
              key={key}
              className={`stat ${category === key || (key === "ok" && category === "all") ? "active" : ""}`}
              onClick={() => {
                setCategory(key === "ok" ? "ok" : key);
                setOffset(0);
              }}
            >
              <div className="n" style={{ color: key === "ok" ? "var(--good)" : count ? style.color : "var(--ink-3)" }}>
                {count}
              </div>
              <div className="l">
                <span className="dot" style={{ background: style.color }} />
                {style.label}
              </div>
            </button>
          );
        })}
        <button className={`stat ${category === "exception" ? "active" : ""}`} onClick={() => { setCategory("exception"); setOffset(0); }}>
          <div className="n" style={{ color: "var(--critical)" }}>
            {batch.summary.cells
              ? Object.entries(batch.summary.cells)
                  .filter(([key]) => key !== "ok")
                  .reduce((sum, [, value]) => sum + value, 0)
              : 0}
          </div>
          <div className="l">
            <span className="dot" style={{ background: "var(--critical)" }} />
            全部异常
          </div>
        </button>
      </div>

      <div className="card">
        <div className="filters">
          <div className="field">
            <span className="field-label">类别</span>
            <select
              className="select"
              value={category}
              onChange={(event) => {
                setCategory(event.target.value);
                setOffset(0);
              }}
            >
              <option value="all">全部类别</option>
              <option value="exception">仅异常</option>
              {CATEGORY_ORDER.map((key) => (
                <option key={key} value={key}>
                  {categoryStyle(key).label}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <span className="field-label">指标</span>
            <select
              className="select"
              value={metric}
              onChange={(event) => {
                setMetric(event.target.value);
                setOffset(0);
              }}
            >
              <option value="all">全部指标</option>
              {metricKeys.map((key) => (
                <option key={key} value={key}>
                  {key}
                </option>
              ))}
            </select>
          </div>
          <form
            className="field grow"
            onSubmit={(event) => {
              event.preventDefault();
              setSearch(searchInput.trim());
              setOffset(0);
            }}
          >
            <span className="field-label">搜索原值 / 结果 / 说明</span>
            <div className="row" style={{ gap: 6 }}>
              <input
                className="input"
                value={searchInput}
                placeholder="例如 500.5g、超出、y = 5/9"
                onChange={(event) => setSearchInput(event.target.value)}
              />
              <button className="btn btn-sm" type="submit">
                <Icon name="search" size={13} /> 搜索
              </button>
              {search ? (
                <button
                  className="btn btn-sm btn-ghost"
                  type="button"
                  onClick={() => {
                    setSearch("");
                    setSearchInput("");
                  }}
                >
                  清除
                </button>
              ) : null}
            </div>
          </form>
        </div>

        {results ? (
          <>
            <div className="results-wrap">
              <table className="results">
                <thead>
                  <tr>
                    <th className="ln">行号</th>
                    <th>指标</th>
                    <th>原始输入</th>
                    <th>单位识别</th>
                    <th>公式</th>
                    <th style={{ textAlign: "right" }}>换算结果</th>
                    <th>状态</th>
                    <th>说明</th>
                  </tr>
                </thead>
                <tbody>
                  {results.items.map((row) => (
                    <ResultLine
                      key={`${row.row_no}-${row.metric}`}
                      row={row}
                      selected={selected?.row_no === row.row_no && selected?.metric === row.metric}
                      onClick={() => openDetail(row)}
                    />
                  ))}
                </tbody>
              </table>
              {!results.items.length ? (
                <div className="empty">
                  <b>没有匹配的结果</b>
                  调整类别、指标或搜索条件。
                </div>
              ) : null}
            </div>
            <div className="pager">
              <span>
                第 {page} / {totalPages} 页 · 共 {results.total} 个单元格结果
              </span>
              <div className="row" style={{ gap: 6 }}>
                <button
                  className="btn btn-sm"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                >
                  上一页
                </button>
                <button
                  className="btn btn-sm"
                  disabled={offset + PAGE_SIZE >= results.total}
                  onClick={() => setOffset(offset + PAGE_SIZE)}
                >
                  下一页
                </button>
              </div>
            </div>
          </>
        ) : (
          <div className="loading-block">
            <span className="spinner" /> 正在读取结果…
          </div>
        )}
      </div>

      <div className="card" style={{ marginTop: 18 }}>
        <div className="card-head">
          <div className="card-title">
            <Icon name="sliders" size={15} /> 规则调整与新批次
          </div>
          <span className="card-hint">调整规则不会修改本批次</span>
        </div>
        <div className="card-pad">
          <div className="row row-wrap" style={{ alignItems: "flex-end" }}>
            <label className="field" style={{ minWidth: 220 }}>
              <span className="field-label">使用规则版本</span>
              <select
                className="select"
                value={targetRuleset}
                onChange={(event) => setTargetRuleset(Number(event.target.value))}
              >
                {rulesets.map((ruleset) => (
                  <option key={ruleset.id} value={ruleset.id}>
                    v{ruleset.version} · {ruleset.name}
                    {ruleset.version === batch.rules_version ? "（当前）" : ""}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="btn btn-accent"
              disabled={!targetRuleset || busy}
              onClick={async () => {
                if (!batchId) return;
                setBusy(true);
                try {
                  const form = new FormData();
                  form.append("ruleset_id", String(targetRuleset));
                  form.append("name", `${batch.name} · v${rulesets.find((item) => item.id === targetRuleset)?.version}`);
                  const created = await api.upload<Batch>(`/api/batches/${batchId}/recompute`, form);
                  toast.show("新批次已生成，可进行比较");
                  navigate(`/batches/${created.id}`);
                } catch (err) {
                  toast.show((err as Error).message, "error");
                } finally {
                  setBusy(false);
                }
              }}
            >
              <Icon name="sparkle" size={14} /> 生成新批次
            </button>
            {otherBatches.length ? (
              <div style={{ position: "relative" }}>
                <button className="btn" onClick={() => setShowComparePicker((value) => !value)}>
                  <Icon name="compare" size={14} /> 与其它批次比较
                </button>
                {showComparePicker ? (
                  <div
                    className="card"
                    style={{ position: "absolute", bottom: "calc(100% + 6px)", right: 0, minWidth: 280, zIndex: 5 }}
                  >
                    {otherBatches.map((item) => (
                      <div
                        key={item.id}
                        className="version-item"
                        style={{ cursor: "pointer" }}
                        onClick={() => navigate(`/batches/${batchId}/compare/${item.id}`)}
                      >
                        <span>{item.name}</span>
                        <span className="mono muted">v{item.rules_version}</span>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
          {batch.comparisons_with.length ? (
            <div className="notice notice-info" style={{ marginTop: 12 }}>
              <Icon name="compare" size={14} className="icon" />
              <div>
                由此批次派生了 {batch.comparisons_with.length} 个新批次。{" "}
                <button
                  className="btn btn-sm btn-ghost"
                  onClick={() => navigate(`/batches/${batchId}/compare/${batch.comparisons_with[0]}`)}
                >
                  查看比较
                </button>
              </div>
            </div>
          ) : null}
        </div>
      </div>

      {selected ? (
        <ResultDrawer
          row={selected}
          detail={detail}
          batch={batch}
          onClose={() => {
            setSelected(null);
            setDetail(null);
          }}
        />
      ) : null}
      {toast.node}
    </div>
  );
}

function ResultLine({
  row,
  selected,
  onClick,
}: {
  row: ResultRow;
  selected: boolean;
  onClick: () => void;
}) {
  const style = categoryStyle(row.category);
  const ok = row.category === "ok";
  return (
    <tr className={`${ok ? "" : "exception"} ${selected ? "selected" : ""}`} onClick={onClick}>
      <td className="ln">{row.row_no}</td>
      <td className="metric">{row.metric_label}</td>
      <td className="raw">{row.raw_cell || <span className="muted">—</span>}</td>
      <td>
        {row.recognized?.code ? (
          <span className="row" style={{ gap: 5 }}>
            <span className="mono" style={{ fontSize: 11.5 }}>
              {row.recognized.code}
            </span>
            <span className="muted" style={{ fontSize: 10.5 }}>
              {row.recognized.source === "in_cell" ? "单元格" : row.recognized.source === "unit_column" ? "单位列" : "默认"}
            </span>
          </span>
        ) : (
          <span className="muted" style={{ fontSize: 11 }}>
            {row.recognized?.issue === "ambiguous_unit" ? "待确认" : "—"}
          </span>
        )}
      </td>
      <td className="mono muted" style={{ fontSize: 11 }}>
        {row.formula ?? "—"}
      </td>
      <td style={{ textAlign: "right" }} className="result">
        {ok ? `${row.formatted_result} ${row.target_unit}` : "—"}
      </td>
      <td>
        <span className={`chip ${style.className}`}>{style.label}</span>
      </td>
      <td className="ex">{ok ? row.rounding?.changed ? `舍入 ${signedDelta(row)}` : "未舍入" : row.message}</td>
    </tr>
  );
}

function ResultDrawer({
  row,
  detail,
  batch,
  onClose,
}: {
  row: ResultRow;
  detail: RowDetail | null;
  batch: Batch;
  onClose: () => void;
}) {
  const style = categoryStyle(row.category);
  const rounding = row.rounding;
  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true" aria-label="结果追溯">
        <div className="drawer-head">
          <div>
            <div className="row" style={{ gap: 8, marginBottom: 4 }}>
              <span className="eyebrow" style={{ margin: 0 }}>第 {row.row_no} 行</span>
              <span className={`chip ${style.className}`}>{style.label}</span>
            </div>
            <div className="drawer-title">
              {row.metric_label} · {row.raw_cell || "空单元格"}
            </div>
            <div className="muted" style={{ fontSize: 11.5, marginTop: 3 }}>
              批次 {batch.name} · 规则 v{batch.rules_version}
            </div>
          </div>
          <button className="btn btn-icon btn-ghost" onClick={onClose} aria-label="关闭">
            <Icon name="x" size={16} />
          </button>
        </div>
        <div className="drawer-body">
          <div className="drawer-section">
            <div className="section-label">
              <Icon name="file" size={12} /> 原始行（第 {row.row_no} 行）
            </div>
            {detail ? (
              <div className="raw-quote">{detail.raw_line ?? "（源文件行不可用）"}</div>
            ) : (
              <div className="muted">读取中…</div>
            )}
          </div>

          <div className="drawer-section">
            <div className="section-label">
              <Icon name="check" size={12} /> 结果对照
            </div>
            <div className="meta-bar" style={{ gridTemplateColumns: "1fr 1fr" }}>
              <div className="meta-cell">
                <div className="k">原始字符串</div>
                <div className="v mono" style={{ fontSize: 14 }}>{row.raw_cell || "—"}</div>
                <div className="muted" style={{ fontSize: 10.5, marginTop: 2 }}>
                  {row.raw_value ? `数值 ${row.raw_value}` : ""}
                </div>
              </div>
              <div className="meta-cell">
                <div className="k">换算结果（{row.target_unit}）</div>
                <div className="v mono" style={{ fontSize: 14, color: row.category === "ok" ? "var(--ink)" : "var(--critical)" }}>
                  {row.category === "ok" ? row.formatted_result : "—"}
                </div>
                <div className="muted" style={{ fontSize: 10.5, marginTop: 2 }}>
                  精度 {row.precision} 位 · {row.rounding?.method}
                </div>
              </div>
            </div>
          </div>

          {row.category === "ok" && rounding ? (
            <div className="drawer-section">
              <div className="section-label">
                <Icon name="gauge" size={12} /> 这一步发生了什么
              </div>
              <div className="rounding-callout">
                <div>
                  <b>{row.exact_result_decimal}</b> {row.target_unit} 是精确换算值；规则要求保留{" "}
                  <b>{rounding.precision}</b> 位小数，四舍五入后输出 <b>{rounding.formatted}</b>。
                </div>
                <div style={{ marginTop: 7, fontSize: 11.5 }}>
                  舍入增量 <span className="mono">{rounding.delta}</span> · 精确分数{" "}
                  <span className="mono">{rounding.exact_fraction}</span> · 结果分数{" "}
                  <span className="mono">{rounding.rounded_value}</span>
                </div>
                {rounding.half_tie ? (
                  <div className="tie">
                    <Icon name="alert" size={12} /> 最低位恰为 .5 的半值，按四舍五入（远离零）进位
                  </div>
                ) : null}
              </div>
            </div>
          ) : null}

          {row.recognized ? (
            <div className="drawer-section">
              <div className="section-label">
                <Icon name="scale" size={12} /> 单位识别
              </div>
              <dl className="kv">
                <dt>读取到的单位</dt>
                <dd className="mono">{row.recognized.alias ?? "（无）"}</dd>
                <dt>识别来源</dt>
                <dd>{describe(row.recognized.source)}</dd>
                <dt>匹配结果</dt>
                <dd>
                  {row.recognized.code ? (
                    <span className="row" style={{ gap: 6 }}>
                      <span className="mono">{row.recognized.code}</span>
                      <span className="muted">{row.source_unit_display}</span>
                    </span>
                  ) : (
                    <span className="muted">{row.recognized.message}</span>
                  )}
                </dd>
                <dt>说明</dt>
                <dd className="muted">{row.recognized.message}</dd>
              </dl>
            </div>
          ) : null}

          {row.formula ? (
            <div className="drawer-section">
              <div className="section-label">
                <Icon name="hash" size={12} /> 代入的公式
              </div>
              <div className="formula-box">{row.formula}</div>
              <div className="muted" style={{ fontSize: 11.5, marginTop: 6 }}>
                {row.substitution}
              </div>
            </div>
          ) : null}

          {row.range ? (
            <div className="drawer-section">
              <div className="section-label">
                <Icon name="filter" size={12} /> 合理范围（按目标单位）
              </div>
              <div className={`notice ${row.range.passed === false ? "notice-danger" : row.range.passed ? "notice-good" : "notice-info"}`}>
                <Icon name={row.range.passed === false ? "alert" : "info"} size={14} className="icon" />
                <div>{row.range.message}</div>
              </div>
            </div>
          ) : null}

          {row.trace ? (
            <div className="drawer-section">
              <div className="section-label">
                <Icon name="layers" size={12} /> 计算轨迹
              </div>
              <div className="trace">
                {row.trace.map((step, index) => (
                  <div className={`trace-step ${step.ok ? "" : "fail"}`} key={`${step.step}-${index}`}>
                    <div className="trace-num">{step.ok ? index + 1 : "!"}</div>
                    <div>
                      <div className="st">{step.step}</div>
                      <div className="sd">{step.detail}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {row.category !== "ok" ? (
            <div className="drawer-section">
              <div className="section-label">
                <Icon name="alert" size={12} /> 异常说明
              </div>
              <div className="notice notice-danger">{row.message}</div>
            </div>
          ) : null}

          <div className="drawer-section">
            <div className="section-label">
              <Icon name="sliders" size={12} /> 使用的规则
            </div>
            <dl className="kv">
              <dt>规则版本</dt>
              <dd className="mono">v{batch.rules_version}</dd>
              <dt>目标单位</dt>
              <dd className="mono">{row.target_unit}</dd>
              <dt>输出精度</dt>
              <dd className="mono">{row.precision} 位小数</dd>
              <dt>舍入方式</dt>
              <dd>{row.rounding?.method ?? "四舍五入（远离零）"}</dd>
            </dl>
          </div>
        </div>
      </aside>
    </>
  );
}

function describe(source: string | null): string {
  switch (source) {
    case "in_cell":
      return "单元格内（数值与单位写在一起）";
    case "unit_column":
      return "独立单位列";
    case "column_default":
      return "列默认单位";
    case "header_default":
      return "表头括号提示";
    default:
      return "—";
  }
}
