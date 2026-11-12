# 单位换算台

上传带数值和单位的 CSV，按指标统一换算到目标单位，逐格留痕：原始字符串、识别到的单位、代入的公式、精确结果、舍入位置、规则版本，全部可追溯。

- 后端：Python / FastAPI / SQLite
- 前端：React 18 + TypeScript + Vite
- 换算全程使用 `fractions.Fraction` 精确有理数（解析用 `Decimal`），只在输出时做一次「四舍五入」（远离零）
- 规则版本不可变；批次固定规则快照与数据副本；已发布批次只读，规则调整生成新批次后可只读比较

## 快速开始

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt

# 构建前端（产物 frontend/dist 由后端直接托管）
cd frontend && npm install && npm run build && cd ..

# 启动（默认 http://127.0.0.1:8000）
.venv/bin/uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

开发模式（前端热更新，Vite 把 `/api` 代理到 8000 端口的后端）：

```bash
.venv/bin/uvicorn backend.app:app --reload --port 8000
cd frontend && npm run dev   # http://127.0.0.1:5173
```

首次打开页面时若还没有规则集，点「规则」页会自动写入一套默认规则（v1）。数据库与数据副本分别落在 `data/app.db` 和 `data/datasets/`。

## 使用流程

1. **导入换算**：拖入 CSV，自动嗅探分隔符与编码（UTF-8 / GB18030），自动推断列映射（单元格内单位 `1.2kg`、独立单位列 `重量单位`、表头提示 `重量（kg）`）。
2. **别名冲突确认**：若某个别名同时指向多个单位（如 `度` → `C` / `F`），导入前必须逐个别名选择本次使用的单位；确认只对本次导入生效，不改动规则。
3. **生成批次**：逐格换算并按规则精度舍入，异常分门别类记录。
4. **规则维护**：每个指标可设目标单位、输出精度、合理上下限、来源单位别名、允许的来源单位。保存即生成新版本，旧版本及其批次保持不变。
5. **规则调整 → 新批次 → 比较**：批次详情页选一个规则版本生成派生批次（沿用原批次的数据副本与列映射），再与旧批次只读比较；已发布批次的明细/异常导出内容与快照永远不变。
6. **导出**：明细 CSV 与异常 CSV 第一列都是「原始行号」（表头为第 1 行，数据从第 2 行起）。

## 异常类别

| 类别 | 含义 |
| --- | --- |
| `empty` | 单元格为空或缺失占位符（`—`、`n/a`、`null` 等） |
| `parse_error` | 无法从单元格解析出数值 |
| `unknown_unit` | 单位不在该指标的别名表中 |
| `ambiguous_unit` | 别名指向多个单位且本次导入未确认 |
| `dimension_mismatch` | 来源单位属于别的维度（如重量列里写 `2m`），拒绝跨维度换算 |
| `out_of_range` | 换算后的目标单位精确值超出合理范围（在舍入之前判定） |

## 关键约定

- **别名区分大小写**：只做 NFKC 与空白归一，不做大小写折叠。`KG` 配了别名就是 `kg`，`Kg` 不在别名表里就是「单位不明」，避免把不同单位混为一谈。
- **只舍入一次**：中间值全是精确分数，例如 `-5F` 精确为 `-185/9`（约 `-20.555…`），只在输出时按精度舍入为 `-20.6`；`500.5g → 0.501` 正好落在半值，按远离零进位，并标记 `half_tie`。
- **范围按目标单位判定**：`4000000g = 4000kg` 落在 `0.001–5000 kg` 内算正常；`0.0005kg` 低于下限进异常。
- **公式形如** `y = a · x + b`，例如 `g → kg` 是 `y = 1/1000 · x`，`F → C` 是 `y = 5/9 · x - 160/9`，来源单位本身就是目标单位时为 `y = x`。

## 接口一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/units` | 维度与单位目录 |
| GET/POST | `/api/rulesets` | 规则版本列表 / 保存新版本 |
| GET | `/api/rulesets/latest` | 最新规则 |
| POST | `/api/seed/default-rules` | 写入默认规则（幂等） |
| POST | `/api/batches/preview` | 解析文件 + 建议映射 + 别名冲突（不落库） |
| POST | `/api/batches` | 生成批次（存在未确认别名时 409） |
| GET | `/api/batches` | 批次列表 |
| GET | `/api/batches/{id}` | 批次详情（含规则快照） |
| GET | `/api/batches/{id}/results` | 单元格结果（分页、类别/指标/搜索过滤） |
| GET | `/api/batches/{id}/rows/{row_no}` | 行级追溯（原始行 + 每格轨迹） |
| POST | `/api/batches/{id}/publish` | 发布并锁定 |
| POST | `/api/batches/{id}/recompute` | 基于本批次数据 + 指定规则版本生成派生批次 |
| GET | `/api/batches/{id}/compare/{other}` | 只读比较 |
| GET | `/api/batches/{id}/export/{detail\|exceptions}` | 导出 CSV（UTF-8 BOM，带原始行号） |

## 测试

```bash
.venv/bin/python -m pytest tests -q
```

- `tests/test_processing.py`：解析、精确换算、四舍五入边界、别名大小写、歧义别名确认、跨维度、范围判定、轨迹完整性。
- `tests/test_api.py`：临时 SQLite 上的端到端流程，含独立单位列识别、导出原始行号、发布后快照不变、派生批次与只读比较。

## 示例数据

- `samples/measurements.csv`：小数重量、负温度、别名冲突（`度`）、舍入半值（`500.5g`）、大小写陷阱（`1Kg`）、范围边界（`0.0005kg`、`4000000g`）。
- `samples/with_unit_column.csv`：数值与单位分列（`重量单位` / `温度单位`），含 `度`、`K`、`mg`。
