# GameCenter 本机 / Mac / Windows 编译与同步操作说明

> 适用场景：群组 Agent 在 **10.98.8.15** 改 Cocos 源码 → 在 **本机（Mac / Windows / Mac mini）** 用 Cocos 真编译 → 把 `build/web-mobile` 推回服务器 → `:5099` 试玩生效。

---

## 1. 先理解目录关系（很重要）

| 位置 | 路径 | 谁写 | 谁读 |
|------|------|------|------|
| 服务器源码（Agent 改这里） | `/opt/xiaoxiao/gamecenter/newsrc/<slug>/<嵌套工程>/` | DevBridge Agent | pipeline 拉取 |
| 服务器试玩（:5099） | 同上项目的 `build/web-mobile/` | pipeline 推送 | GameCenter gunicorn |
| 服务器 playables | `/opt/xiaoxiao/gamecenter/playables/<slug>/current` | pipeline / DevBridge publish | 部分 nginx 入口 |
| 本机工作区 | `~/dev/gamecenter-server/newsrc/<slug>/` | rsync 拉取 | 本机 Cocos 编译 |

**DevBridge 配置（服务器）：**

- `source_root`: `/opt/xiaoxiao/gamecenter/src`
- `extra_source_roots`: `["/opt/xiaoxiao/gamecenter/newsrc"]` ← **pkg0002 实际在这里**
- Agent `patch` 写入的是 **resolve 出来的嵌套工程目录**，不是随便一个外层文件夹。

**常见误解：**

1. **「pull 没拉代码」** — rsync 是增量的，若本机已与服务器一致，日志里可能只显示 `0 file(s) updated`，这是正常的，不代表没执行拉取。
2. **「改了源码试玩没变」** — 可能是：① Cocos `library/` 缓存未重编；② 浏览器缓存；③ 看的是旧版本标记（如 `ver:1.0` 一直存在）；④ 服务器上 DevBridge `build_command` 在无 Cocos 时**复用旧 build**。
3. **`:5099` 不读 playables** — 必须更新 `newsrc/.../build/web-mobile`，只 publish 到 playables 不够。

---

## 2. 本机一次性配置

### 2.1 复制环境文件

```bash
cp ops/scripts/gamecenter-local.env.example ops/scripts/gamecenter-local.env
```

编辑 `ops/scripts/gamecenter-local.env`：

```bash
export GAMECENTER_COCOS_CREATOR_BIN="/Applications/Cocos/Creator/3.8.8/CocosCreator.app/Contents/MacOS/CocosCreator"
export LOCAL_GAMECENTER="$HOME/dev/gamecenter-server"
export SSH_USER="xiaoxiao"
# 一般不用改：
# export REMOTE_GAMECENTER_ROOT="/opt/xiaoxiao/gamecenter"
# export REMOTE_PROJECT_PARENT="newsrc"
```

### 2.2 SSH 免密

本机 → 服务器：

```bash
ssh-copy-id xiaoxiao@10.98.8.15
ssh xiaoxiao@10.98.8.15 'echo ok'
```

### 2.3 确认 Cocos 可执行

```bash
"$GAMECENTER_COCOS_CREATOR_BIN" --version 2>/dev/null || ls -la "$GAMECENTER_COCOS_CREATOR_BIN"
```

---

## 3. 脚本速查

| 脚本 | 作用 |
|------|------|
| `gamecenter-local-pipeline.sh` | **一条命令**：拉源码 → 本机编译 → 推 build + 源码回服务器 |
| `gamecenter-sync-from-server.sh` | 仅拉取（整个 gamecenter 或后续按 slug 使用） |
| `gamecenter-local-build-project.sh` | 仅本机编译（需已有本地源码） |
| `gamecenter-sync-build-to-server.sh` | 仅推送（源码 + build/web-mobile + playables 镜像） |
| `gamecenter-verify-playable.sh` | 检查服务器 build 时间、源码片段、HTTP |
| `gamecenter-diff-server-local.sh` | **对比服务器与本机某个源文件 md5**（排查拉取问题） |
| `gamecenter-ssh-build.sh` | 在**服务器上**编译（无 Cocos 时只会复用旧包，不推荐） |

---

## 4. 日常操作（推荐）

