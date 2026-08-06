# llm-evalops-platform 实现计划

> **状态更新（2026-08-06）：** Phase 2 Agent/RAG MVP 已完成并通过 45 项本地测试；
> 根目录 `scripts/run_three_project_closure.sh` 已验证真实 producer payload、独立 API/worker、
> compare、gate 与 release decision 持久化。Phase 5 review UI 与 bad-case API 仍未完成。

## 1. 项目定位

面向 agent / RAG / post-training 的共享评测、观测、发布平台。  
API-first，单租户，本地部署优先。

本项目在整体路线图中是 **Phase 2**（第 4–5 周），依赖 Phase 1（`llm-coding-agent-system` agent runtime）先完成。核心职责只有 4 件：

1. 接收上游系统的 run 上报（被动 ingest）
2. 标准化指标
3. 跨版本 compare
4. 基于规则的 release gate

> **MVP 不做主动 eval job 调度**。平台不触发 eval 执行，只接收已完成的 run 报告。主动调度是 v2 功能。

---

## 2. 全局时间线

| 周次（全局） | 阶段 | 内容 |
|---|---|---|
| 第 1–3 周 | Phase 1 | `llm-coding-agent-system` agent runtime |
| **第 4 周** | **Phase 2 前半** | **平台骨架 + DB schema + ingest 端点 + 标准化 worker** |
| **第 5 周** | **Phase 2 后半** | **接入 RAG + agent + compare + gate + 集成测试** |
| 第 6–7 周 | Phase 3 | `rag-benchmark-system` → Agent Knowledge Subsystem |
| 第 8 周 | Phase 4 | `coding-llm-finetune` → failure-driven post-training |
| 第 9 周 | Phase 5 | 统一包装、review loop、README 架构图 |

---

## 3. 数据模型

### 3.1 表结构

#### `ingested_reports`
原始上报记录，worker 生命周期挂在此表上。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| app_type | TEXT NOT NULL | `agent` / `rag` / `finetune` |
| schema_version | TEXT NOT NULL | canonical key，格式为 `{app_type}/{version}`，如 `rag/v1` |
| run_id | TEXT NOT NULL | producer 提供的 run 标识 |
| raw_payload | TEXT NOT NULL | 原始 JSON，永不修改，保留审计能力 |
| status | TEXT NOT NULL | `pending` / `processing` / `processed` / `failed` / `unsupported` |
| attempt_count | INTEGER NOT NULL DEFAULT 0 | worker 处理尝试次数 |
| claimed_at | REAL | worker 本次开始处理的时间戳；用于 lease 超时判断 |
| last_error | TEXT | 最近一次处理失败的错误信息 |
| processed_at | REAL | 成功处理的时间戳 |
| received_at | REAL NOT NULL | 平台收到请求的时间戳 |

**唯一约束**：`(app_type, schema_version, run_id)`  
Producer 重试时若已存在相同记录，返回 200 + 已有 `id`，不写重复行。

**注**：`schema_version` 字段值由 API 层从路由参数拼接而成：
```
canonical_key = f"{app_type}/{version}"
# 路由 POST /v1/ingest/rag/v1 → schema_version 存为 "rag/v1"
```
worker 和 adapter 注册均按此 canonical key 路由，与路由路径保持一致。

#### `runs`
标准化后的 run 记录，跨 app_type 统一结构。使用代理主键以避免跨 producer 的 run_id 冲突。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 代理主键，内部 FK 使用此字段 |
| app_type | TEXT NOT NULL | |
| run_id | TEXT NOT NULL | producer 提供的字符串标识 |
| ingest_report_id | INTEGER FK → ingested_reports(id) | 关联原始上报记录 |
| schema_version | TEXT NOT NULL | canonical key，如 `rag/v1` |
| task_set_id | TEXT | compare 校验字段；NULL 则不可参与 compare |
| dataset_version | TEXT | 可为 NULL |
| config_version | TEXT | 可为 NULL |
| model_version | TEXT | 可为 NULL |
| source_commit | TEXT | 可为 NULL |
| primary_artifact_path | TEXT | 可选；其余产物放 artifacts 表 |
| status | TEXT NOT NULL | run 最终状态（来自 producer） |
| wall_duration_ms | INTEGER | |
| created_at | REAL NOT NULL | |

