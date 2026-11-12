import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "./api";
import { Icon } from "./Icon";
import { EmptyState, Loading } from "./Feedback";
import { PageHead } from "./Shell";
import type { BatchListItem } from "./types";
import { formatDate } from "./ui";

export function BatchesPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<BatchListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<{ items: BatchListItem[] }>("/api/batches")
      .then((data) => setItems(data.items))
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <div>
      <PageHead
        eyebrow="批次"
        title={
          <>
            所有批次 <span className="thin">· 结果留痕</span>
          </>
        }
        sub="每个批次固定一个规则版本和一份数据副本。已发布的批次不可修改；规则调整会生成新批次。"
        actions={
          <button className="btn btn-accent" onClick={() => navigate("/")}>
            <Icon name="plus" size={14} /> 导入新 CSV
          </button>
        }
      />
      {error ? <div className="notice notice-danger">{error}</div> : null}
      {!items ? (
        <Loading label="正在读取批次…" />
      ) : !items.length ? (
        <EmptyState title="还没有批次" hint="从「导入换算」上传一个 CSV 开始。" />
      ) : (
        <div className="card">
          {items.map((item) => {
            const exceptions = item.row_count - item.rows_ok;
            return (
              <div
                key={item.id}
                className="batch-row"
                onClick={() => navigate(`/batches/${item.id}`)}
              >
                <div style={{ minWidth: 0 }}>
                  <div className="batch-name">
                    <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {item.name}
                    </span>
                    {item.status === "published" ? (
                      <span className="chip chip-good">
                        <Icon name="lock" size={10} /> 已发布
                      </span>
                    ) : (
                      <span className="chip chip-outline">工作副本</span>
                    )}
                    {item.parent_batch_id ? <span className="chip chip-info">派生</span> : null}
                  </div>
                  <div className="batch-meta">
                    <span className="mono">v{item.rules_version}</span>
                    <span>{item.dataset_filename}</span>
                    <span>{item.row_count} 行 · {Object.values(item.cells).reduce((a, b) => a + b, 0)} 单元格</span>
                    <span>{formatDate(item.created_at)}</span>
                    {item.published_at ? <span>发布 {formatDate(item.published_at)}</span> : null}
                  </div>
                </div>
                <div className="batch-stats">
                  <span className="chip chip-good">{item.rows_ok} 行正常</span>
                  {exceptions ? <span className="chip chip-critical">{exceptions} 行异常</span> : null}
                  <Icon name="chevron" size={15} className="muted" />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