### 4.1 Agent 改完代码后 — 一条命令闭环

```bash
./ops/scripts/gamecenter-local-pipeline.sh 10.98.8.15 pkg0002-3-x-3-8-3ts --force
```

步骤说明：

1. **[1/3] Pull** — 从 `10.98.8.15:/opt/xiaoxiao/gamecenter/newsrc/pkg0002-.../` 拉到本机  
   - 排除：`build/`、`library/`、`temp/`（build 在本机生成，library 在本机缓存）
   - 输出 `pull summary: N file(s) updated`；**N=0 表示已与服务器同步**
   - 自动用 `UILoading.ts` 做 **md5 校验**（不一致则中止，避免用旧代码编译）

2. **[2/3] Build** — 本机 Cocos 编 `web-mobile`  
   - `--force` 会先删除本机 `library/`、`temp/`，避免增量缓存导致改了 `.ts` 却不进包
   - Cocos 可能报 `exit 36`（mach_port 子进程），只要有 `build/web-mobile/index.html` 仍视为成功

3. **[3/3] Push** — 推回服务器  
   - 源码（assets/settings/…）→ 服务器嵌套工程目录  
   - **build/web-mobile** → 服务器同路径（**:5099 读这个**）  
   - 镜像一份到 `playables/<slug>/releases/...`

4. **验证** — 脚本末尾自动跑 `gamecenter-verify-playable.sh`

试玩地址（**必须强刷 Cmd+Shift+R**）：

- http://10.98.8.15:5099/pkg0002-3-x-3-8-3ts/
- https://xyx.9235.net/pkg0002-3-x-3-8-3ts/

### 4.2 怀疑没拉到服务器最新代码

```bash
# 对比单个文件（默认 UILoading.ts）
./ops/scripts/gamecenter-diff-server-local.sh 10.98.8.15 pkg0002-3-x-3-8-3ts

# 对比你刚改的文件
./ops/scripts/gamecenter-diff-server-local.sh 10.98.8.15 pkg0002-3-x-3-8-3ts assets/scripts/ui/UIMain.ts
```

输出 `md5: MATCH` = 本机与服务器一致；`DIFF` = 需要先拉取或检查 Agent 是否写对路径。

也可在服务器直接看 Agent 改的文件：

```bash
ssh xiaoxiao@10.98.8.15 \
  "grep -n '你的标记' /opt/xiaoxiao/gamecenter/newsrc/pkg0002-3-x-3-8-3ts/*/assets/scripts/ui/UIMain.ts"
```

### 4.3 分步执行（调试）

```bash
# 只拉
rsync -avz --exclude build/ --exclude library/ --exclude temp/ \
  xiaoxiao@10.98.8.15:/opt/xiaoxiao/gamecenter/newsrc/pkg0002-3-x-3-8-3ts/ \
  ~/dev/gamecenter-server/newsrc/pkg0002-3-x-3-8-3ts/

# 只编
./ops/scripts/gamecenter-local-build-project.sh \
  ~/dev/gamecenter-server/newsrc/pkg0002-3-x-3-8-3ts --force

# 只推（确认本地源码已与服务器一致后再推，否则会覆盖服务器上的 Agent 修改）
./ops/scripts/gamecenter-sync-build-to-server.sh 10.98.8.15 pkg0002-3-x-3-8-3ts
```

### 4.4 常用参数

| 参数 | 含义 |
|------|------|
| `--force` | 清 `library/`/`temp/` 后强制重编 |
| `--skip-pull` | 跳过拉取（**仅当你确定本机源码已是最新**） |
| `--skip-push` | 只编译不上传 |

---

## 5. Mac mini 作为专用编译机

架构：

```
10.98.8.15 (MChat + 源码 + 试玩)
      ↕ rsync / ssh
Mac mini (只负责 Cocos 编译)
```

### 5.1 Mac mini 初始化

1. 安装 Cocos Creator 3.8.8（路径与 `gamecenter-local.env` 一致）
2. 开启 **系统设置 → 共享 → 远程登录**
3. 创建用户如 `build`，克隆 mchat 或同步 `ops/scripts/` 到 `/opt/mchat`
4. 配置 `/opt/mchat/ops/scripts/gamecenter-local.env`（同第 2 节）
5. **双向 SSH 免密**：
   - Mac mini → 10.98.8.15（拉推 rsync）
   - 10.98.8.15 → Mac mini（Agent 触发编译）

