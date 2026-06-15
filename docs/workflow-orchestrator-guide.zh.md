# MChat 技能编排（Workflow Orchestrator）完整文档

> 本文档覆盖技能编排的设计、节点类型、字段链接语法、Skill 输入输出、执行引擎、以及最佳实践。

---

## 目录

1. [架构概览](#1-架构概览)
2. [节点类型与配置](#2-节点类型与配置)
3. [字段链接语法](#3-字段链接语法)
4. [Skill 输入与输出](#4-skill-输入与输出)
5. [执行引擎](#5-执行引擎)
6. [条件分支](#6-条件分支)
7. [循环节点（Batch）](#7-循环节点batch)
8. [审批节点](#8-审批节点)
9. [合并节点](#9-合并节点)
10. [节点组](#10-节点组)
11. [模板系统](#11-模板系统)
12. [API 参考](#12-api-参考)
13. [最佳实践](#13-最佳实践)

---

## 1. 架构概览

```
┌─ 前端（React + ReactFlow）─────────────────────────────────┐
│                                                            │
│  WorkflowGraphPage (独立全屏页面)                           │
│    ├─ WorkflowSidebar    左栏：节点树 + 预设                │
│    ├─ ReactFlow 画布     拖拽编排 + 双击搜索 + 右键菜单      │
│    ├─ WorkflowNodeSearch 双击弹出的节点搜索                 │
│    ├─ 右栏属性面板       节点配置 + PayloadMapper            │
│    └─ 弹窗               模板画廊 / 运行历史 / 结果查看      │
│                                                            │
├─ 后端（FastAPI + SQLAlchemy）──────────────────────────────┤
│                                                            │
│  workflow_service.py                                       │
│    └─ _execute_graph_workflow()                            │
│         ├─ 拓扑排序 → 按层并发执行                          │
│         ├─ _render_template()  渲染 ${} 模板变量            │
│         ├─ _resolve_path()     按 . 路径取值（含 list 索引）│
│         └─ execute_skill()     调用 Skill 执行器            │
│                                                            │
│  skill/executor.py → workspace/skill_runner.py             │
│    └─ Python 工具 / CLI 适配 / 容器执行                     │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

### 关键文件

| 文件 | 职责 |
|------|------|
| `src/backend/app/services/workflow_service.py` | 执行引擎（拓扑排序、模板渲染、节点分发） |
| `src/backend/app/skill/executor.py` | Skill 执行入口（Python 工具 / Webhook） |
| `src/backend/app/workspace/skill_runner.py` | 本地 / 容器内脚本执行 |
| `src/backend/app/schemas/workflow.py` | 数据模型（Graph / Node / Edge） |
| `src/backend/app/data/workflow_templates.py` | 内置模板定义 |
| `src/frontend/src/components/workflow/WorkflowGraphEditor.tsx` | 图编辑器主体 |
| `src/frontend/src/components/workflow/PayloadMapper.tsx` | Skill 参数映射 UI |

---

## 2. 节点类型与配置

### 2.1 节点类型一览

| 类型 | 颜色 | 图标 | 用途 | 是否参与执行 |
|------|------|------|------|-------------|
| `start` | 🟢 #22c55e | ▶ CirclePlay | 定义输入字段，接收用户输入 | ✅ |
| `skill` | 🔵 #3b82f6 | 🔧 Wrench | 执行一个 Skill | ✅ |
| `condition` | 🟡 #f59e0b | ⊕ Split | 条件分支 | ✅ |
| `merge` | 🟣 #6366f1 | ⋈ GitMerge | 聚合多个上游结果 | ✅ |
| `batch` | 🔵 #06b6d4 | 🔁 Repeat | 遍历列表，对每项执行子流程 | ✅ |
| `approval` | 🔴 #ef4444 | 🛡 ShieldCheck | 人工审批暂停 | ✅ |
| `end` | 🟣 #a855f7 | ■ Square | 聚合最终输出 | ✅ |
| `group` | ⬜ #64748b | ▢ Box | 视觉分组（不执行） | ❌ |

### 2.2 各节点 config 字段

#### start 节点

```jsonc
{
  "type": "start",
  "config": {
    "input_fields": [
      {
        "key": "keyword",          // 字段标识，下游用 ${input.keyword} 引用
        "label": "关键词",          // 表单显示名
        "placeholder": "输入搜索词",
        "required": true,           // 运行时校验必填
        "type": "text"              // text | multiline | number | file
      },
      {
        "key": "industry",
        "label": "行业",
        "required": false,
        "type": "text"
      }
    ]
  }
}
```

#### skill 节点

```jsonc
{
  "type": "skill",
  "config": {
    "skill_id": "uuid-xxx",        // Skill ID（优先）
    "skill_name": "patent-search", // 或用 name（兜底）
    "workflow_role": "search",     // 分类：search/analyze/visualize/export/other
    "payload_template": {           // 传给 Skill 的参数（支持 ${} 模板）
      "command": "search",
      "query": "${input.keyword}",
      "industry": "${input.industry}"
    },
    "retry_count": 0,              // 失败重试次数
    "timeout_seconds": 0           // 超时秒数（0=不限制）
  }
}
```

#### condition 节点

```jsonc
{
  "type": "condition",
  "config": {
    "left": "input.keyword",       // 左值路径（用 _resolve_path 解析）
    "op": "==",                    // 运算符（见下表）
    "right": "AI"                  // 右值（也支持 ${} 模板变量）
  }
}
```

**支持的运算符：**

| op | 说明 | 类型 |
|----|------|------|
| `==` | 等于 | 任意 |
| `!=` | 不等于 | 任意 |
| `>` | 大于 | 数字 |
| `<` | 小于 | 数字 |
| `>=` | 大于等于 | 数字 |
| `<=` | 小于等于 | 数字 |
| `contains` | 包含子串 | 字符串 |
| `not_contains` | 不包含子串 | 字符串 |
| `startswith` | 前缀匹配 | 字符串 |
| `endswith` | 后缀匹配 | 字符串 |

> **注意**：`left` 和 `right` 都支持 `${}` 模板变量。`left` 用路径解析（如 `input.keyword`），`right` 用模板渲染（如 `${nodes.x.result.field}` 或静态值）。

#### merge 节点

```jsonc
{
  "type": "merge",
  "config": {
    "merge_mode": "sections"   // 目前唯一支持的模式
  }
}
```

聚合所有上游节点的结果为一个 `sections` 字典，按节点名索引。

#### batch 节点

```jsonc
{
  "type": "batch",
  "config": {
    "list_path": "nodes.search.result.patent_ids",  // 列表数据来源
    "max_concurrent": 3                              // 最大并发数
  }
}
```

batch 节点的子节点通过 `parentId` 关联，在画布上放在 batch 容器内。子节点目前仅支持 `skill` 类型。

#### approval 节点

无 config 字段。执行到此节点时暂停，等待人工审批后恢复。

#### end 节点

无 config 字段。自动聚合所有已执行节点的输出。

#### group 节点

```jsonc
{
  "type": "group",
  "config": {
    "color": "#3b82f6",     // 组颜色
    "collapsed": false,     // 是否折叠
    "width": 280,           // 宽度
    "height": 160           // 高度
  }
}
```

纯视觉容器，不参与执行。

---

## 3. 字段链接语法

### 3.1 变量命名空间

执行引擎维护一个 `outputs` 上下文：

```python
outputs = {
    "input": { ... },          # start 节点的用户输入
    "nodes": {                  # 各节点的执行结果
        "search": { "patent_ids": [...], "count": 42 },
        "merge": { "sections": { ... } },
    }
}
```

batch 循环中额外有：

```python
outputs = {
    ...,
    "item": { "line": "专利标题" },  # 当前迭代项
    "item_value": "专利标题"          # 当前项的取值
}
```

### 3.2 变量引用语法

| 语法 | 含义 | 示例 |
|------|------|------|
| `${input.KEY}` | 引用 start 节点输入 | `${input.keyword}` |
| `${nodes.ID}` | 引用整个节点结果（dict） | `${nodes.search}` |
| `${nodes.ID.FIELD}` | 引用节点结果的子字段 | `${nodes.search.patent_ids}` |
| `${nodes.ID.FIELD.0}` | 引用列表的第 0 项 | `${nodes.search.results.0.title}` |
| `${nodes.merge.sections}` | merge 节点的聚合结果 | `${nodes.merge.sections}` |
| `${item}` | batch 当前迭代项（整段保留类型） | `${item}` |
| `${item.KEY}` | batch 当前项的子字段 | `${item.line}` |
| `${item_value}` | batch 当前项的标量值 | `${item_value}` |

### 3.3 类型保留规则

模板渲染有两种模式：

**整段匹配**（值是一个完整的 `${...}`）→ **保留原始类型**：

```jsonc
// payload_template:
{ "sections": "${nodes.merge.sections}" }
// 渲染后（sections 是 dict，原样传入）：
{ "sections": { "search": {...}, "analyze": {...} } }
```

**部分替换**（值中嵌入 `${...}`）→ **全部转为字符串**：

```jsonc
// payload_template:
{ "title": "报告：${input.keyword}（${input.industry}）" }
// 渲染后：
{ "title": "报告：AI（半导体）" }
```

> **关键区别**：需要传 dict/list/number 给 Skill 时，整个值必须只写 `"${...}"`，不能混入其他文字。

### 3.4 不支持的语法

| 不支持 | 说明 | 替代方案 |
|--------|------|---------|
| 数组索引 `[N]` | 用 `.N` 代替 | `${nodes.x.list.0}` ✅ |
| 默认值 `${a:-b}` | — | 用 condition 节点预处理 |
| 过滤器 `${a|upper}` | — | 在 Skill 内部处理 |
| 算术运算 | — | 在 Skill 内部计算 |
| 嵌套 `${${var}}` | — | — |

---

## 4. Skill 输入与输出

### 4.1 Skill 输入

Skill 通过 `payload_template` 接收参数。模板渲染后，结果作为 `args` dict 传入 Skill 执行器。

**payload_template 示例：**

```jsonc
{
  "command": "search",
  "query": "${input.keyword}",
  "year_from": "${input.year_from}",
  "sort": "s"
}
```

渲染后传给 Skill 的 `args`：

```python
args = {
    "command": "search",
    "query": "人工智能",
    "year_from": "2020",
    "sort": "s"
}
```

### 4.2 Skill 输入参数声明

Skill 可通过 `SKILL.md` 声明参数（供前端 PayloadMapper 展示表单）：

```markdown
---
workflow_fields: [{"key":"query","label":"搜索词","type":"string","required":true},{"key":"sort","label":"排序","type":"select","options":["s","d","p"]}]
---
```

### 4.3 Skill 输出格式

Skill 的返回值经过标准化：

| 返回类型 | 标准化结果 |
|---------|-----------|
| `dict` | 原样保留 |
| `str` / `int` / `float` / `bool` | `{"value": ...}` |
| `list` | 原样保留 |
| `None` | `{"ok": true}` |

典型 Skill 返回：

```python
return {
    "patent_ids": ["CN123", "CN456"],
    "count": 2,
    "results": [{"title": "...", "patent_id": "CN123"}],
    # 可选：文件产出
    "files": [{"name": "report.xlsx", "path": "/tmp/report.xlsx"}],
    "charts": [{"name": "trend.png", "path": "/tmp/trend.png"}],
}
```

### 4.4 Skill 返回字段约定

| 字段 | 类型 | 说明 |
|------|------|------|
| `patent_ids` | `list[str]` | 专利 ID 列表（专利搜索类 Skill） |
| `results` | `list[dict]` | 详细结果列表 |
| `count` | `int` | 结果数量 |
| `sections` | `dict` | 分段内容（merge 节点常用） |
| `files` | `list[dict]` | 文件产出（自动改名 `report_files`） |
| `charts` | `list[dict]` | 图表产出（自动复制为 `report_charts`） |
| `stdout` | `str` | CLI 模式的标准输出 |
| `error` | `str` | 错误信息（引擎会将其视为失败） |

---

## 5. 执行引擎

### 5.1 拓扑执行流程

```
1. 解析 graph → 构建 incoming/outgoing 邻接表
2. 初始化 ready 队列 = [start 节点 + 无入边节点]
3. while ready:
     batch = ready 中未完成的节点
     results = asyncio.gather(并行执行 batch)  ← 每个节点独立 DB session
     for each result:
       - success → 加入 done，写入 outputs
       - paused  → 记录暂停原因，继续处理兄弟节点
       - failed  → 加入 done（标记失败），继续
     根据完成节点更新 ready（检查依赖是否满足）
     若有 paused → 停止调度新节点
4. 返回 (status, error, payload)
```

### 5.2 并发安全

- 每个并发执行的节点使用独立的 `AsyncSession`（`async_session_factory()`）
- batch 子项也各自独立 session
- 避免了 "This session is already handling a request" 错误

### 5.3 重试与超时

Skill 节点支持配置：

| 配置 | 说明 |
|------|------|
| `retry_count` | 失败后重试次数（默认 0） |
| `timeout_seconds` | 单次执行超时（0 = 不限制） |

---

## 6. 条件分支

### 6.1 工作方式

1. `condition` 节点求值 `left op right`，得到 `True` 或 `False`
2. 根据**出边的 condition 字段**选择走哪条分支

### 6.2 边的 condition 值

| edge.condition | 含义 |
|----------------|------|
| `"true"` | condition 结果为 True 时走这条边 |
| `"false"` | condition 结果为 False 时走这条边 |
| `"default"` 或空 | 无条件走（fallback） |

### 6.3 示例

```
[condition: input.keyword == "AI"]
    ├──(condition="true")──→ [skill: AI 分析]
    └──(condition="false")─→ [skill: 通用分析]
```

---

## 7. 循环节点（Batch）

### 7.1 工作方式

1. 从 `list_path` 解析出列表数据
2. 对列表中的每个 `item`，创建独立执行上下文
3. 按 `max_concurrent` 并发执行子流程
4. 子流程中的 skill 节点可通过 `${item}` / `${item_value}` 引用当前项

### 7.2 列表解析规则

| list_path 返回值 | 处理方式 |
|-----------------|---------|
| `list` | 直接遍历 |
| JSON 字符串（以 `[` 开头） | 解析为 list |
| 普通字符串 | 按换行分割为 `[{line: "xxx"}, ...]` |

### 7.3 子节点上下文

```python
local_outputs = {
    "input": ...,          # 继承父级输入
    "nodes": ...,          # 继承父级节点结果快照
    "item": item,          # 当前迭代项
    "item_value": ...,     # 当前项的取值（dict+line 键取 line 值）
}
```

---

## 8. 审批节点

执行到 `approval` 节点时：

1. 创建 `SkillWorkflowApproval` 记录（status=pending）
2. 工作流暂停（status=paused）
3. 用户通过 API 审批 → 恢复执行

### 审批 API

| 端点 | 说明 |
|------|------|
| `GET /workflows/approvals/pending` | 列出待审批 |
| `POST /workflows/approvals/{id}/approve` | 批准 |
| `POST /workflows/approvals/{id}/reject` | 拒绝 |
| `POST /workflows/runs/{id}/resume` | 恢复暂停的运行 |

---

## 9. 合并节点

聚合多个上游分支的结果。

### 输出结构（sections 模式）

```python
{
    "sections": {
        "搜索": {"node_id": "search", "result": {...}},
        "分析": {"node_id": "analyze", "result": {...}},
        "图表": {"node_id": "chart", "result": {...}},
    },
    "merged": True
}
```

下游节点通过 `${nodes.merge.sections}` 引用整个聚合结果。

---

## 10. 节点组

视觉分组容器，不参与执行。

| 操作 | 方式 |
|------|------|
| 创建 | 选中 ≥2 节点 → `Cmd/Ctrl+G` 或右键 → Group Selected |
| 重命名 | 双击标题 |
| 换色 | 点击色圆 |
| 折叠 | 点击 chevron（隐藏子节点） |
| 删除 | 删除组 → 子节点自动解除归属（不被删除） |

---

## 11. 模板系统

### 内置模板

| ID | 名称 | 说明 |
|----|------|------|
| `patent_report_multidim` | 专利多维分析报表 | 搜索→分析→图表→导出 |
| `batch_url_fetch` | 批量 URL 抓取 | batch 循环 + 技能 |
| `web_fetch` | 网页抓取 | 单技能流程 |
| `notify_ping_test` | 通知测试 | 通知链路验证 |

### 模板结构

```jsonc
{
  "id": "xxx",
  "name": "模板名",
  "description": "描述",
  "category": "patent",      // patent | notification | general
  "locale": "zh",            // zh | en
  "graph_json": { "version": 1, "nodes": [...], "edges": [...] }
}
```

---

## 12. API 参考

### 工作流 CRUD

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/workflows` | 列出全部 |
| GET | `/workflows/wf/{id}` | 获取单个 |
| POST | `/workflows` | 创建 |
| PATCH | `/workflows/{id}` | 更新（含 graph_json） |
| DELETE | `/workflows/{id}` | 删除 |

### 运行

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/workflows/{id}/run-once` | 触发运行 |
| GET | `/workflows/runs/list` | 运行列表 |
| GET | `/workflows/runs/{id}` | 运行详情 |
| POST | `/workflows/runs/{id}/resume` | 恢复暂停 |
| DELETE | `/workflows/runs/{id}` | 删除运行 |

### 模板

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/workflows/templates` | 模板列表 |
| POST | `/workflows/from-template/{id}` | 从模板创建 |
| POST | `/workflows/{id}/save-as-template` | 另存为模板 |

---

## 13. 最佳实践

### 13.1 命名规范

- 节点名用中文短词（搜索、分析、图表、导出），便于 `${nodes.搜索.result}` 引用
- 或用英文 ID 并在 name 中标注

### 13.2 错误处理

- 关键 skill 设置 `retry_count: 1-2`
- 长时间 skill 设置 `timeout_seconds`
- 用 condition 节点检查上游结果是否为空，避免下游报错

### 13.3 性能优化

- batch `max_concurrent` 建议 3-5（过高会触发外部 API 限流）
- 合并节点放扇出分支汇聚点
- 大数据集考虑分页处理

### 13.4 调试技巧

- 在 skill 之间插入 condition 节点检查中间值
- 用 JSON 标签页直接查看/编辑 graph 结构
- 运行历史 → 结果面板查看每个节点的输出
- 双击画布快速搜索添加节点