**唯一约束**：`(app_type, run_id)`

> **字段可空性原则**：`task_set_id`、`dataset_version`、`config_version`、`model_version`、`source_commit` 在 `runs` 表均允许 NULL。adapter 只填 producer 实际提供的字段，缺失字段置 NULL，不因字段缺失而拒绝写入。

#### `run_metrics`
每个 run 的各维度指标，kv 结构，支持不同 app_type 的任意指标字段。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| run_pk | INTEGER NOT NULL FK → runs(id) | |
| metric_name | TEXT NOT NULL | 如 `tool_success_rate`、`f1`、`avg_retrieval_latency_ms` |
| metric_value | REAL NOT NULL | |
| created_at | REAL NOT NULL | |

#### `artifacts`

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| run_pk | INTEGER NOT NULL FK → runs(id) | |
| artifact_type | TEXT NOT NULL | 如 `trajectory`、`eval_report`、`bad_cases` |
| artifact_path | TEXT NOT NULL | |
| created_at | REAL NOT NULL | |

#### `compare_sessions`

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| app_type | TEXT NOT NULL | compare 要求两个 run 同 app_type |
| task_set_id | TEXT NOT NULL | compare 要求两个 run 同 task_set_id |
| baseline_run_id | TEXT NOT NULL | 对应 runs.run_id（app_type 相同） |
| candidate_run_id | TEXT NOT NULL | 对应 runs.run_id（app_type 相同） |
| result_json | TEXT | per-metric absolute delta 和 percent delta |
| created_at | REAL NOT NULL | |

#### `release_decisions`

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| compare_session_id | INTEGER NOT NULL FK → compare_sessions(id) | |
| rules_json | TEXT NOT NULL | 执行时使用的规则快照 |
| decision | TEXT NOT NULL | `promoted` / `rejected` |
| detail_json | TEXT NOT NULL | per-rule 通过/拒绝明细 |
| created_at | REAL NOT NULL | |

#### `bad_case_tags`
第 4 周建表，第 9 周填充内容。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| run_pk | INTEGER NOT NULL FK → runs(id) | |
| case_id | TEXT NOT NULL | producer 提供的样本标识 |
| tag | TEXT NOT NULL | failure mode 标签 |
| note | TEXT | 可选备注 |
| created_at | REAL NOT NULL | |

---

### 3.2 Producer 字段契约

每个 producer 实际能提供的字段不同。adapter 按此表填充 `runs`，缺失字段置 NULL。

#### RAG `rag/v1`（来源：`EvalRunReport`）

| `runs` 字段 | 来源字段 | 必填？ | 说明 |
|---|---|---|---|
| `run_id` | `run_id` | 是 | |
| `task_set_id` | `dataset` | 是 | 数据集名作为任务集标识；两次相同数据集的 run 可 compare |
| `dataset_version` | `dataset` | 是 | 同上（`dataset` 兼作版本标识） |
| `config_version` | `retriever_mode` | 是 | 仅检索配置；不与 model_version 混用 |
| `model_version` | `generator_model` | 是 | |
| `source_commit` | （不可用） | NULL | RAG report 不含 git commit |
| `primary_artifact_path` | （不可用） | NULL | |
| `wall_duration_ms` | （不可用） | NULL | `EvalRunReport` 只有 per-query 平均延迟，无 run 级墙钟时长，不可伪造 |

**RAG 延迟指标处理**：`EvalRunReport` 中的四个平均延迟字段（`avg_retrieval_latency_ms`、`avg_rerank_latency_ms`、`avg_generation_latency_ms`、`avg_query_expansion_latency_ms`）全部作为独立指标存入 `run_metrics`，并额外派生一条：

```
avg_end_to_end_latency_ms = sum(avg_retrieval, avg_rerank, avg_generation, avg_query_expansion)
```

此派生值存入 `run_metrics`，不写入 `runs.wall_duration_ms`，以保持该字段在 agent 和 rag 两个 app_type 下语义一致（均为真实 run 墙钟时长）。

#### Agent `agent/v1`（来源：`RunRecordModel` / `RunStateStore` / eval manifest）

