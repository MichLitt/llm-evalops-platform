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
| `wall_duration_ms` | `wall_duration_ms` | required |

**`task_set_id` computation:**
- `run_type = "eval"` and `benchmark_name` + `task_ids` present:
  `sha256(f"{benchmark_name}:{','.join(sorted(task_ids))}")[:16]`
- `run_type = "service"` or fields absent: `NULL` (cannot participate in compare)

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
