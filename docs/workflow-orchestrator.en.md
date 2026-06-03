# Workflow Orchestrator (Beta)

**[中文文档](workflow-orchestrator.zh.md)**

> **Status: Beta** — Core paths are ready for production validation, but the API, graph DSL, and UI may still change. See [Known limitations](#8-known-limitations-beta) below.

MChat Workflow chains multiple Skills into reusable pipelines with **manual**, **scheduled**, and **channel message** triggers. This document is the implementation reference; endpoint details also appear in [api.en.md — Workflows (Beta)](./api.en.md#workflows-beta).

Screenshots: [Product tour — Workflow](product-tour.en.md#workflow-orchestration-beta) (list page and graph editor, EN/ZH UI).

---

## 1. Concepts

| Concept | Description |
|---------|-------------|
| **Skill** | Smallest execution unit (tool, function, webhook) |
| **Workflow** | A flow built from Skills; supports linear steps or a `graph_json` DAG |
| **Channel** | Traffic entry point (Web / WeChat / Telegram, etc.); defines *who* triggers |
| **Schedule** | Time-based trigger; defines *when*; can bind to a Workflow |

**Relationship**: Channel = scenario, Workflow = process, Schedule = timing.

---

## 2. Shipped capabilities (Beta)

### 2.1 Workflow management

- CRUD, enable/disable, manual `run-once`
- **Linear steps**: executed by `order_index`; supports `${input.xxx}` / `${steps.step_key.result.xxx}` templates
- **Graph (DAG)**: when valid `graph_json` exists, the graph executor takes precedence
- Run history and detail: `step_runs` (linear) / `node_runs` (graph)

### 2.2 Graph editor (React Flow)

- Node types: `start` / `skill` / `condition` / `approval` / `merge` / `end`
- **Canvas tools**: `V` pointer / `H` pan (ComfyUI-style), toggle from toolbar
- DSL validation: at least one start and end; edge and node legality checks
- Conditional branches, parallel batches, per-step retry and timeout
- Approval nodes: run pauses (`paused`); resume after human approve/reject
- Failure/rejection alert webhook (see [Configuration](#6-configuration))

### 2.3 Channel trigger rules (Phase 2.x)

- Bind multiple Workflows per channel; trigger by priority and match rules
- `match_type`: `all` / `contains` / `regex`
- `workflow_dispatch_mode`: `all` / `first_match`
- Rule preview, hit explanation, snippet highlighting
- Rule JSON import/export, hit statistics (Admin → **Channels** → workflow trigger rules)
- Rule template API remains; admin UI for templates not exposed yet (use import/export)

### 2.4 Complex report orchestration (patent multi-dimension)

For pipelines like *search → parallel analysis → merge → charts → export*:

- **Merge node**: waits for all upstream branches, merges into `sections` for downstream nodes
- **Skill library groups**: search / analyze / visualize / export
- **Payload mapper**: visual editor for `payload_template`; supports `${input.*}`, `${nodes.<id>.*}`
- **Built-in templates**:
  - `Patent Multi-Dimension Report` (`patent_report_multidim_en`) — search/analysis → `patent-search`; charts/export → `patent-report` (**external skill repo**, see [patent-workflow-showcase.zh.md](./patent-workflow-showcase.zh.md))
  - `专利多维分析报表` (`patent_report_multidim`) — same topology as the English template
- **Patent node presets**: drag from the left sidebar; skill names from `GET /workflows/showcase-config` (env-configurable)
- **Bind by `skill_name`**: templates may reference `patent-search`; resolved to the current user's `skill_id` on save/create
- **Run form**: `input_fields` on the start node (keyword, industry, etc.); modal on execute

### 2.5 Custom templates (My templates)

Beyond built-ins like `patent_report_multidim`, you can author and reuse graphs in the admin UI:

1. **New workflow** → **Graph mode** — drag start / skill / merge / end nodes, wire edges, set `payload_template`
2. **Save graph** (top-right in the editor)
3. On the workflow list, click **Save as template** and enter name/description
4. Template appears under **My templates**; **Use this template** creates a new workflow with the same topology

**Storage rules**:

- Templates live in `skill_workflow_templates` (per-user isolation)
- Export **strips `skill_id`, keeps `skill_name`** — same as built-ins for cross-workflow reuse
- Creating from a template still resolves `skill_name` → installed skills for the current user

**API**:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/workflows/templates?locale=en` | Built-in + my templates |
| POST | `/api/workflows/{workflow_id}/save-as-template` | Save workflow graph as template |
| DELETE | `/api/workflows/templates/{template_id}` | Delete my template (built-ins cannot be deleted) |
| POST | `/api/workflows/from-template/{template_id}` | Create workflow from built-in or my template |

### Skill i18n

Skill `config` can declare display names; the workflow sidebar and node cards follow **UI language** (binding still uses `skill.name`):

```yaml
# SKILL.md frontmatter or config after install
i18n:
  zh:
    title: 专利检索
    description: 检索、分析与导出
  en:
    title: Patent Search
    description: Search, analysis and export
```

Flat form also works: `display_name: { zh: "专利检索", en: "Patent Search" }`.

OpenClaw `patent-search` `locales.zh` / `locales.en` blocks are auto-mapped to `config.i18n` on load (`name`/`title` → `title`, `description` → `description`).

### Reusing `patent-search` for analysis nodes

`patent-search` exposes sub-commands — **no separate skill per dimension**:

| Workflow node role | patent-search call |
|--------------------|-------------------|
| Search | `command: search`, `query: ${input.keyword}` |
| Applicant analysis | `command: analysis`, `dimension: applicant` |
| Year trend | `command: analysis`, `dimension: applicationYear` |
| Region / province | `command: analysis`, `dimension: province` |
| Legal status | `command: analysis`, `dimension: legalStatus` |
| IPC classification | `command: analysis`, `dimension: ipc` |
| Chart | `command: chart`, `sections: ${nodes.merge.sections}` |
| Excel | `command: excel`, `sections: ${nodes.merge.sections}` |
| Word / PPT | `command: word` / `ppt`, optional `charts: ${nodes.chart.charts}` |
| Full export | `command: all` (chart + Excel + Word + PPT) |

The same skill may appear many times in a DAG; each node differs by `payload_template`. Charts and Office export use the **`patent-report`** skill (`skills/patent-report/`).

Recommended skill names:

| Role | Skill name | Notes |
|------|------------|-------|
| Search / analysis dimensions | `patent-search` | `search` / `analysis` + dimension |
| Chart / Excel / Word / PPT | `patent-report` | `chart` / `excel` / `word` / `ppt` / `all` |

> **Editor presets**: drag from **Patent node presets** in the left sidebar; analysis nodes use `patent-search`, chart/export nodes use `patent-report`.

Set `workflow_role` in skill `config`: `search` | `analyze` | `visualize` | `export` to influence library grouping.

### 2.6 Schedules

- Skill Schedule can trigger a Workflow (not only a single Skill)
- Standalone Worker process polls schedules (`WORKER_ENABLED=true`)

---

## 3. Data model

| Table | Purpose |
|-------|---------|
| `skill_workflows` | Workflow definition (includes `graph_json`) |
| `skill_workflow_steps` | Linear steps |
| `skill_workflow_runs` | Run instances |
| `skill_workflow_step_runs` | Linear step runs |
| `skill_workflow_approvals` | Approval queue |
| `channel_workflow_bindings` | Channel ↔ workflow bindings and match rules |
| `skill_schedules` | Schedule trigger config |

---

## 4. Execution model

### Linear mode

1. Execute steps by `order_index`
2. Render `payload_template`, then call `execute_skill()`
3. Write `step_run`; follow `on_error` (`stop` / `continue`) to halt or continue

### Graph mode (DAG)

1. Topological sort, execute in batches
2. `skill` nodes call Skills; `condition` branches by edge label (`true` / `false`)
3. `approval` nodes pause the run and create approval records
4. Aggregate `node_runs` and final `output_payload`

---

## 5. API index

Full request/response shapes: [API docs — Workflows (Beta)](./api.en.md#workflows-beta).

**Workflows**

- `GET/POST /api/workflows`
- `PATCH/DELETE /api/workflows/{workflow_id}`
- `GET/PUT /api/workflows/{workflow_id}/steps`
- `POST /api/workflows/{workflow_id}/run-once`
- `GET /api/workflows/runs/list`
- `GET /api/workflows/runs/{run_id}`
- `POST /api/workflows/runs/{run_id}/resume`

**Approvals**

- `GET /api/workflows/approvals/pending`
- `POST /api/workflows/approvals/{approval_id}/approve|reject`

**Channel rules**

- `GET/PUT /api/channels/{channel_id}/workflows`
- `POST /api/channels/{channel_id}/workflows/preview`
- `GET /api/channels/{channel_id}/workflows/export`
- `POST /api/channels/{channel_id}/workflows/import`
- `GET /api/channels/{channel_id}/workflows/stats`
- `GET/POST/DELETE /api/channels/templates/workflow`
- `POST /api/channels/{channel_id}/workflows/apply-template/{template_id}`

**Schedules**

- `GET/POST/PATCH/DELETE /api/skill-schedules`
- `POST /api/skill-schedules/{id}/trigger`

---

## 6. Configuration

| Variable / setting | Description |
|--------------------|-------------|
| `WORKFLOW_ALERT_WEBHOOK_URL` | POST JSON alert on workflow failure / approval rejection |
| `workflow.alert_webhook_url` | Same as above; overridable in system settings |
| `WORKER_ENABLED` | Start background Worker (schedules, etc.) |
| `WORKER_TIMEZONE` | Worker timezone, default `Asia/Shanghai` |

---

## 7. Admin UI entry points

- Admin → **Workflows (Beta)**: list, step JSON, graph editor, run history, pending approvals
- Admin → **Skill schedules**: bind Workflow or Skill
- Admin → **Channels**: workflow bindings and rule debugging

URL (local dev): `http://localhost:5173/admin/workflows`

---

## 8. Known limitations (Beta)

- Graph editor UX is still evolving; validate complex DAGs with linear steps first
- Alerts are primarily webhook / optional SMS; **in-app inbox notifications** (unread + Admin WS) are described in [inbox-notifications.zh.md](inbox-notifications.zh.md) and not implemented yet
- Edge cases for parallel nodes and condition expressions need real-workload validation
- During Beta, `graph_json` schema may iterate in minor versions — export backups before upgrades

---

## 9. Roadmap

| Phase | Scope | Status |
|-------|-------|--------|
| P1 | Linear Workflow + run logs | ✅ |
| P2 | Schedule / Channel triggers | ✅ |
| P2.5–2.8 | Rule matching, preview, explanation, highlighting | ✅ |
| P2.9 | Template library, import/export, hit stats | ✅ |
| P3.0–3.5 | Graph DSL, React Flow, DAG, approval, resume | ✅ Beta |
| Next | Run replay on canvas, ComfyUI-style node cards, eval & A/B | Planned |

See also [Product roadmap — Workflow](roadmap.en.md#8-workflow-orchestration-beta).

---

## 10. Related code

| Area | Path |
|------|------|
| API | `src/backend/app/api/workflow.py` |
| Service | `src/backend/app/services/workflow_service.py` |
| Models | `src/backend/app/models/workflow.py` |
| Graph editor | `src/frontend/src/components/workflow/WorkflowGraphEditor.tsx` |
| Admin page | `src/frontend/src/pages/WorkflowsPage.tsx` |
| Worker | `src/backend/app/worker/` |