| `runs` 字段 | 来源字段 | 必填？ | 说明 |
|---|---|---|---|
| `run_id` | `run_id` | 是 | |
| `task_set_id` | 见下方说明 | 条件 | |
| `dataset_version` | （不可用） | NULL | agent 不针对固定数据集 |
| `config_version` | `preset` | 否 | preset 名作为配置版本 |
| `model_version` | `llm_profile` | 否 | llm profile 名作为模型版本 |
| `source_commit` | `git_commit` | 否 | |
| `primary_artifact_path` | （不可用） | NULL | |
| `wall_duration_ms` | `wall_duration_ms` | 是 | service 层已计算 |

**`task_set_id` 生成规则**：

- **Eval/benchmark run**（上报时携带 `benchmark_name` + `task_ids`）：
  ```python
  task_set_id = sha256(f"{benchmark_name}:{','.join(sorted(task_ids))}").hexdigest()[:16]
  ```
  相同 benchmark + 相同任务集的两次 run 得到相同 `task_set_id`，可参与 compare。

- **Service API run**（`experiment_id = "service"`，无固定任务集）：
  `task_set_id = NULL`，不可参与 compare。

> **结论**：agent EvalOpsClient 上报时必须区分这两种 run 类型并附带对应字段；adapter 不能简单将 `experiment_id` 映射为 `task_set_id`。

> **MVP 验收原则**：平台不因 NULL 字段拒绝 run。`task_set_id` 为 NULL 的 run 不可参与 compare，其余字段 NULL 只影响展示，不影响 ingest 或 gate 流程。

---

### 3.3 设计原则

- `ingested_reports` 是原始审计层，`raw_payload` 永不修改
- `runs` 只由 worker 写入，API 只读；外部 API 用 `(app_type, run_id)` 定位，内部 FK 用 `runs.id`
- `primary_artifact_path` 是快速访问字段；`artifacts` 表存完整产物列表，两者不冲突
- compare 前置校验：两个 run 必须满足 `app_type` 相同 + `task_set_id` 相同且非 NULL，由 compare endpoint 机器校验

---

## 4. 系统架构

```
Producer (RAG / Agent / Finetune)
    │
    │  POST /v1/ingest/{app_type}/{version}
    │  canonical_key = f"{app_type}/{version}"  ← 由 API 层拼接后存入 schema_version
    ▼
┌─────────────────────────────────┐
│  Ingest API                     │
│  - 校验 Pydantic schema         │
│  - 幂等写入 ingested_reports    │
│    (unique: app_type+schema_version+run_id)   │
│  - 返回 202 Accepted            │
└────────────────┬────────────────┘
                 │  status = pending
                 ▼
┌─────────────────────────────────┐
│  Normalization Worker           │
│  - 轮询 pending 记录            │
│  - 同时 reclaim 超时的          │
│    processing 记录（见第 6 节） │
│  - 按 schema_version 路由       │
│    到对应 adapter               │
│  - 写入 runs + run_metrics      │
│  - 更新 ingested_reports.status │
└─────────────────────────────────┘

Consumer API
  GET  /v1/runs?app_type=&task_set_id=&status=&limit=&offset=
  GET  /v1/runs/{app_type}/{run_id}
  GET  /v1/runs/{app_type}/{run_id}/metrics
  GET  /v1/runs/{app_type}/{run_id}/artifacts
  POST /v1/compare       ← 校验 app_type + task_set_id 一致且非 NULL
  POST /v1/gate          ← 基于规则输出 promoted / rejected
```

---

## 5. Gate 规则 Schema（显式定义）

gate endpoint 接受规则列表，每条规则格式：

```json
{
  "metric": "tool_success_rate",
  "op": "gte",
  "threshold": 0.8,
  "required": true
}
```

支持的 `op`（分为绝对值比较和变化量比较两组）：

| op | 类型 | 含义 | threshold 单位 |
|---|---|---|---|
| `gte` / `lte` / `gt` / `lt` | 绝对值 | candidate 指标值 vs threshold | 指标原始单位 |
| `delta_abs_gte` / `delta_abs_lte` | 绝对差 | `candidate - baseline` vs threshold | 指标原始单位 |
| `delta_pct_gte` / `delta_pct_lte` | 百分比变化 | `(candidate - baseline) / |baseline|` vs threshold | 小数（0.15 = 15%） |

