# 专利工作流展示案例（配置化）

> **原则**：专利 skill 包在 **独立仓库** 维护（如 `~/dev/skills/patents`），**不**提交进 mchat。  
> mchat 只提供 Workflow 模板、节点预设与 `EXTRA_SKILLS_DIRS` 扫描机制，作为完整演示案例。

---

## 1. 架构关系

```text
┌─────────────────────────────┐     EXTRA_SKILLS_DIRS      ┌──────────────────────────┐
│  mchat 平台仓库              │ ─────────────────────────► │  专利 skill 独立仓库        │
│  · 内置 Workflow 模板        │                            │  patent-search            │
│  · 专利节点预设（可配置名）   │                            │  patent-report            │
│  · skill 热加载 / 执行器     │     SKILLS_DIR (内置)      │  patent-transaction …     │
│  · mchat-help / mchat-ops   │ ◄───────────────────────── │  （各自 SKILL.md + main）  │
└─────────────────────────────┘                            └──────────────────────────┘
```

| 组件 | 所在位置 | 说明 |
|------|----------|------|
| 平台内置 skill | `mchat/skills/mchat-*` | 进 Git，运维/帮助类 |
| 专利 skill | 外部目录 / ClawHub zip | **不进** mchat Git |
| 专利多维报表模板 | `app/data/workflow_templates.py` | 引用可配置的 skill 名 |
| 展示配置 API | `GET /workflows/showcase-config` | 返回 skill 名、磁盘/DB 是否就绪 |

---

## 2. 环境变量

在 `src/backend/.env` 中配置（参见 `.env.example`）：

| 变量 | 示例 | 说明 |
|------|------|------|
| `SKILLS_DIR` | `../../skills` | 平台 skill 根目录 |
| `EXTRA_SKILLS_DIRS` | `/Users/you/dev/skills/patents` | 额外扫描路径，逗号/冒号分隔 |
| `PATENT_WORKFLOW_SHOWCASE_ENABLED` | `true` | `false` 时隐藏内置专利模板 |
| `PATENT_WORKFLOW_SEARCH_SKILL` | `patent-search` | 检索/分析节点绑定的 skill 名 |
| `PATENT_WORKFLOW_REPORT_SKILL` | `patent-report` | 图表/Excel/Word/PPT 节点 |
| `PATENT_SKILLS_SOURCE` | 同上路径 | 仅文档/运维备注，不参与扫描 |

快捷生成配置：

```bash
make patent-skills-env                    # 打印 .env 片段
make patent-skills-env WRITE=1            # 追加到 src/backend/.env
make patent-skills-prune                  # 删除 mchat/skills 内 patent-* 副本
make patent-skills-reload                 # 重载到 DB（默认 ~/dev/skills/patents）
make test-patent-showcase                 # 跑展示相关单测
```

或手动：

```bash
bash scripts/setup-patent-skills-env.sh
# 或写入已有 .env：
PATENT_SKILLS_DIR=/Users/xiaoxiao/dev/skills/patents bash scripts/setup-patent-skills-env.sh --write
```

---

## 3. 本地联调步骤

1. **准备专利 skill 目录**（独立仓库 clone 到本地）  
   需至少包含：`patent-search`、`patent-report`（报表导出，含 chart/excel/word/ppt/all）。

2. **配置 `.env`** — 设置 `EXTRA_SKILLS_DIRS` 指向该目录。

3. **安装 Python 依赖**（报表导出）：

   ```bash
   cd src/backend && pip install -r requirements-lite.txt
   ```

4. **重载 skill 到数据库**：

   ```bash
   cd src/backend
   python ../../scripts/reload-patent-skills.py
   ```

5. **配置 Secrets**（管理后台 → 技能 → patent-search → Secrets）：

   ```json
   { "PATENT_API_TOKEN": "你的令牌" }
   ```

6. **启动开发环境**：

   ```bash
   make dev
   ```

7. **验证展示配置**：

   ```bash
   curl -s -H "Authorization: Bearer <token>" http://127.0.0.1:3001/api/workflows/showcase-config | jq
   ```

   `ready: true` 表示 search + report 均已安装并启用。

8. **跑内置模板**：管理后台 → Workflow → 使用模板「专利多维分析报表」→ 填写关键词 → 运行。

---

## 4. 内置模板拓扑

```text
start → search (patent-search · search)
     → 并行 analysis (applicant / year / province / legalStatus)
     → merge → chart (patent-report · chart)
            → export (patent-report · all)
            → end
```

模板中的 `skill_name` 在返回给前端/创建实例时会按环境变量 **映射** 为实际安装的 skill 名（默认不变）。

---

## 5. patent-report 技能

维护在专利 skill 独立仓库中（与 `patent-search` 同级），**不要**放进 mchat 的 `skills/` 并提交。

| command | 输出 |
|---------|------|
| `chart` | PNG 柱状图 |
| `excel` | 多 Sheet xlsx |
| `word` | docx |
| `ppt` | pptx |
| `all` | 上述全部 |

输入：`sections` ← merge 节点 `${nodes.merge.sections}`。

---

## 6. CI / 新同事克隆仓库

- mchat CI **不**包含专利 skill；`test_patent_report_skill` 在找不到 skill 目录时会 skip。
- 演示专利 Workflow 的机器需：配置 `EXTRA_SKILLS_DIRS` + 重载 skill + API token。
- 可选：从 ClawHub 安装 `patent-search`，将 `patent-report` zip 安装到平台 `SKILLS_DIR`（仍与 mchat 源码解耦）。

---

## 7. 相关文件

| 文件 | 作用 |
|------|------|
| `app/core/skills_paths.py` | 多目录扫描 |
| `app/data/patent_workflow_showcase.py` | 模板 skill 名映射 |
| `app/skill/loader.py` | 合并加载多根目录 |
| `src/frontend/src/lib/patentWorkflowPresets.ts` | 前端预设（读 showcase-config） |
| `scripts/setup-patent-skills-env.sh` | 生成 .env 片段 |
| `scripts/reload-patent-skills.py` | 重载到 DB |

专利 skill 源仓库维护说明见独立仓库 `README.md` / `INSTALL.md`。
