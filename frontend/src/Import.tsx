import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "./api";
import { EmptyState, Loading, Notice } from "./Feedback";
import { Icon } from "./Icon";
import { ConflictPanel, MappingEditor, SampleTable } from "./Mapping";
import { PageHead } from "./Shell";
import { useToast } from "./Feedback";
import type { Batch, DimensionInfo, PreviewResult, Ruleset } from "./types";
import { formatDate } from "./ui";

type Mapping = Record<
  string,
  { value_column: string; unit_column: string | null; default_unit: string | null }
>;

export function ImportPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const [ruleset, setRuleset] = useState<Ruleset | null>(null);
  const [dimensions, setDimensions] = useState<DimensionInfo[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [mapping, setMapping] = useState<Mapping>({});
  const [confirmations, setConfirmations] = useState<Record<string, string>>({});
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    Promise.all([
      api.get<Ruleset>("/api/rulesets/latest").catch(() => null),
      api.get<{ dimensions: DimensionInfo[] }>("/api/units"),
    ])
      .then(([activeRules, units]) => {
        setRuleset(activeRules);
        setDimensions(units.dimensions);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  const unitLabels = useMemo(() => {
    const map: Record<string, string> = {};
    for (const dimension of dimensions) {
      for (const unit of dimension.units) map[unit.code] = unit.display;
    }
    return map;
  }, [dimensions]);

  const runPreview = useCallback(
    async (selected: File, nextMapping?: Mapping, nextConfirmations?: Record<string, string>) => {
      setBusy(true);
      setError(null);
      try {
        const form = new FormData();
        form.append("file", selected);
        if (nextMapping && Object.keys(nextMapping).length) {
          form.append("mapping", JSON.stringify(nextMapping));
        }
        if (nextConfirmations && Object.keys(nextConfirmations).length) {
          form.append("confirmations", JSON.stringify(nextConfirmations));
        }
        const result = await api.upload<PreviewResult>("/api/batches/preview", form);
        setPreview(result);
        const suggested = result.validated_mapping ?? buildMappingFromSuggestions(result);
        setMapping(suggested);
        setConfirmations((current) => ({ ...result.confirmations, ...(nextConfirmations ?? current) }));
        if (result.error) setError(result.error);
      } catch (err) {
        setError((err as Error).message);
        setPreview(null);
      } finally {
        setBusy(false);
      }
    },
    [],
  );

  const chooseFile = (selected: File) => {
    setFile(selected);
    setPreview(null);
    setError(null);
    setName(selected.name.replace(/\.[^.]+$/, ""));
    setConfirmations({});
    void runPreview(selected);
  };

  const create = async () => {
    if (!file || !preview) return;
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("name", name.trim() || file.name);
      form.append("mapping", JSON.stringify(mapping));
      form.append("confirmations", JSON.stringify(confirmations));
      const batch = await api.upload<Batch>("/api/batches", form);
      toast.show(`批次已生成：${batch.summary.rows_ok} 行正常 / ${batch.summary.rows_exception} 行异常`);
      navigate(`/batches/${batch.id}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const unresolvedConflicts = preview
    ? preview.unit_conflicts.filter((conflict) => !confirmations[`${conflict.metric}:${conflict.alias}`])
    : [];

  const mappedCount = Object.values(mapping).filter((entry) => entry.value_column).length;
  const canCreate =
    preview && !preview.error && unresolvedConflicts.length === 0 && mappedCount > 0 && !busy;

  return (
    <div>
      <PageHead
        eyebrow="导入 / 换算"
        title={
          <>
            上传带数值和单位的 CSV <span className="thin">· 统一换算</span>
          </>
        }
        sub="数值先按精确有理数换算到目标单位，只在最后一步按规则精度四舍五入。原始字符串、公式和规则版本都会保留下来。"
        actions={
          ruleset ? (
            <div className="version-chip" style={{ padding: "8px 12px" }}>
              <Icon name="lock" size={13} />
              <span>
                使用规则 <b>v{ruleset.version}</b> · {ruleset.name}
              </span>
            </div>
          ) : (
            <Notice tone="warn" icon="alert">
              尚未配置规则，请先到 <a href="/rules">规则页</a> 保存。
            </Notice>
          )
        }
      />

      {!ruleset && !error ? <Loading label="正在读取规则…" /> : null}

      {error ? (
        <Notice tone="danger" icon="alert">
          {error}
        </Notice>
      ) : null}

      {!file ? (
        <div
          className={`dropzone ${dragging ? "dragging" : ""}`}
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            const dropped = event.dataTransfer.files?.[0];
            if (dropped) chooseFile(dropped);
          }}
          onClick={() => inputRef.current?.click()}
          role="button"
          tabIndex={0}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") inputRef.current?.click();
          }}
        >
          <div className="dz-icon">
            <Icon name="upload" size={21} />
          </div>
          <h3>把 CSV 拖到这里，或点击选择文件</h3>
          <p>首行为表头；单位可以写在单元格里（1.2kg），也可以单独一列。UTF-8 / GB18030 自动识别。</p>
          <input
            ref={inputRef}
            type="file"
            accept=".csv,text/csv"
            onChange={(event) => {
              const selected = event.target.files?.[0];
              if (selected) chooseFile(selected);
              event.target.value = "";
            }}
          />
        </div>
      ) : null}

      {busy && !preview ? <Loading label="正在解析文件…" /> : null}

      {file ? (
        <div className="stack" style={{ marginTop: 18 }}>
          <div className="file-chip">
            <Icon name="file" size={17} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="name">{file.name}</div>
              <div className="meta">
                {(file.size / 1024).toFixed(1)} KB ·{" "}
                {preview
                  ? `${preview.row_count} 行数据 · ${preview.header.length} 列 · ${preview.encoding} · 分隔符「${preview.delimiter === "\t" ? "TAB" : preview.delimiter}」`
                  : "解析中…"}
              </div>
            </div>
            <div className="field" style={{ width: 220 }}>
              <span className="field-label">批次名称</span>
              <input className="input" value={name} onChange={(event) => setName(event.target.value)} />
            </div>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => {
                setFile(null);
                setPreview(null);
                setMapping({});
                setConfirmations({});
                setError(null);
              }}
            >
              <Icon name="x" size={13} /> 移除
            </button>
          </div>

          {preview && preview.notes.length ? (
            <Notice tone="info" icon="info">
              <b>列识别说明：</b>
              <ul style={{ margin: "4px 0 0 18px", padding: 0 }}>
                {preview.notes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            </Notice>
          ) : null}

          {preview ? (
            <>
              <div className="card">
                <div className="card-head">
                  <div className="card-title">
                    <Icon name="table" size={15} /> 列映射
                  </div>
                  <span className="card-hint">数值列标「·」的会参与换算</span>
                </div>
                <div className="card-pad">
                  <MappingEditor
                    header={preview.header}
                    preview={preview}
                    mapping={mapping}
                    onChange={(next) => setMapping(next)}
                  />
                  {preview.skipped_metrics?.length ? (
                    <div className="muted" style={{ marginTop: 10, fontSize: 11.5 }}>
                      未映射的指标将被跳过：{preview.skipped_metrics.join("、")}
                    </div>
                  ) : null}
                </div>
              </div>

              {preview.unit_conflicts.length ? (
                <div className="card">
                  <div className="card-head">
                    <div className="card-title">
                      <Icon name="alert" size={15} /> 单位别名冲突，需要先确认
                    </div>
                    <span className="card-hint">确认只影响本次导入，不改动规则</span>
                  </div>
                  <div className="card-pad">
                    <ConflictPanel
                      conflicts={preview.unit_conflicts}
                      confirmations={confirmations}
                      onChange={setConfirmations}
                      unitLabels={unitLabels}
                    />
                  </div>
                </div>
              ) : null}

              <div className="card">
                <div className="card-head">
                  <div className="card-title">
                    <Icon name="file" size={15} /> 前 8 行预览
                  </div>
                </div>
                <div className="card-pad">
                  <SampleTable preview={preview} mapping={mapping} />
                </div>
              </div>

              <div className="card-pad" style={{ display: "flex", gap: 12, alignItems: "center" }}>
                <button className="btn btn-primary" disabled={!canCreate} onClick={create}>
                  <Icon name="sparkle" size={15} />
                  生成批次并换算
                </button>
                <button className="btn btn-ghost" onClick={() => file && runPreview(file, mapping, confirmations)}>
                  重新预览
                </button>
                <span className="muted" style={{ fontSize: 12 }}>
                  {preview.error
                    ? "修正映射后才能生成批次"
                    : unresolvedConflicts.length
                      ? `还有 ${unresolvedConflicts.length} 个别名待确认`
                      : `将处理 ${mappedCount} 个指标、${preview.row_count} 行数据`}
                </span>
              </div>
            </>
          ) : null}
        </div>
      ) : null}

      {!file ? (
        <RecentBatches />
      ) : null}
      {toast.node}
    </div>
  );
}

function buildMappingFromSuggestions(preview: PreviewResult): Mapping {
  const mapping: Mapping = {};
  for (const metric of preview.metrics) {
    const suggestion = preview.suggested_mapping[metric.key];
    mapping[metric.key] = {
      value_column: suggestion?.value_column ?? "",
      unit_column: suggestion?.unit_column ?? null,
      default_unit: suggestion?.default_unit ?? null,
    };
  }
  return mapping;
}

function RecentBatches() {
  const navigate = useNavigate();
  const [items, setItems] = useState<
    { id: string; name: string; status: string; rules_version: number; rows_exception: number; row_count: number; created_at: string }[] | null
  >(null);

  useEffect(() => {
    api
      .get<{ items: typeof items }>("/api/batches")
      .then((data) => setItems(data.items ?? []))
      .catch(() => setItems([]));
  }, []);

  if (!items) return null;
  if (!items.length) {
    return (
      <div style={{ marginTop: 26 }}>
        <EmptyState
          title="还没有批次"
          hint="上传一个 CSV 后，这里会出现最近的批次。也可以先到规则页确认目标单位和别名。"
        />
      </div>
    );
  }
  return (
    <div style={{ marginTop: 28 }}>
      <div className="row spread" style={{ marginBottom: 10 }}>
        <div className="section-label" style={{ margin: 0 }}>
          最近批次
        </div>
        <button className="btn btn-sm btn-ghost" onClick={() => navigate("/batches")}>
          查看全部 <Icon name="chevron" size={12} />
        </button>
      </div>
      <div className="card">
        {items.slice(0, 4).map((item) => (
          <div className="batch-row" key={item.id} onClick={() => navigate(`/batches/${item.id}`)}>
            <div>
              <div className="batch-name">
                {item.name}
                {item.status === "published" ? (
                  <span className="chip chip-good">
                    <Icon name="lock" size={10} /> 已发布
                  </span>
                ) : (
                  <span className="chip chip-outline">工作副本</span>
                )}
              </div>
              <div className="batch-meta">
                <span>v{item.rules_version}</span>
                <span>{item.row_count} 行</span>
                <span>{formatDate(item.created_at)}</span>
              </div>
            </div>
            <div className="batch-stats">
              <span className="chip chip-good">{item.row_count - item.rows_exception} 行正常</span>
              {item.rows_exception ? (
                <span className="chip chip-critical">{item.rows_exception} 行异常</span>
              ) : null}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
