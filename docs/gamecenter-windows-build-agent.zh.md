# GameCenter Windows 编译 Agent — 部署与 Cocos 2.x 适配

> 适用：Windows 编译机（10.98.8.186）通过 HTTP Agent 接收来自 MChat 服务器的构建请求，在桌面会话中运行 Cocos Creator 编译，解决 2.x 的 WebGL 初始化问题。

---

## 1. 背景

### 1.1 为什么需要 HTTP Agent

SSH 连接 Windows 时，sshd 运行在 **Session 0**（隔离桌面）。Cocos Creator 2.x 的 build-worker 需要在 Electron 进程中创建 WebGL 上下文来打包纹理/图集。Session 0 没有 GPU 访问权，导致 `canvas.getContext('webgl')` 返回 `null`，随后 `Device._initCaps` 调用 `null.getParameter()` 崩溃。

HTTP Agent 通过**用户登录时自启的计划任务**运行在**桌面会话（Session 1+）**中，天然拥有 GPU/桌面访问权。MChat 服务器通过 HTTP（而非 SSH）将 2.x 项目的构建请求发送给 Agent。

Cocos 3.x 不受此影响（原生 C++ 资源处理，不依赖 WebGL），可继续走 SSH。

### 1.2 SwiftShader — 即使桌面会话仍需

**即使 Agent 跑在桌面会话中**，Cocos 2.x 的 build-worker 仍然会遇到 WebGL 初始化失败。根因是：

```
Windows: CocosCreator.exe → Electron renderer → WebGL → ANGLE → Direct3D
         ↳ build-worker 进程中 ANGLE 初始化 D3D device 失败
         ↳ canvas.getContext('webgl') 返回 null → crash
```

**SwiftShader 方案**：在启动 `CocosCreator.exe` 时传入 `--use-gl=swiftshader --ignore-gpu-blocklist --disable-gpu-sandbox`，强制使用 CPU 模拟 WebGL，彻底绕过 GPU/D3D 依赖。

此方案不依赖物理显示器、不依赖 GPU driver、不依赖远程桌面保持连接。Cocos 2.4.15 安装目录自带 SwiftShader DLL（`libEGL.dll` / `libGLESv2.dll` 在 `swiftshader/` 子目录中）。

**编译耗时**：约 10 分钟（含 rsync 拉取 8000+ 文件 → Cocos 编译 → 推送回服务器）。

---

## 2. Windows 编译机一次性配置

### 2.1 前置条件

- Windows 10/11
- 已安装 Cocos Creator 2.4.15（`C:\ProgramData\cocos\editors\Creator\2.4.15\`）
- 已安装 Git for Windows（提供 Bash + rsync）
- 已克隆 mchat 仓库到 `C:\Users\Administrator\dev\mchat`
- 已配置 SSH 免密到 10.98.8.15（rsync 拉推源码）

### 2.2 一键安装 Agent

在 Windows 上以管理员运行 PowerShell：

```powershell
cd C:\Users\Administrator\dev\mchat\ops\scripts
Set-ExecutionPolicy Bypass -Scope Process -Force
.\gamecenter-windows-build-agent-setup.ps1
```

该脚本会：
1. 检查文件（Agent 脚本、配置模板、Git Bash）
2. 生成 `gamecenter-windows-agent.json`（含随机 token）
3. 添加防火墙规则（TCP 19280，仅允许 10.98.8.15 访问）
4. 注册计划任务 `GameCenterBuildAgent`（用户登录时自启）
5. 立即启动 Agent

**记下脚本输出的 token，需要写到服务器 `.env` 中。**

### 2.3 Watchdog（保活）

Agent 只在登录时启动，崩溃后不会自动恢复。添加每 5 分钟的健康检查：

```powershell
$Action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$env:USERPROFILE\dev\mchat\ops\scripts\gamecenter-windows-build-agent-watchdog.ps1`""
$Trigger = New-ScheduledTaskTrigger -Once (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName "GameCenterBuildAgentWatchdog" -Action $Action -Trigger $Trigger -User $env:USERNAME -Force
```

### 2.4 配置项说明

`gamecenter-windows-agent.json`：

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `host` | `0.0.0.0` | 监听地址 |
| `port` | `19280` | 监听端口 |
| `token` | 随机生成 | Bearer Token，与服务器一致 |
| `deploy_host` | `10.98.8.15` | rsync 回推目标 |
| `mchat_dir` | `C:/Users/Administrator/dev/mchat` | mchat 仓库路径 |
| `pipeline_script` | 自动拼接 | `gamecenter-local-pipeline.sh` 路径 |
| `bash_exe` | `C:\Program Files\Git\bin\bash.exe` | Git Bash 路径 |
| `build_timeout_seconds` | `1800` | 单次构建超时 |

### 2.5 Agent API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/health` | GET | 健康检查 |
| `/v1/status` | GET | 当前/上次任务状态 |
| `/v1/build` | POST | 触发构建（body: `{"slug": "...", "force": false}`） |

健康检查示例：

```bash
curl http://10.98.8.186:19280/v1/health -H "Authorization: Bearer <token>"
```

---

## 3. 服务器端配置

### 3.1 `.env` 追加

文件：`/opt/xiaoxiao/mchat/.env`

```bash
# Windows HTTP Agent（仅 2.x 走 HTTP，3.x 仍走 SSH）
GAMECENTER_BUILD_AGENT_URL=http://10.98.8.186:19280
GAMECENTER_BUILD_AGENT_TOKEN=<setup 脚本输出的 token>

# 编译机 SSH（3.x 用）
GAMECENTER_BUILD_SSH_HOST=10.98.8.186
GAMECENTER_BUILD_SSH_USER=administrator
GAMECENTER_BUILD_PIPELINE_SCRIPT=/c/Users/Administrator/dev/mchat/ops/scripts/gamecenter-local-pipeline.sh
GAMECENTER_BUILD_SSH_IDENTITY=~/.ssh/id_gamecenter_build
GAMECENTER_DEPLOY_HOST=10.98.8.15
```