> **不提供混义的 `delta_gte` / `delta_lte`**。实现方按绝对差还是百分比，调用方按另一种理解，gate 结论会漂移。两组 op 语义严格分离。

- `required: true`：任意一条失败即整体 rejected
- `required: false`：失败时记录在 detail 但不影响最终决策

**示例规则集（agent/v1）**：

```json
[
  {"metric": "tool_success_rate",  "op": "gte",           "threshold": 0.8,   "required": true},
  {"metric": "task_success_rate",  "op": "delta_pct_gte", "threshold": -0.02, "required": true},
  {"metric": "total_tokens",       "op": "delta_pct_lte", "threshold": 0.15,  "required": false},
  {"metric": "wall_duration_ms",   "op": "lte",           "threshold": 120000,"required": false}
]
```

说明：第 2 条表示"成功率最多允许下降 2%"；第 3 条表示"token 用量最多允许增加 15%"，阈值均为小数比例。

规则引擎用 Python dict 驱动，不需要 DSL，新增 op 只需在 `services/gate.py` 里加一个分支。

**边界条件（实现必须遵守）**：

| 场景 | 处理方式 |
|---|---|
| `delta_pct_*` 且 `baseline == 0` | `percent_delta = NULL`；`required=true` 规则视为 `passed=false, reason="percent_delta_undefined"`；`required=false` 规则同样记 `passed=false, reason="percent_delta_undefined"` |
| 规则引用的 metric 在 candidate 或 baseline run 中不存在 | `required=true`：规则视为 `passed=false, reason="metric_missing"`，整体 `rejected`；`required=false`：记录 `passed=false, reason="metric_missing"`，不影响整体决策 |

> 不对缺失 metric 抛 422，因为调用方在提交规则时可能无法预知 run 覆盖了哪些指标。gate 应总能输出一个可追溯的决策，而不是在边界条件下崩溃。

---

## 6. 第 4 周（全局）工作项

**目标**：平台骨架 + DB + ingest 端点 + worker 可运行

- [x] 初始化 repo（pyproject.toml + uv + FastAPI + Pydantic + SQLite）
- [x] 实现 DB schema 和 migration 脚本（`storage/migrations/`）
- [x] 实现 `POST /v1/ingest/rag/v1`（含幂等约束）
- [x] 实现 `POST /v1/ingest/agent/v1`（含幂等约束）
- [x] 实现 `POST /v1/ingest/finetune/v1`（接受 payload，worker 遇到此 schema_version 直接标 `unsupported`，不进入重试队列）
- [x] 实现标准化 worker 进程（`worker/normalizer.py`），含 lease/reclaim 机制：
  - 每轮轮询同时处理两类记录：
    1. `status = 'pending'`
    2. `status = 'processing' AND claimed_at < now - LEASE_TIMEOUT_SECS`（默认 60s）
  - claim 时：`UPDATE SET status='processing', claimed_at=now`（单条 UPDATE，原子占位）
  - 成功后：`UPDATE SET status='processed', processed_at=now`
  - 失败且 `attempt_count < MAX_RETRIES`（默认 3）：`UPDATE SET status='pending', attempt_count+=1, last_error=...`
  - 达到最大重试次数：`UPDATE SET status='failed'`
  - 无对应 adapter：`UPDATE SET status='unsupported'`
- [x] 实现 `GET /v1/runs`（支持 query 参数：`app_type`、`task_set_id`、`status`、`limit`、`offset`）
- [x] 实现 `GET /v1/runs/{app_type}/{run_id}`
- [x] 在 ingest endpoint 和 worker 加结构化日志（JSON，字段：`run_id`、`app_type`、`schema_version`、`latency_ms`、`status`、`error`）

---

## 7. 第 5 周（全局）工作项

**目标**：两个 producer 接入 + compare + gate + 集成测试

### 7.1 接入 rag-benchmark-system

RAG 已有 `EvalOpsClient` + `EvalRunReport`（`schema_version = "rag/v1"`），迁移成本最低。

