# StockIntelligence · A 股情况分析技能（mchat 集成）

8 个 A 股分析技能 + 3 套可视化 workflow 编排预设，已接入 mchat。

> ⚠️ 数据仅供参考，不构成投资建议。

## 技能一览

| 技能 | 渠道 | workflow_role | 数据源 |
|------|------|---------------|--------|
| stock-quote | 行情 / K线 / 技术指标(MA/MACD/RSI/KDJ) | search | AKShare(新浪源) |
| stock-capital | 资金面 / 龙虎榜 / 融资融券 / 市场情绪 | search | AKShare |
| stock-fundamentals | 财务基本面 / ROE / 毛利率 / 同口径同比 | search | AKShare |
| stock-research | 券商研报 / 评级分布 / 预测PE | analyze | AKShare |
| stock-news | 新闻舆情 / 关键词情绪打标 | analyze | AKShare |
| stock-announcement | 公告 / 事件分类(回购/解禁/分红...) | analyze | AKShare(cninfo) |
| stock-sentiment | 东财人气榜 / 涨停梯队 | analyze | AKShare |
| stock-analysis | **综合研判（7渠道加权→报告）** | export | 调用上述 |

## 3 套 workflow 编排预设

在「工作流模板」/「模板市场」中可见（category=stock）：

| 预设 | 拓扑 | 适用 |
|------|------|------|
| **快速诊股** `stock_quick_scan` | start → stock-analysis(自调度7渠道) → end | 一键看一只票，最简 |
| **多维诊断** `stock_multi_diag` | start → 7采集并行 → merge → analysis → end | 完整情况分析，可视化最丰富（推荐） |
| **精选渠道** `stock_focus_pick` | start → quote+capital+research → merge → analysis → end | 聚焦核心三渠道，可增删节点 |

## 安装

技能源码仓库：`/Users/xiaoxiao/dev/skills/StockIntelligence`

### 方式一：同步到 mchat/skills（已配置）

```bash
bash /Users/xiaoxiao/dev/mchat/scripts/sync-stock-skills.sh
# 每个 skill 内嵌一份 si_common，独立可加载
```

重启 mchat 后端，或调用技能重载：
```bash
cd src/backend
venv/bin/python ../../scripts/reload-patent-skills.py   # 通用重载脚本，会扫描所有 stock-*
```

### 方式二：外部目录（可选）

在 `src/backend/.env` 加：
```
EXTRA_SKILLS_DIRS=/Users/xiaoxiao/dev/skills/StockIntelligence
```
注意：外部目录方式需保证 si_common 可被各 skill 通过相对路径 import（当前源仓库结构已支持）。

## 依赖

```bash
cd src/backend
venv/bin/pip install akshare pandas openpyxl matplotlib
```

- AKShare 免费免 token（默认）
- Tushare Pro 可选（配 `TUSHARE_TOKEN` 环境变量，自动切换；缺 token 回退 AKShare）
- K线图中文需 Noto CJK 字体（sync 脚本已处理；缺失时 `bash stock-analysis/ensure-font.sh`）

## 验证

```bash
# 技能被发现
PYTHONPATH=src/backend src/backend/venv/bin/python -c "
from app.skill.loader import SkillLoader
s=[x for x in SkillLoader().scan_skills() if x['name'].startswith('stock-')]
print(len(s),'个 stock 技能')"

# 模板可见
PYTHONPATH=src/backend src/backend/venv/bin/python -c "
from app.data.workflow_templates import list_workflow_templates
print([t['id'] for t in list_workflow_templates() if 'stock' in t['id']])"

# 单 skill 跑通
cd skills/stock-quote && python3 main.py 600519
```

## 原理

- 每个 skill 的 `main.py` 暴露 `run(**kwargs) -> dict`（mchat tool 契约），返回 `{ok, message, envelope, summary}`
- 采集 skill 返回标准信封 `{code, channel, signals[], summary, raw}`，每条 signal 带 `direction: bull|bear|neutral`
- stock-analysis 从 merge 节点的 `sections` 提取各渠道信封，加权研判（行情技术面×1.5、资金面×1.3…），评分 -100~+100，导出 Markdown + Excel + K线图
- workflow 编排器并行调度采集节点，merge 汇总，analysis 研判

## 输入输出参数约定（可视化组合）

每个 skill 通过 SKILL.md frontmatter 声明 IO 契约，方便在画布上组合：

### 输入：`workflow_fields`（画布渲染输入控件）

拖入节点时，画布按 `workflow_fields` 渲染表单控件（文本框/数字框/下拉框），而非让用户手写 JSON。例如 stock-quote：

```yaml
workflow_fields: {"code":{"type":"text","label":"股票代码","required":true,"placeholder":"600519"},
                  "days":{"type":"number","label":"回看天数","default":120},
                  "adjust":{"type":"select","label":"复权","options":[{"value":"qfq","label":"前复权"}]}}
```

字段类型：`text` | `number` | `select`（带 options）。

### 输出：`outputs`（JSON Schema，驱动绑定芯片）

每个 skill 声明 `run()` 返回的结构。当配置下游节点时，绑定下拉**自动列出上游可引用的路径**（取代旧的硬编码 patent 列表）。例如 stock-quote 输出：

```yaml
outputs: {"type":"object","properties":{
  "ok":{"type":"boolean"},
  "summary":{"type":"string"},
  "envelope":{"type":"object","description":"标准信号信封","properties":{
    "code":{},"channel":{},"signals":{"type":"array"},
    "raw":{"type":"object"}}}}}
```

由此，配置 stock-analysis 时绑定芯片会显示 `nodes.quote.envelope`、`nodes.quote.envelope.signals`、`nodes.quote.summary` 等真实可引用路径。嵌套对象会自动展开一层。

### 典型引用路径

| 来源 | 可引用路径 | 含义 |
|------|-----------|------|
| 开始节点 | `${input.code}` | 用户输入的股票代码 |
| 任意采集 skill | `${nodes.<id>.envelope}` | 该渠道完整信封 |
| 任意采集 skill | `${nodes.<id>.envelope.signals}` | 该渠道信号列表 |
| 任意采集 skill | `${nodes.<id>.summary}` | 该渠道摘要文本 |
| merge 节点 | `${nodes.merge.sections}` | 所有上游渠道信封汇总 |
| stock-analysis | `${nodes.analysis.score}` / `.files` / `.charts` | 综合评分/产物 |

### 各 skill 输出 channel 标识

| skill | channel | 主要信号 |
|-------|---------|---------|
| stock-quote | quote | MA/MACD/RSI/KDJ 多空 |
| stock-capital | capital | 主力资金/龙虎榜/融资/沪深300 |
| stock-fundamentals | fundamentals | ROE/毛利率/营收净利同比 |
| stock-research | research | 评级分布/预测PE |
| stock-news | news | 舆情情绪汇总 |
| stock-announcement | announcement | 事件分类(回购/解禁/分红) |
| stock-sentiment | sentiment | 人气排名/涨停梯队 |
| stock-analysis | — | score/direction/files/charts |

详见源仓库 `README.md` / `CHANGELOG.md`。