### 5.2 Mac mini 上手动验证

```bash
/opt/mchat/ops/scripts/gamecenter-local-pipeline.sh 10.98.8.15 pkg0002-3-x-3-8-3ts --force
```

### 5.3 自动化方式

**方式 A — 定时（简单）**

Mac mini `crontab`：

```cron
*/10 * * * * /opt/mchat/ops/scripts/gamecenter-local-pipeline.sh 10.98.8.15 pkg0002-3-x-3-8-3ts --force >> /tmp/gc-build.log 2>&1
```

**方式 B — 群组 Agent 改完即编（推荐）**

在 MChat 管理端 **DevBridge 设置**：

| 字段 | 建议值 |
|------|--------|
| `cocos_creator_bin` | 留空（Linux 服务器没有 Cocos） |
| `build_command` | 见下方 |
| `build_timeout_seconds` | `1800` |

```bash
ssh -o BatchMode=yes -o ConnectTimeout=15 build@<macmini-ip> \
  'bash /opt/mchat/ops/scripts/gamecenter-local-pipeline.sh 10.98.8.15 {slug} --force'
```

Agent 流程：`patch`（服务器）→ `build`（SSH 到 Mac mini 跑 pipeline）→ 试玩更新。

**方式 C — 构建队列**

多台游戏或并发请求时，Mac mini 用 `flock` 串行编译，避免多个 Cocos 同时跑：

```bash
flock /tmp/cocos-build.lock \
  bash /opt/mchat/ops/scripts/gamecenter-local-pipeline.sh 10.98.8.15 "$SLUG" --force
```

### 5.4 服务器 DevBridge 路径配置参考

文件：`/opt/xiaoxiao/mchat/data/devbridge/admin-settings.json`

```json
{
  "gamecenter": {
    "source_root": "/opt/xiaoxiao/gamecenter/src",
    "extra_source_roots": ["/opt/xiaoxiao/gamecenter/newsrc"],
    "build_command": "ssh -o BatchMode=yes build@<macmini-ip> 'bash /opt/mchat/ops/scripts/gamecenter-local-pipeline.sh 10.98.8.15 {slug} --force'",
    "cocos_creator_bin": "",
    "playables_root": "/opt/xiaoxiao/gamecenter/playables",
    "playable_base_urls": ["http://10.98.8.15:5099", "https://xyx.9235.net"]
  }
}
```

> 在未接 Mac mini 之前，服务器上的 `build_command` 若指向 `gamecenter-bridge-build.sh` 且未配置 Cocos，**只会复用旧 build**，看起来「构建成功」但试玩不变。

---

## 6. 故障排查清单

| 现象 | 检查 |
|------|------|
| 没有 `[3/3] Push` | 看 Cocos 是否 exit 36；应用最新 `gamecenter-local-build-project.sh` |
| pull 显示 0 files updated | 正常；用 `gamecenter-diff-server-local.sh` 确认 md5 |
| pull verify FAILED | 路径或权限问题；确认 slug 与 `extra_source_roots` |
| 源码改了试玩不变 | `--force` 清缓存；强刷浏览器；看 `verify-playable` 的 index.html 时间 |
| Agent 改了但服务器文件没变 | 看 DevBridge 是否 `write_enabled`；patch 路径是否相对工程根 |
| 构建成功但仍是旧 UI | 服务器 `build_command` 是否在复用旧包；改走 Mac pipeline |
| FPS/调试面板关不掉 | 不是 Main.ts 问题；`debug=true` 会在 `application.js` 写 `showFPS: true`；用 `debug=false` 重编 |
| Agent 说 patch/build 成功但无变化 | 查 `data/devbridge/.../changes/` 是否有该文件；build id 是否在 `builds/` 里真实存在 |

快速验证命令：

```bash
./ops/scripts/gamecenter-verify-playable.sh 10.98.8.15 pkg0002-3-x-3-8-3ts
./ops/scripts/gamecenter-diff-server-local.sh 10.98.8.15 pkg0002-3-x-3-8-3ts
```

---