- [x] 实现 `adapters/rag_v1.py`，字段映射（依据 3.2 节契约）：

  | `EvalRunReport` 字段 | `runs` 字段 | `run_metrics` 指标名 |
  |---|---|---|
  | `run_id` | `run_id` | — |
  | `dataset` | `task_set_id` + `dataset_version` | — |
  | `retriever_mode` | `config_version` | — |
  | `generator_model` | `model_version` | — |
  | — | `source_commit = NULL` | — |
  | `em` | — | `em` |
  | `f1` | — | `f1` |
  | `recall_at_k` | — | `recall_at_k` |
  | `avg_faithfulness` | — | `avg_faithfulness` |
  | `hallucination_rate` | — | `hallucination_rate` |
  | `avg_retrieval_latency_ms` | — | `avg_retrieval_latency_ms` |
  | `avg_rerank_latency_ms` | — | `avg_rerank_latency_ms` |
  | `avg_generation_latency_ms` | — | `avg_generation_latency_ms` |
  | `avg_query_expansion_latency_ms` | — | `avg_query_expansion_latency_ms` |
  | （派生）四项平均延迟之和 | — | `avg_end_to_end_latency_ms` |
  | `total_generation_cost_usd` | — | `total_generation_cost_usd` |
  | `avg_generation_cost_usd` | — | `avg_generation_cost_usd` |
  | — | `wall_duration_ms = NULL` | — |

- [x] 把 RAG 的 `EvalOpsClient` endpoint 指向本平台
- [x] 端到端验证：RAG 跑完一次 eval → 上报 → 平台可查询

### 7.2 接入 llm-coding-agent-system

`RunRecordModel`（`schemas.py`）没有 `dataset_version` 和 `model_version` 独立字段，按 3.2 节契约处理：`dataset_version = NULL`，`model_version` 取 `llm_profile`。

- [x] 在 `llm-coding-agent-system` 里新增 `coder_agent/evalops/client.py`：
  - fire-and-forget HTTP POST
  - 超时（建议 3s）后静默丢弃，不抛异常，不阻塞 agent run
  - 失败时写本地日志，run 结果保留在本地 SQLite
- [x] 挂在 `RunStateStore.finish_run` 之后触发上报
- [x] 上报字段（MVP）：
  - 所有 run 类型共有：`run_id`、`run_type`（`"eval"` 或 `"service"`）、`status`、`total_steps`、`total_tool_calls`、`tool_success_rate`、`total_tokens`、`termination_reason`、`wall_duration_ms`、`git_commit`、`preset`、`llm_profile`
  - eval run 额外携带：`benchmark_name`、`task_ids`（列表）
  - service run：`benchmark_name` 和 `task_ids` 不填
- [x] 实现 `adapters/agent_v1.py`，字段映射（依据 3.2 节契约）：

  | 上报字段 | `runs` 字段 | `run_metrics` 指标名 | 说明 |
  |---|---|---|---|
  | `run_id` | `run_id` | — | |
  | `benchmark_name` + `task_ids` | `task_set_id` | — | eval run：`sha256(f"{benchmark_name}:{','.join(sorted(task_ids))}")[:16]`；service run：`NULL` |
  | `preset` | `config_version` | — | |
  | `llm_profile` | `model_version` | — | |
  | `git_commit` | `source_commit` | — | |
  | — | `dataset_version = NULL` | — | agent 无固定数据集 |
  | `status` | `status` | — | |
  | `wall_duration_ms` | `wall_duration_ms` | — | |
  | `total_steps` | — | `total_steps` | |
  | `total_tool_calls` | — | `total_tool_calls` | |
  | `tool_success_rate` | — | `tool_success_rate` | |
  | `total_tokens` | — | `total_tokens` | |

### 7.3 Compare + Gate

- [x] 实现 `POST /v1/compare`：
  - 前置校验：两个 `(app_type, run_id)` 均存在，且 `app_type` 相同、`task_set_id` 相同且非 NULL；不满足返回 422 并说明原因
  - 计算每个指标的 `absolute_delta = candidate - baseline` 和 `percent_delta = (candidate - baseline) / |baseline|`
  - 写入 `compare_sessions.result_json`
- [x] 实现 `POST /v1/gate`：
  - 接受 `compare_session_id` + `rules[]`
  - 按规则 schema（第 5 节）执行，`required: true` 的规则任意失败则整体 `rejected`
  - 写入 `release_decisions`
  - 响应体：`{ decision, detail: [{metric, op, threshold, actual, passed}] }`

