import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "./api";
import { useToast } from "./Feedback";
import { Icon } from "./Icon";
import type { CompareResult, ResultRow } from "./types";
import { categoryStyle, formatDate, statusLabel } from "./ui";

export function ComparePage() {
  const { batchId, otherId } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState<CompareResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("all");
  const toast = useToast();

  useEffect(() => {
    if (!batchId || !otherId) return;
    setData(null);
    setError(null);
    api
      .get<CompareResult>(`/api/batches/${batchId}/compare/${otherId}`)
      .then(setData)
      .catch((err: Error) => setError(err.message));
  }, [batchId, otherId]);

  const changes = useMemo(() => {
    if (!data) return [];
    if (filter === "all") return data.changes;
    return data.changes.filter((change) => change.change === filter);
  }, [data, filter]);

  return (
    <div>
      <div className="page-head">
        <div>
          <div className="eyebrow">批次比较</div>
          <h1>规则调整前后对照</h1>
          <div className="sub">
            旧批次的已发布结果保持原样；这里只读地比较两份结果，不修改任何一方。
          </div>
        </div>
        <div className="row">
          <button className="btn btn-ghost" onClick={() => navigate(`/batches/${batchId}`)}>
            <Icon name="chevron" size={14} style={{ transform: "rotate(180deg)" }} />
            返回批次
          </button>
        </div>
      </div>

      {error ? <div className="notice notice-danger">{error}</div> : null}

      {data ? (
        <>
          <div className="compare-heads" style={{ marginBottom: 18 }}>
            <div className="compare-side">
              <div className="tag">旧批次</div>
              <div className="nm">{data.left.name}</div>
              <div className="mt">
                v{data.left.rules_version} · {statusLabel(data.left.status)} · {formatDate(data.left.created_at)}
                {data.left.published_at ? ` · 发布于 ${formatDate(data.left.published_at)}` : ""}
              </div>
            </div>
            <div className="compare-vs">
              <Icon name="compare" size={22} />
            </div>
            <div className="compare-side">
              <div className="tag">新批次</div>
              <div className="nm">{data.right.name}</div>
              <div className="mt">
                v{data.right.rules_version} · {statusLabel(data.right.status)} · {formatDate(data.right.created_at)}
              </div>
            </div>
          </div>

          <div className="stats" style={{ marginBottom: 18 }}>
            <div className="stat" role="button" onClick={() => setFilter("all")} style={{ cursor: "pointer" }}>
              <div className="n">{data.changed_total}</div>
              <div className="l">
                <span className="dot" style={{ background: "var(--accent)" }} />
                有变化的单元格
              </div>
            </div>
            <div className="stat" role="button" onClick={() => setFilter("changed")} style={{ cursor: "pointer" }}>
              <div className="n">{data.counts.changed ?? 0}</div>
              <div className="l">
                <span className="dot" style={{ background: "var(--serious)" }} />
                结果或类别变化
              </div>
            </div>
            <div className="stat" role="button" onClick={() => setFilter("moved")} style={{ cursor: "pointer" }}>
              <div className="n">{data.counts.moved ?? 0}</div>
              <div className="l">
                <span className="dot" style={{ background: "var(--info)" }} />
                来源或公式变化
              </div>
            </div>
            <div className="stat">
              <div className="n">{data.rows_compared}</div>
              <div className="l">
                <span className="dot" style={{ background: "var(--ink-3)" }} />
                比较的单元格
              </div>
            </div>
            <div className="stat">
              <div className="n">{data.counts.same ?? 0}</div>
              <div className="l">
                <span className="dot" style={{ background: "var(--good)" }} />
                未变化
              </div>
            </div>
          </div>

          {data.identical ? (
            <div className="notice notice-good">
              <Icon name="check" size={15} className="icon" />
              两个批次的全部单元格结果一致，规则调整没有改变任何输出。
            </div>
          ) : (
            <div className="card">
              <div className="card-head">
                <div className="card-title">
                  <Icon name="compare" size={15} /> 变化明细
                  {data.truncated ? <span className="card-hint">（仅显示前 500 条）</span> : null}
                </div>
                <div className="field" style={{ minWidth: 160, padding: 0 }}>
                  <select className="select" value={filter} onChange={(event) => setFilter(event.target.value)}>
                    <option value="all">全部变化</option>
                    <option value="changed">结果或类别变化</option>
                    <option value="moved">来源或公式变化</option>
                  </select>
                </div>
              </div>
              <div className="results-wrap">
                <table className="changes">
                  <thead>
                    <tr>
                      <th className="ln">行号</th>
                      <th>指标</th>
                      <th>原始输入</th>
                      <th>旧结果</th>
                      <th>新结果</th>
                      <th>说明</th>
                    </tr>
                  </thead>
                  <tbody>
                    {changes.map((change) => (
                      <tr key={`${change.row_no}-${change.metric}`}>
                        <td className="ln">{change.row_no}</td>
                        <td style={{ fontWeight: 560 }}>{change.metric_label}</td>
                        <td className="mono" style={{ fontSize: 11.5 }}>
                          {change.new?.raw_cell || change.old?.raw_cell || "—"}
                          {change.new?.source_unit || change.old?.source_unit ? (
                            <span className="muted"> · {change.new?.source_unit ?? change.old?.source_unit}</span>
                          ) : null}
                        </td>
                        <td className="val">
                          {change.old ? (
                            <span className={change.new && change.old.formatted_result !== change.new.formatted_result ? "from" : ""}>
                              {change.old.formatted_result ?? categoryStyle(change.old.category).label}
                            </span>
                          ) : (
                            <span className="muted">—</span>
                          )}
                        </td>
                        <td className="val">
                          {change.new ? (
                            <span className={change.old && change.old.formatted_result !== change.new.formatted_result ? "to" : ""}>
                              {change.new.formatted_result ?? categoryStyle(change.new.category).label}
                            </span>
                          ) : (
                            <span className="muted">—</span>
                          )}
                        </td>
                        <td className="muted" style={{ fontSize: 11.5, maxWidth: 320 }}>
                          {change.detail}
                          {change.old?.formula && change.new?.formula && change.old.formula !== change.new.formula ? (
                            <div className="mono" style={{ fontSize: 10.5, marginTop: 2 }}>
                              {change.old.formula} → {change.new.formula}
                            </div>
                          ) : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!changes.length ? (
                  <div className="empty">
                    <b>没有匹配的变化</b>
                    换一个筛选条件试试。
                  </div>
                ) : null}
              </div>
            </div>
          )}
        </>
      ) : error ? null : (
        <div className="loading-block">
          <span className="spinner" /> 正在比较两个批次…
        </div>
      )}
      {toast.node}
    </div>
  );
}
