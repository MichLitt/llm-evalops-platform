# Adapters

Adapters convert raw ingest payloads into `NormalizedOutput`, which the worker
writes to `runs` + `run_metrics`.

## Registered Adapters

| canonical key | file | producer |
|---|---|---|
| `rag/v1` | `adapters/rag_v1.py` | `rag-benchmark-system` `EvalRunReport` |
| `agent/v1` | `adapters/agent_v1.py` | `llm-coding-agent-system` run summary |
| `finetune/v1` | `adapters/finetune_v1.py` | stub — NOT registered; records marked `unsupported` |

## Field Contracts

### `rag/v1`

Source: `EvalRunReport` in `rag-benchmark-system/src/evalops/schema.py`

| `runs` field | source field | nullable? |
|---|---|---|
| `run_id` | `run_id` | required |
| `task_set_id` | `dataset` | required |
| `dataset_version` | `dataset` | required |
| `config_version` | `retriever_mode` | required |
| `model_version` | `generator_model` | required |
| `source_commit` | — | always NULL |
| `wall_duration_ms` | — | always NULL (only per-query averages available) |

Derived metric: `avg_end_to_end_latency_ms = sum(avg_retrieval + avg_rerank + avg_generation + avg_query_expansion)`

### `agent/v1`

Source: `llm-coding-agent-system` `EvalOpsClient` payload

| `runs` field | source field | nullable? |
|---|---|---|
| `run_id` | `run_id` | required |
| `task_set_id` | computed (see below) | conditional |
| `dataset_version` | — | always NULL |
| `config_version` | `preset` | optional |
| `model_version` | `llm_profile` | optional |
| `source_commit` | `git_commit` | optional |
| `wall_duration_ms` | `wall_duration_ms` | optional: NULL when the producer did not record wall time |

**`task_set_id` computation:**
- `run_type = "eval"` and `benchmark_name` + `task_ids` present:
  `sha256(f"{benchmark_name}:{','.join(sorted(task_ids))}")[:16]`
- `run_type = "service"` or fields absent: `NULL` (cannot participate in compare)

**Metrics (`run_metrics`)** — each numeric field becomes a metric row when it is
non-null: `total_steps`, `total_tool_calls`, `tool_success_rate`,
`total_tokens`, `input_tokens`, `output_tokens`, `llm_call_count`,
`estimated_cost_usd`, plus the controlled-evaluation extensions
(`verification_pass_rate`, `tool_retry_rate`, `retrieval_hit_rate`,
`citation_correctness_rate`, `wall_latency_p50_ms`, `wall_latency_p95_ms`)
and the benchmark aggregate `resolved_rate`.

`resolved_rate` (0–1) is the share of `task_ids` that a benchmark's official
grader marked resolved, sent by aggregate reports such as the WP1 SWE-bench
Verified arms (one `agent/v1` report per arm, `run_type = "eval"`). An
aggregate of an external agent that does not time its runs sends
`wall_duration_ms: null`.

Token fields are provider-reported usage. `token_usage_status` (not a metric)
is `provider` when every LLM call reported usage, `partial` when only some did
(token metrics are then lower bounds), and `unavailable` when none did; in that
case the producer sends `null` and no token or cost metric row is written.
Producers never substitute a client-side estimate. `estimated_cost_usd` is
present only when the producer profile configures pricing.

## Adding a New Adapter

1. Create `adapters/{app_type}_v{n}.py` and implement `BaseAdapter.normalize()`.
2. Add `REGISTRY["{app_type}/v{n}"] = YourAdapter()` at the bottom of the file.
3. Add the import to `adapters/__init__.py` side-effect imports.
4. Update this file (ADAPTERS.md) with the field contract.
5. Update `PROJECT_PLAN.md` Sections 3.2 and 7.
6. Add the canonical key and its Pydantic request model to
   `api/ingest.py` `_SCHEMA_MODELS`.

## Gate Rule Ops Reference

| op | semantics | threshold unit |
|---|---|---|
| `gte` / `lte` / `gt` / `lt` | absolute candidate value | metric native unit |
| `delta_abs_gte` / `delta_abs_lte` | `candidate - baseline` | metric native unit |
| `delta_pct_gte` / `delta_pct_lte` | `(candidate - baseline) / |baseline|` | decimal (0.15 = 15%) |

**Boundary conditions:**
- `delta_pct_*` when `baseline == 0`: `percent_delta = NULL` → `passed=False, reason="percent_delta_undefined"`
- Rule references a missing metric: `passed=False, reason="metric_missing"`
  - `required=True` → whole gate `rejected`
  - `required=False` → recorded but does not affect decision