### 7.4 集成测试（MVP 验收）

- [x] `tests/integration/test_rag_ingest_to_gate.py`：

  ```
  POST /v1/ingest/rag/v1 (run_a, baseline)
  POST /v1/ingest/rag/v1 (run_b, candidate)
  触发 worker（测试模式下同步调用）
  GET  /v1/runs/rag/{run_a} → 校验字段和 NULL 语义
  POST /v1/compare          → 校验 absolute_delta 和 percent_delta
  POST /v1/gate             → 校验 decision + per-rule detail
  ```

- [x] `tests/integration/test_agent_ingest.py`：上报 + 查询 + NULL 字段校验
- [x] `tests/integration/test_idempotent_ingest.py`：同一 run_id 重复上报，确认返回 200 且 DB 无重复行

---

## 8. 第 9 周（Phase 5）补充

**目标**：review loop + 可演示前端 + README 架构图

- [ ] `GET /v1/runs/{app_type}/{run_id}/bad-cases`
- [ ] `POST /v1/runs/{app_type}/{run_id}/bad-cases/{case_id}/tags`
- [ ] compare_session 扩展 per-case 对比视图
- [ ] 最小前端：静态 HTML + fetch，展示 run list + compare 结果（不做 SPA）
- [x] README 架构图：以 `ingest → normalize → compare → gate → release decision` 为主干，突出 `release_decisions` 是平台核心产出而非附属功能

---

## 9. 仓库结构

```text
llm-evalops-platform/
├── pyproject.toml
├── src/llm_evalops_platform/
│   ├── api/
│   │   ├── ingest.py          — POST /v1/ingest/{app_type}/{version}
│   │   ├── runs.py            — GET /v1/runs, GET /v1/runs/{app_type}/{run_id}
│   │   ├── compare.py         — POST /v1/compare
│   │   └── gate.py            — POST /v1/gate
│   ├── worker/
│   │   └── normalizer.py      — 轮询 + reclaim + 标准化写入
│   ├── domain/
│   │   ├── runs.py            — Run / RunMetric 领域模型
│   │   ├── compare.py         — CompareSession
│   │   └── gate.py            — ReleaseDecision + 规则引擎
│   ├── storage/
│   │   ├── db.py              — SQLite 连接管理
│   │   └── migrations/        — SQL schema 文件
│   ├── adapters/
│   │   ├── base.py            — Adapter 基类 + registry
│   │   ├── rag_v1.py          — EvalRunReport → runs + run_metrics
│   │   ├── agent_v1.py        — agent run summary → runs + run_metrics
│   │   └── finetune_v1.py     — stub（worker 遇到此 key 标 unsupported）
│   ├── services/
│   │   ├── compare.py         — compare 业务逻辑
│   │   └── gate.py            — 规则引擎（delta_abs_* / delta_pct_* / 绝对值）
│   └── schemas/
│       ├── ingest.py          — Pydantic ingest request schemas
│       └── responses.py       — Pydantic response schemas
├── scripts/
│   ├── start_api.py
│   └── start_worker.py
├── tests/
│   ├── integration/
│   │   ├── test_rag_ingest_to_gate.py
│   │   ├── test_agent_ingest.py
│   │   └── test_idempotent_ingest.py
│   └── unit/
├── docs/
└── .env.example
```

---

## 10. MVP 交付标准

1. `rag-benchmark-system` 可以把一次 eval run 上报到平台并被查询到。
2. `llm-coding-agent-system` 可以把一次 agent run summary 上报到平台并参与 compare。
3. 平台可以按 `(app_type, run_id)` 查详情，按 `app_type` / `task_set_id` / `status` 筛选 runs，对两个版本做 compare，输出一次 gate 决策。
4. 每个 run 都能追到 `schema_version` 和 `task_set_id`；`config_version`、`model_version`、`source_commit`、`dataset_version` 按 producer 实际能力填充，允许部分为 NULL，不因 NULL 字段失败。
5. 集成测试 `test_rag_ingest_to_gate.py` 全程跑通（ingest → normalize → compare → gate → decision）。
6. 幂等性：同一 run_id 重复上报不产生重复 run，`test_idempotent_ingest.py` 验证。
7. 平台 worker 不可用时，ingest endpoint 仍接收 payload 写入 `ingested_reports`（`status=pending`）；worker 恢复后自动 reclaim 并补处理（含超时 `processing` 记录）。
8. 平台整体不可用时，两个上游系统的 EvalOpsClient 失败静默，run 结果保留在各自本地存储，不阻塞主流程。