### 3.2 分流逻辑（无需额外配置）

`gamecenter-remote-pipeline-build.sh` 已内置智能分流：

```
项目是 2.x + 配置了 GAMECENTER_BUILD_AGENT_URL
  → HTTP POST 到 Windows Agent

其他情况（3.x 或 Agent 未配置）
  → 走原来的 SSH 路径
```

DevBridge 的 `build_command` 保持不变：
```
bash /opt/xiaoxiao/mchat/ops/scripts/gamecenter-remote-pipeline-build.sh {slug}
```

### 3.3 验证

```bash
# 在 10.98.8.15 上
curl http://10.98.8.186:19280/v1/health -H "Authorization: Bearer $GAMECENTER_BUILD_AGENT_TOKEN"

# 手动触发一个 2.x 构建
bash /opt/xiaoxiao/mchat/ops/scripts/gamecenter-remote-pipeline-build.sh pkg0005-2-4-13
```

---

## 4. Cocos 2.x SwiftShader 机制

### 4.1 相关脚本

修改文件：`ops/scripts/gamecenter-local-build-project.sh`

Cocos 2.x 启动命令行（第 159-163 行）：

```bash
"$COCOS_BIN" \
  --use-gl=swiftshader --ignore-gpu-blocklist --disable-gpu-sandbox \
  --path "$PROJECT_DIR" --build "platform=web-mobile"
```

| 标志 | 作用 |
|------|------|
| `--use-gl=swiftshader` | 用 CPU 模拟 WebGL，而非 GPU/D3D |
| `--ignore-gpu-blocklist` | 跳过 Electron 的 GPU 黑名单检查 |
| `--disable-gpu-sandbox` | 在 Windows 上避免 GPU 进程沙箱冲突 |

### 4.2 开关控制

默认启用。若需要回退到原有行为：

```bash
GAMECENTER_2X_SWIFTSHADER=0 bash ops/scripts/gamecenter-local-build-project.sh <project_dir>
```

或通过 Agent 的环境变量覆盖。

### 4.3 失败尝试记录

以下方案**未生效**：

| 尝试 | 结果 | 原因 |
|------|------|------|
| `ELECTRON_EXTRA_LAUNCH_ARGS` 环境变量 | ❌ 不生效 | Cocos 2.4.15 内嵌的 Electron 8.x 不识读该 env var |
| 命令行传参 + env var 同时使用 | ❌ 不生效 | env var 仍然不生效，但命令行直接传参有效 |

最终方案：**命令行直接传参**（不通过环境变量）。

---

## 5. 日常运维

### 5.1 查看 Agent 状态

```bash
# 从服务器
curl http://10.98.8.186:19280/v1/status -H "Authorization: Bearer <token>"
```

响应示例：

```json
{
  "ok": true,
  "current": null,
  "last": {"slug": "pkg0005-2-4-13", "status": "built", "returncode": 0}
}
```

### 5.2 Agent 日志

Windows 上：`%USERPROFILE%\dev\gamecenter-agent\agent.log`

### 5.3 手动杀 Cocos 进程

```powershell
# 在 Windows 上
taskkill /F /IM CocosCreator.exe
```

Agent 会检测到进程退出，标记任务为 failed。

### 5.4 重启 Agent

```powershell
taskkill /F /IM python.exe /FI "WINDOWTITLE eq gamecenter-windows-build-agent*"
# 计划任务会自动在下次登录时重启；或手动：
Start-ScheduledTask -TaskName "GameCenterBuildAgent"
```

### 5.5 防火墙

Agent 的防火墙规则仅允许 10.98.8.15 访问 19280 端口：

```powershell
Get-NetFirewallRule -DisplayName "GameCenter Build Agent 19280" | Format-List
```

---

## 6. 故障排查

| 现象 | 排查 |
|------|------|
| Agent 不响应 | `netstat -an | findstr 19280` 确认端口在监听；检查计划任务是否触发 |
| 构建 2.x 失败 `getParameter of null` | 确认脚本已更新到包含 `--use-gl=swiftshader` 的版本；检查 `swiftshader/` DLL 存在 |
| 构建超时 | 默认 1800s；大型项目首次编译可能更久；调大 `build_timeout_seconds` |
| Agent 返回 409 | 上一次构建仍在运行；等它结束或手动杀 Cocos |
| 3.x 构建也走 HTTP | 不会。分流逻辑检测 `project.json` 版本，仅 2.x 走 HTTP |

---

## 7. 相关文件

| 文件 | 说明 |
|------|------|
| `ops/scripts/gamecenter-windows-build-agent.py` | HTTP Agent 主程序 |
| `ops/scripts/gamecenter-windows-build-agent-setup.ps1` | 一键安装脚本 |
| `ops/scripts/gamecenter-windows-build-agent-run.ps1` | 计划任务启动器（防重复） |
| `ops/scripts/gamecenter-windows-build-agent-start.bat` | Python 进程包装 |
| `ops/scripts/gamecenter-windows-agent.json.example` | Agent 配置模板 |
| `ops/scripts/gamecenter-local-build-project.sh` | Cocos 构建（含 SwiftShader 逻辑） |
| `ops/scripts/gamecenter-remote-pipeline-build.sh` | 服务器端分流入口 |
| `docs/gamecenter-build-queue.zh.md` | 构建队列与 worker 运维 |
| `docs/gamecenter-local-build-guide.zh.md` | 本机/远程 pipeline 通用指南 |
