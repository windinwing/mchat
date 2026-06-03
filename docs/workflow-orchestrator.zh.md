# Workflow 编排器（Beta）

**[English](workflow-orchestrator.en.md)** · 本文档为中文译本；实现细节以英文版与代码为准。

> **状态：Beta** — 核心链路已可用于生产验证，但 API、图 DSL 与 UI 仍可能调整。详见下文「已知限制」。

MChat Workflow 用于将多个 Skill 编排为可复用流程，统一支撑**手动触发**、**定时触发**与**频道消息触发**。设计文档与实现以代码为准；API 明细见 [api.zh.md](./api.zh.md#工作流-beta)（英文 API 索引见 [api.en.md — Workflows](./api.en.md#workflows-beta)）。

界面截图见 [产品导览 · Workflow](product-tour.zh.md#workflow-编排beta)（含中英文列表页与图编辑器）。

---

## 1. 概念

| 概念 | 说明 |
|------|------|
| **Skill** | 最小执行单元（工具、函数、Webhook） |
| **Workflow** | 由 Skill 组成的流程；支持线性步骤或 `graph_json` DAG |
| **Channel** | 流量入口（Web / 微信 / Telegram 等）；决定「谁在触发」 |
| **Schedule** | 时间调度；决定「何时触发」，可绑定 Workflow |

**关系**：Channel 是场景，Workflow 是流程，Schedule 是时机。

---

## 2. 已落地能力（Beta）

### 2.1 工作流管理

- CRUD、启停、手动 `run-once`
- **线性步骤**：`order_index` 顺序执行，支持 `${input.xxx}` / `${steps.step_key.result.xxx}` 模板
- **图编排（DAG）**：存在有效 `graph_json` 时优先走图执行器
- 运行记录与详情：`step_runs`（线性）/ `node_runs`（图）

### 2.2 图编排（React Flow）

- 节点类型：`start` / `skill` / `condition` / `approval` / `merge` / `end`
- **画布工具**：`V` 指针 / `H` 拖拽平移（ComfyUI 风格），工具栏可切换
- DSL 校验：至少一个 start 与 end，边与节点合法性检查
- 条件分支、并行批次、步骤级重试与超时
- 审批节点：运行暂停（`paused`），人工批准/拒绝后可续跑
- 失败/拒绝告警 Webhook（见配置）

### 2.3 频道触发规则（Phase 2.x）

- 频道绑定多个 Workflow，按优先级与匹配规则触发
- `match_type`：`all` / `contains` / `regex`
- `workflow_dispatch_mode`：`all` / `first_match`
- 规则预览、命中原因解释、片段高亮
- 规则预览、命中原因解释
- 规则 JSON 导入/导出、命中统计（管理页「频道 → 工作流触发规则」）
- 规则模板 API 仍保留，管理 UI 暂未暴露（可用导入/导出替代）

### 2.4 复杂报表编排（专利多维分析）

面向「检索 → 多维度并行分析 → 汇总 → 图表 → 导出」类任务：

- **merge 节点**：等待所有上游分支完成后，合并为 `sections` 供下游使用
- **技能分类节点库**：检索 / 分析 / 图表 / 导出分组展示
- **参数映射器**：可视化编辑 `payload_template`，支持 `${input.*}`、`${nodes.<id>.*}` 引用
- **内置模板**：
  - `专利多维分析报表`（`patent_report_multidim`）— 检索/分析 → `patent-search`；图表/导出 → `patent-report`（**外部 skill 仓库**，见 [patent-workflow-showcase.zh.md](./patent-workflow-showcase.zh.md)）
  - `Patent Multi-Dimension Report`（`patent_report_multidim_en`）— 与中文版相同拓扑
- **专利节点预设**：图编辑器左栏拖拽；skill 名来自 `GET /workflows/showcase-config`（环境变量可配置）
- **按 skill_name 绑定**：模板中可写 `patent-search` 等技能名，保存/创建时自动解析为当前用户的 `skill_id`
- **运行表单**：开始节点 `input_fields` 定义关键词、行业等，执行时弹窗填写

### 2.5 自定义模板（我的模板）

除代码内置的 `patent_report_multidim` 等模板外，可在管理后台**自行创作**并复用流程图：

1. **新建工作流** → **图形编排**，拖入开始 / 技能 / merge / 结束等节点，配置 `payload_template` 与连线
2. **保存图形**（编辑器右上角保存）
3. 在工作流列表点击 **「保存为模板」**，填写模板名称与描述
4. 模板出现在 **「我的模板」** 区域；点击 **「使用此模板」** 即可基于同一拓扑创建新工作流

**存储规则**：

- 模板保存在数据库表 `skill_workflow_templates`（按用户隔离）
- 导出时会 **去掉 `skill_id`、保留 `skill_name`**，与内置模板一致，便于跨工作流复用
- 从模板创建时仍走 `skill_name` → 当前用户已安装技能的自动绑定

**API**：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/workflows/templates?locale=zh` | 内置 + 我的模板列表 |
| POST | `/api/workflows/{workflow_id}/save-as-template` | 将已有工作流存为模板 |
| DELETE | `/api/workflows/templates/{template_id}` | 删除我的模板（内置不可删） |
| POST | `/api/workflows/from-template/{template_id}` | 从内置或我的模板创建工作流 |

### 技能多语言（i18n）

技能 `config` 可声明展示名，工作流左栏与节点卡片按 **UI 语言** 显示（内部仍用 `skill.name` 绑定）：

```yaml
# SKILL.md frontmatter 或安装后写入 config
i18n:
  zh:
    title: 专利检索
    description: 检索、分析与导出
  en:
    title: Patent Search
    description: Search, analysis and export
```

也支持扁平写法：`display_name: { zh: "专利检索", en: "Patent Search" }`。

OpenClaw 格式 `patent-search` 的 `locales.zh` / `locales.en` 块会在加载时自动写入 `config.i18n`（`name`/`title` → `title`，`description` → `description`）。

### 基于 patent-search 复用分析节点

`patent-search` 已内置子命令，**不必**为每个分析维度单独安装 skill：

| 工作流节点角色 | patent-search 调用 |
|----------------|-------------------|
| 检索 | `command: search`, `query: ${input.keyword}` |
| 申请人分析 | `command: analysis`, `dimension: applicant` |
| 年份趋势 | `command: analysis`, `dimension: applicationYear` |
| 区域/省份 | `command: analysis`, `dimension: province` |
| 法律状态 | `command: analysis`, `dimension: legalStatus` |
| IPC 分类 | `command: analysis`, `dimension: ipc` |
| 图表 | `command: chart`, `sections: ${nodes.merge.sections}` |
| Excel | `command: excel`, `sections: ${nodes.merge.sections}` |
| Word / PPT | `command: word` / `ppt`，可传 `charts: ${nodes.chart.charts}` |
| 全套导出 | `command: all`（图表 + Excel + Word + PPT） |

同一 skill 可在 DAG 中出现多次，靠各节点不同的 `payload_template` 区分。图表与 Office 导出由内置 **`patent-report`** skill 完成（`skills/patent-report/`）。

技能命名建议：

| 角色 | skill 名 | 说明 |
|------|----------|------|
| 检索 / 各维度分析 | `patent-search` | `search` / `analysis` + dimension |
| 图表 / Excel / Word / PPT | `patent-report` | `chart` / `excel` / `word` / `ppt` / `all` |

> **编辑器预设**：从左栏「专利节点预设」拖拽；分析节点底层为 `patent-search`，图表/导出为 `patent-report`。

在技能 `config` 中设置 `workflow_role`: `search` | `analyze` | `visualize` | `export` 可影响节点库分组。

### 2.5 定时任务

- Skill Schedule 可触发 Workflow（不仅限于单 Skill）
- 独立 Worker 进程轮询调度（`WORKER_ENABLED=true`）

---

## 3. 数据模型

| 表 | 用途 |
|----|------|
| `skill_workflows` | 工作流定义（含 `graph_json`） |
| `skill_workflow_steps` | 线性步骤 |
| `skill_workflow_runs` | 运行实例 |
| `skill_workflow_step_runs` | 线性步骤运行 |
| `skill_workflow_approvals` | 审批待办 |
| `channel_workflow_bindings` | 频道 ↔ 工作流绑定与匹配规则 |
| `skill_schedules` | 定时触发配置 |

---

## 4. 执行模型

### 线性模式

1. 按 `order_index` 执行步骤  
2. 渲染 `payload_template` 后调用 `execute_skill()`  
3. 写入 `step_run`；按 `on_error`（`stop` / `continue`）决定终止或继续  

### 图模式（DAG）

1. 拓扑排序后按批次执行  
2. `skill` 节点调用 Skill；`condition` 根据连线标签（`true` / `false`）分支  
3. `approval` 节点暂停运行，写入审批记录  
4. 汇总 `node_runs` 与最终 `output_payload`  

---

## 5. API 索引

完整请求/响应见 [API 文档 — 工作流（Beta）](./api.zh.md#工作流-beta)。

**工作流**

- `GET/POST /api/workflows`
- `PATCH/DELETE /api/workflows/{workflow_id}`
- `GET/PUT /api/workflows/{workflow_id}/steps`
- `POST /api/workflows/{workflow_id}/run-once`
- `GET /api/workflows/runs/list`
- `GET /api/workflows/runs/{run_id}`
- `POST /api/workflows/runs/{run_id}/resume`

**审批**

- `GET /api/workflows/approvals/pending`
- `POST /api/workflows/approvals/{approval_id}/approve|reject`

**频道规则**

- `GET/PUT /api/channels/{channel_id}/workflows`
- `POST /api/channels/{channel_id}/workflows/preview`
- `GET /api/channels/{channel_id}/workflows/export`
- `POST /api/channels/{channel_id}/workflows/import`
- `GET /api/channels/{channel_id}/workflows/stats`
- `GET/POST/DELETE /api/channels/templates/workflow`
- `POST /api/channels/{channel_id}/workflows/apply-template/{template_id}`

**定时**

- `GET/POST/PATCH/DELETE /api/skill-schedules`
- `POST /api/skill-schedules/{id}/trigger`

---

## 6. 配置

| 变量 / 设置项 | 说明 |
|---------------|------|
| `WORKFLOW_ALERT_WEBHOOK_URL` | 工作流失败/审批拒绝时 POST JSON 告警 |
| `workflow.alert_webhook_url` | 同上，可在系统设置中覆盖 |
| `WORKER_ENABLED` | 是否启动后台 Worker（定时任务等） |
| `WORKER_TIMEZONE` | Worker 时区，默认 `Asia/Shanghai` |

---

## 7. 前端入口

- 管理后台 → **工作流（Beta）**：列表、步骤 JSON、图编辑器、运行记录、待审批
- 管理后台 → **定时任务**：绑定 Workflow 或 Skill
- 管理后台 → **渠道**：工作流绑定与规则调试

---

## 8. 已知限制（Beta）

- 图编辑器 UX 持续优化中；复杂 DAG 建议先用线性步骤验证
- 告警目前以 Webhook / 可选 SMS 为主；**轻客服站内提醒**（会话未读 + Admin WS）见 [inbox-notifications.zh.md](inbox-notifications.zh.md)，尚未实现
- 并行节点与条件表达式的边界 case 需在真实业务中进一步验证
- Beta 期间 `graph_json` schema 可能小版本迭代，升级前请导出备份

---

## 9. 路线图

| 阶段 | 内容 | 状态 |
|------|------|------|
| P1 | 线性 Workflow + 运行日志 | ✅ |
| P2 | Schedule / Channel 触发 Workflow | ✅ |
| P2.5–2.8 | 规则匹配、预览、解释、高亮 | ✅ |
| P2.9 | 模板库、导入导出、命中统计 | ✅ |
| P3.0–3.5 | 图 DSL、React Flow、DAG、审批、续跑 | ✅ Beta |
| 后续 | 运行态画布回放、ComfyUI 风格节点卡片、评估与 A/B | 规划中 |

---

## 10. 相关代码

| 区域 | 路径 |
|------|------|
| API | `src/backend/app/api/workflow.py` |
| 服务 | `src/backend/app/services/workflow_service.py` |
| 模型 | `src/backend/app/models/workflow.py` |
| 图编辑器 | `src/frontend/src/components/workflow/WorkflowGraphEditor.tsx` |
| 管理页 | `src/frontend/src/pages/WorkflowsPage.tsx` |
| Worker | `src/backend/app/worker/` |