## 7. Windows 回写（与 Mac 同一套脚本）

流程与 Mac **完全相同**：拉取 → 编译 → 推送。差别只在运行环境和路径写法。

### 7.1 推荐环境：Git Bash

不要用纯 CMD/PowerShell 直接跑 `.sh`（除非你自己封装）。推荐：

| 组件 | 安装方式 |
|------|----------|
| Git Bash | [Git for Windows](https://git-scm.com/download/win) |
| OpenSSH | Windows 10+ 自带；或 `scoop install openssh` |
| rsync | `scoop install rsync` 或 `choco install rsync` |

在 **Git Bash** 里进入 mchat 仓库根目录执行（与 Mac 一样）：

```bash
./ops/scripts/gamecenter-local-pipeline.sh 10.98.8.15 pkg0002-3-x-3-8-3ts --force
```

### 7.2 Windows 环境文件

```bash
cp ops/scripts/gamecenter-local.env.windows.example ops/scripts/gamecenter-local.env
```

示例（路径用 Git Bash 风格 `/c/...`）：

```bash
export GAMECENTER_COCOS_CREATOR_BIN="/c/Program Files/Cocos/Creator/3.8.8/CocosCreator.exe"
export LOCAL_GAMECENTER="/c/Users/你的用户名/dev/gamecenter-server"
export SSH_USER="xiaoxiao"
```

在 Cocos Dashboard 里确认实际安装路径；常见为：

```
C:\Program Files\Cocos\Creator\3.8.8\CocosCreator.exe
```

### 7.3 SSH 免密（Windows）

PowerShell 或 Git Bash：

```bash
ssh-keygen -t ed25519
cat ~/.ssh/id_ed25519.pub
# 把公钥追加到服务器 ~/.ssh/authorized_keys

ssh xiaoxiao@10.98.8.15 'echo ok'
```

### 7.4 验证 rsync 可用

Git Bash 里：

```bash
rsync --version
ssh xiaoxiao@10.98.8.15 'echo ok'
```

若 `rsync: command not found`，先 `scoop install rsync`。

### 7.5 Windows 注意事项

1. **路径**：`gamecenter-local.env` 里用 `/c/Users/...`，不要混用反斜杠。
2. **Cocos 退出码**：Windows 上也可能非 0，只要有 `build/web-mobile/index.html` 脚本会继续（与 Mac 相同）。
3. **debug=false**：默认已关闭 FPS 面板；无需改 Main.ts。
4. **不要用 WSL 编 Cocos 又用 Windows 路径**：Cocos Creator 是 Windows GUI 程序，建议在 **Git Bash + Windows 版 Cocos** 一套做完，不要跨 WSL/Windows 混用工程目录。
5. **Agent 触发 Windows 编译机**：在 Windows 上安装 [OpenSSH Server](https://learn.microsoft.com/windows-server/administration/openssh/openssh_install_firstuse)，服务器 DevBridge `build_command` 可写：
   ```bash
   ssh -o BatchMode=yes 你的Windows用户@<windows-ip> \
     'bash /c/Users/你/mchat/ops/scripts/gamecenter-local-pipeline.sh 10.98.8.15 {slug} --force'
   ```
   （路径按你机器上 mchat 仓库实际位置改。）

### 7.6 Windows 日常命令（与 Mac 一致）

```bash
# 一条命令回写试玩
./ops/scripts/gamecenter-local-pipeline.sh 10.98.8.15 pkg0002-3-x-3-8-3ts --force

# 对比服务器与本机源码
./ops/scripts/gamecenter-diff-server-local.sh 10.98.8.15 pkg0002-3-x-3-8-3ts

# 看 Agent 是否真写过
./ops/scripts/gamecenter-list-changes.sh 10.98.8.15 pkg0002-3-x-3-8-3ts
```

---

## 8. slug 与路径提醒

- 正确 slug：`pkg0002-3-x-3-8-3ts`（不要写成 `...-8-8-3ts`）
- 嵌套工程名以服务器为准（含中文编码），脚本会自动 `gc_resolve_nested_project_dir`
- resolve 命令（服务器）：

```bash
python3 /opt/xiaoxiao/mchat/ops/scripts/resolve-gamecenter-project.py \
  /opt/xiaoxiao/mchat pkg0002-3-x-3-8-3ts
```

---

## 9. 聊天改代码 → 自动编译更新（自动化部署）

目标：群组里 Agent `patch` 改源码后，**自动** SSH 到 Mac/Windows 编译机跑 pipeline，推回 `build/web-mobile`，`:5099` 试玩立刻可测。

### 9.1 架构

```text
用户在群组聊天 patch
    → 10.98.8.15 写入 newsrc 源码
    → （自动）build_command SSH 到编译机
    → 编译机 gamecenter-local-pipeline.sh 拉源码→编→推
    → 10.98.8.15 build/web-mobile 更新
    → http://10.98.8.15:5099/<slug>/ 生效
```

### 9.2 一次性配置（三块）

**① 编译机（Mac / Windows / Mac mini）**

- 安装 Cocos + 配置 `gamecenter-local.env`（见上文）
- 克隆 mchat 的 `ops/scripts`
- 能 SSH 到 `10.98.8.15`（rsync 拉推）
- 手动验证：`gamecenter-local-pipeline.sh 10.98.8.15 <slug> --force`

**② 编译机 ← 10.98.8.15 反向 SSH**

在 **10.98.8.15** 生成密钥，公钥加到编译机 `~/.ssh/authorized_keys`：

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_gamecenter_build -N ''
ssh build@<编译机IP> 'mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys' < ~/.ssh/id_gamecenter_build.pub
ssh -i ~/.ssh/id_gamecenter_build build@<编译机IP> 'echo ok'
```

**③ MChat 管理端 DevBridge**

| 配置项 | 值 |
|--------|-----|
| 构建命令 | `bash /opt/xiaoxiao/mchat/ops/scripts/gamecenter-remote-pipeline-build.sh {slug}` |
| **改代码后自动编译并回写试玩** | ✅ 勾选 |
| Cocos 路径 | 留空（在编译机上） |
| 试玩基址 | `http://10.98.8.15:5099` |

服务器 `.env` 补充（或通过 systemd 环境变量）：

```bash
GAMECENTER_BUILD_SSH_HOST=10.98.8.186
GAMECENTER_BUILD_SSH_USER=<你的Windows用户名>
GAMECENTER_BUILD_PIPELINE_SCRIPT=/opt/mchat/ops/scripts/gamecenter-local-pipeline.sh
GAMECENTER_DEPLOY_HOST=10.98.8.15
GAMECENTER_AUTO_BUILD_AFTER_PATCH=true
GAMECENTER_BUILD_COMMAND=bash /opt/xiaoxiao/mchat/ops/scripts/gamecenter-remote-pipeline-build.sh {slug}
```

部署 MChat Cloud（10.98.8.15）：`bash ops/scripts/deploy-remote-cloud.sh 10.98.8.15`

### 9.3 聊天里用户体验

1. 用户在群组说：「把 Loading 版本号改成 ver:2.0」
2. Agent 调 `patch_gamecenter_project_file` → 显示 change id
3. **同一轮**自动触发远程 pipeline → 显示 `🔨 构建 built` 和试玩链接
4. 用户强刷试玩页验收

无需再手动跑 pipeline，也**不必** `publish`（pipeline 已更新 `:5099` 用的目录）。

### 9.4 失败时怎么查

| 现象 | 处理 |
|------|------|
| patch 成功但没有「自动编译」 | 管理端是否勾选自动编译；`build_command` 是否填写 |
| 自动编译 SSH 失败 | 10.98.8.15 → 编译机免密、`GAMECENTER_BUILD_SSH_HOST` |
| 构建超时 | 调大 `build_timeout_seconds`（默认 1800） |
| Agent 说成功但试玩不变 | 看构建输出是否有 `Upload OK`；勿信无 change id 的 patch |

构建日志在服务器：`data/devbridge/gamecenter/<slug>/builds/<id>/stdout.log`

---

## 10. 相关文档

- Agent 接入设计：`docs/gamecenter-agent-integration.zh.md`
- 远程触发脚本：`ops/scripts/gamecenter-remote-pipeline-build.sh`
- Mac 环境示例：`ops/scripts/gamecenter-local.env.example`
- Windows 环境示例：`ops/scripts/gamecenter-local.env.windows.example`
