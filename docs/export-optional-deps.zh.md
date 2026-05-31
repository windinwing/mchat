# 技能导出：可选依赖自动安装（备忘）

> 仅记录 **mchat 平台机制**，不涉及具体某个技能的用法。  
> 代码在 **Core**（`src/backend/app/skill/`）；Cloud 通过 `create_core_app()` 复用同一套执行器。

---

## 装什么

| 包名（pip） | import 名 | 用途 |
|-------------|-----------|------|
| `openpyxl` | `openpyxl` | 工具导出 `.xlsx` |
| `python-docx` | `docx` | 工具导出 `.docx` |
| `matplotlib` | `matplotlib` | 工作流图表 PNG（`patent-report`） |
| `python-pptx` | `pptx` | 工作流 PPT（`patent-report`） |

`requirements.txt` / `requirements-lite.txt` 已声明上述版本；**发布镜像仍建议显式打进依赖**，不要只靠运行时 pip。

---

## 两层自动安装

### 1）Core 执行器（`app/skill/deps.py`）

- 入口：`executor._execute_python_tool()` 里调用 `warm_skill_export_deps(skill_name, skill_dir)`。
- 行为：对配置了导出能力的技能名（`patent-search` / `patent-transaction` / `patent-disclosure` / `patent-report`），在跑工具前尝试 `import`；失败则：
  1. `uv pip install <包> -q`（若 PATH 有 `uv`）
  2. 否则 `python -m pip install <包> -q`（当前进程的解释器）
- 失败：**只打日志**，不抛错，**不阻塞**该技能的其它子命令（如检索 `search`）。

### 2）技能目录内（各技能 `export_deps.py`）

- 首次真正写 Excel/Word 时再试一次安装（逻辑与上层类似）。
- 仍失败 → 技能脚本内 **回退**（如 xlsx→csv、docx→md），并提示用户；核心查询能力不受影响。

---

## Core / Cloud / 发布 怎么对待

| 层面 | 说明 |
|------|------|
| **Core** | `deps.py`、`executor.py` 在此；`make deploy-core` / `app.main:app` 均走这套逻辑。 |
| **Cloud** | `cloud.main` 挂载 Core 应用，**无单独一份** deps；行为与 Core 一致。 |
| **发布（Release）** | 构建/部署 Core 或 Cloud 后端镜像时，应在镜像构建阶段 `pip install -r requirements.txt`，保证 `openpyxl`、`python-docx` 已存在。运行时自动 pip 仅作**补洞**（本机开发、漏装依赖的机器）。 |

**不要假设** Cloud 机器能访问外网 pip：生产以镜像内依赖为准；自动安装失败时依赖技能侧 CSV/MD 回退。

---

## 相关文件（改机制时动这些）

```
src/backend/app/skill/deps.py      # 预热 + pip 安装
src/backend/app/skill/executor.py  # MCHAT_UPLOAD_DIR、warm_skill_export_deps
src/backend/requirements.txt       # 正式依赖列表
src/backend/requirements-lite.txt
```

技能侧回退逻辑在各自 `skills/*/export_deps.py`、`excel_export.py` 等（属技能仓库，非本文展开）。

---

## 运维自检

```bash
cd src/backend
source venv/bin/activate   # 或 uv 环境
python -c "import openpyxl, docx; print('ok')"
```

缺包时：

```bash
uv pip install openpyxl==3.1.5 python-docx==1.1.2
# 或
pip install -r requirements.txt
```

改 `deps.py` 或 `executor` 后需 **重启后端进程**（Core / Cloud 各自的重启命令见 `docs/core-cloud-split.zh.md` 部署表）。