---

## 11. 明确不做

- 企业级多租户和权限系统
- 重前端 BI 产品
- 全量 step/token trace 仓库
- 训练调度平台
- 通用 LLMOps 功能堆砌
- **主动 eval job 调度**（平台触发执行、管理 job 生命周期）→ v2
- `jobs` 表 → v2
- 混义的 `delta_gte` / `delta_lte` op

---

## 12. 一致性检查

| 检查项 | 结论 |
|---|---|
| `jobs` 表已移除，worker 生命周期挂 `ingested_reports.status` | ✓ 3.1 + 6 节一致 |
| `ingested_reports` 有 status / attempt_count / claimed_at / last_error / processed_at | ✓ 3.1 节 |
| worker 含 lease/reclaim（claimed_at + 超时回 pending）| ✓ 6 节工作项 |
| 幂等约束 `(app_type, schema_version, run_id)` | ✓ 3.1 节；验收标准第 6 条 + 集成测试覆盖 |
| `runs` 使用代理主键 `id`，外部 API 用 `(app_type, run_id)` | ✓ 3.1 节；跨 producer 同名 run_id 不冲突 |
| `run_metrics` / `artifacts` / `bad_case_tags` FK 使用 `runs.id`（字段名 run_pk）| ✓ 3.1 节 |
| compare 用 `task_set_id` 做机器校验，NULL 则拒绝 compare | ✓ 3.3 节原则 + 7.3 节 |
| `runs` 中 task_set_id / config_version 等允许 NULL | ✓ 3.1 节字段定义 + 3.2 节契约 |
| MVP 验收标准第 4 条不要求所有字段非 NULL | ✓ 10 节 |
| `runs.artifact_path` 替换为 `primary_artifact_path`（nullable）| ✓ 3.1 节 |
| ingest 路由 `{app_type}/{version}` → canonical_key 拼接规则明确 | ✓ 3.1 节注 + 4 节架构图 |
| adapter registry 按 canonical_key 路由，与路由路径一致 | ✓ 4 节 + 仓库结构 `adapters/base.py` |
| `finetune/v1` 无 adapter → 标 `unsupported`，不进重试队列 | ✓ 6 节工作项 |
| gate op 分为绝对值、delta_abs_*、delta_pct_*，无混义 delta | ✓ 5 节 + 11 节不做列表 |
| `GET /v1/runs` 支持 app_type / task_set_id / status / limit / offset | ✓ 4 节架构图 + 6 节工作项 |
| agent 系统接入需新写 EvalOpsClient | ✓ 7.2 节 |
| 结构化日志含 schema_version 字段 | ✓ 6 节 |
| 集成测试第 5 周交付，覆盖幂等 + NULL 字段 | ✓ 7.4 节 |
| review loop + README 架构图推迟第 9 周 | ✓ 8 节 |
| `bad_case_tags` 第 4 周建表、第 9 周使用 | ✓ 3.1 节 + 6/8 节 |
| 周次全部使用全局绝对周次 | ✓ 2 节时间线 |
| agent service run `task_set_id = NULL`，不误入 compare | ✓ 3.2 节契约 + 7.2 节 adapter 映射 |
| agent eval run `task_set_id = sha256(benchmark+task_ids)[:16]` | ✓ 3.2 节 + 7.2 节 |
| `rag/v1` `wall_duration_ms = NULL`，不伪造墙钟时长 | ✓ 3.2 节 + 7.1 节 |
| RAG 延迟派生指标 `avg_end_to_end_latency_ms` 进 run_metrics | ✓ 3.2 节 + 7.1 节 |
| `delta_pct_*` baseline=0 时 `percent_delta=NULL`，gate 记 reason | ✓ 5 节边界条件表 |
| gate 规则引用缺失 metric 时有明确处理语义 | ✓ 5 节边界条件表 |
