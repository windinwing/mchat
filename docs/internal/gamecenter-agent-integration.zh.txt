# GameCenter 代码代理接入方案

> 目标：让用户在 MChat 对话里发出类似“修改 `pkg0019-cocos` 登录框位置”的请求，由 Agent 受控修改 `/Users/xiaoxiao/dev/xcx` 下的游戏源码，并完成构建、试玩发布、回退。

## 1. 现状

已确认的环境：

- 小游戏源码根：`/Users/xiaoxiao/dev/xcx/src`
- GameCenter 管理后台：`/Users/xiaoxiao/dev/xcx/gamecenter`
- 远端部署：`10.98.8.15:/opt/xiaoxiao/gamecenter`
- GameCenter 远端服务使用 gunicorn，入口见 `gamecenter/app.py` 与 `deploy/start_gamecenter.sh`
- 各游戏目录是标准 Cocos Creator 项目，普遍存在：
  - `assets/`
  - `build/`
  - `settings/`
  - `library/`
  - `temp/`

当前 GameCenter 已支持：

- 文本资源编辑回写
- 图片资源编辑回写
- 部分编译产物同步
- 远端 publish

也就是说，现有系统已经具备“受控修改项目内容”和“同步试玩产物”的部分能力，但还没有把“代码级修改 + 编译 + 回退 + Chat Agent 调用”串起来。

## 2. 总体原则

### 2.1 不让 MChat 直接裸跑远端命令

MChat 不能直接获得对源码机或 `10.98.8.15` 的任意 shell 权限。

必须通过一个受控执行层暴露有限动作，例如：

- 列出游戏项目
- 读取某个项目允许编辑的源码文件
- 写入补丁
- 构建试玩版
- 发布到试玩目录
- 回滚到某个版本

### 2.2 不直接在生产试玩目录上就地覆盖

必须引入“版本化构建产物 + 原子切换”机制，避免一次构建失败把线上试玩目录打坏。

这里的“线上试玩目录”不一定指公网远端，也可以是**部署在内网源码机上的试玩目录**。关键不是机器在哪，而是不能直接覆盖当前正在被访问的版本。

也就是说，如果源码和 GameCenter 都部署在内网：

1. Agent 可以在内网源码机侧的 bridge 中直接调用固定编译命令
2. 编译完成后直接把产物发布到本机或内网试玩目录
3. 试玩目录仍然必须用“版本目录 + current 切换”方式管理

这样就能实现和“在线改图片后回写”类似的体验，但仍然保留发布安全边界。

### 2.3 不让 Agent 任意改整个仓库

要限定：

- 可编辑项目白名单
- 可编辑目录白名单
- 禁止触碰密钥、部署脚本、系统配置
- 单次改动文件数和 diff 大小限制

### 2.4 源码、构建、试玩发布分层

必须拆成三层目录：

1. 源码层：`/Users/xiaoxiao/dev/xcx/src/<game>`
2. 本机构建层：`build/<target>`
3. 试玩发布层：远端版本目录 + 当前软链接

## 3. 推荐目录规划

以单个游戏 `pkg0019-cocos` 为例。

### 3.1 本地源码目录

- `src/pkg0019-cocos/`

这是唯一允许 Agent 修改的源码目录。

### 3.2 本地构建输出目录

不要直接把试玩目标绑定到源码项目自带 `build/web-mobile`。

建议在项目内继续保留 Cocos 默认输出，但再引入一个受控 staging 目录：

- `src/pkg0019-cocos/build/web-mobile/`：Cocos 原始构建产物
- `src/pkg0019-cocos/build/.mchat-release/<build_id>/`：MChat 归档的发布候选产物

构建完成后，复制或同步：

- `build/web-mobile` -> `build/.mchat-release/<build_id>`

### 3.3 远端试玩目录

试玩目录不要只保留一个目录。

建议：

- `/opt/xiaoxiao/gamecenter/playables/pkg0019-cocos/releases/<build_id>/`
- `/opt/xiaoxiao/gamecenter/playables/pkg0019-cocos/current` -> 指向某个 `releases/<build_id>`

试玩访问统一指向：

- `.../playables/pkg0019-cocos/current/`

发布流程应为：

1. 上传新版本到 `releases/<build_id>`
2. 校验完成
3. 原子切换 `current`

如果源码机和试玩机是同一台，这里的“上传”可以退化成：

1. 把本地构建产物复制到 `releases/<build_id>`
2. 校验完成
3. 原子切换 `current`

### 3.4 回退目录

建议：

- 本地保留最近 10 个 `build/.mchat-release/<build_id>`
- 远端保留最近 20 个 `releases/<build_id>`

## 4. MChat 融合方式

### 4.1 不直接耦合到普通聊天主链路

不要让所有普通聊天都天然拥有“改游戏代码”的能力。

应该作为一组明确的 Agent / Skill 能力挂载：

- `gamecenter-project-list`
- `gamecenter-project-read`
- `gamecenter-project-patch`
- `gamecenter-project-build`
- `gamecenter-project-publish`
- `gamecenter-project-rollback`
- `gamecenter-project-status`

### 4.2 推荐工作流

用户在 MChat 中说：

- “修改 `pkg0019-cocos` 登录框，把它上移 40px。”

系统流程：

1. 路由到 GameCenter 代码代理 Agent
2. Agent 识别目标项目、目标文件、目标改动意图
3. 调 `project-read` 读取候选文件
4. 生成 patch
5. 调 `project-patch` 写入工作副本
6. 调 `project-build` 生成候选构建
7. 构建通过后，返回试玩链接或待发布状态
8. 用户确认后再 `project-publish`
9. 任意时点可 `project-rollback`

### 4.3 推荐分成“草稿”和“发布”两步

不要默认“改完就上线试玩”。

建议状态：

- `draft`：已改源码，尚未构建
- `built`：已构建，待验收
- `published`：已切换到当前试玩版本
- `rolled_back`：已回退

## 5. 权限模型

### 5.1 角色建议

建议最少四档：

- `viewer`：只能看项目状态、版本历史、试玩链接
- `editor`：允许发起代码改动和构建
- `publisher`：允许发布试玩版
- `admin`：允许回退、调整白名单和策略

### 5.2 项目级白名单

建议建立配置表：

- 哪些群组可以改哪些项目
- 哪些用户可以发布哪些项目
- 哪些目录可写

### 5.3 文件级白名单

Agent 可写目录建议限制为：

- `assets/`
- `packages/`（如有业务脚本）
- 必要的 `settings/` 中白名单文件

默认禁止：

- `.env`
- `deploy/`
- 服务启动脚本
- 证书与密钥
- `library/`
- `temp/`

## 6. 回退机制

### 6.1 回退维度

必须同时记录三类信息：

1. 源码 patch / commit
2. 本地构建版本
3. 远端发布版本

### 6.2 推荐实现

如果 `xcx` 仓库本身是 Git 仓库，最稳的方式是：

- 每次 Agent 修改前自动创建一个 worktree 或分支快照
- 每次完成 patch 后生成一个 commit
- 记录 `commit_sha`

如果不能依赖 Git，也至少要记录：

- 被修改文件清单
- 修改前备份
- 修改后构建版本号

### 6.3 回退动作

回退分两种：

1. 仅回退试玩发布：切换远端 `current` 到旧版本
2. 同时回退源码：把源码恢复到指定 commit / patch 快照

MVP 建议先做第一种，第二种作为增强。

## 7. 推荐引入一个 GameCenter Bridge

不要让 MChat 直接 SSH + 改文件 + 编译。

建议新增一个桥接服务，优先部署在**内网源码机**或与 GameCenter 同机：

- 名称：`gamecenter-bridge`
- 职责：
  - 受控暴露项目白名单动作
  - 管理工作副本
  - 触发构建
  - 同步发布目录
  - 记录版本与回退元数据

MChat 只通过这个桥接层调用，而不是直接操作 `xcx` 目录。

在你当前的真实场景里，更推荐：

1. `gamecenter-bridge` 与源码目录 `/Users/xiaoxiao/dev/xcx/src` 共机部署
2. 由 bridge 直接调用固定编译命令
3. 由 bridge 直接复制/切换试玩版本目录
4. 需要公网访问时，再由 GameCenter 或 Nginx 暴露 `current`

### 7.1 当前实现方向已进一步抽象

当前代码结构不再把 `gamecenter` 当作唯一桥接目标，而是：

1. `devbridge` 作为通用桥接入口层
2. `rooted project bridge` 作为通用目录型项目桥接基类
3. `gamecenter` 作为第一个 provider 配置实例

这意味着后续如果要接入别的开发中心、别的源码目录、别的构建器，不需要复制整套桥接协议，只需要：

1. 增加一个新的 provider 配置
2. 按需要覆盖少量 provider 专属逻辑

也就是说，`gamecenter` 现在是“provider”，不是“整套桥接能力本身”。

## 8. 推荐数据模型（MChat 侧）

建议在 MChat 中增加：

- `project_workspaces`
- `project_change_requests`
- `project_change_runs`
- `project_builds`
- `project_releases`
- `project_release_rollbacks`

最少字段包括：

- 项目名
- 发起用户
- 发起群组
- 请求内容
- 关联会话 ID
- 改动摘要
- 修改文件列表
- 构建状态
- 发布状态
- 当前 release id
- 上一个 release id
- 回退记录

## 9. 构建与发布建议

### 9.1 构建命令不要由 Agent 自由生成

应由配置固定，例如：

- `cocos build --platform web-mobile ...`
- 或由项目自带脚本统一封装

MChat 只传项目名和版本号，不拼接任意 shell。

### 9.2 产物校验

发布前至少校验：

- 入口文件存在
- 资源目录完整
- 构建时间戳正常
- 产物大小不为 0

### 9.3 发布方式

推荐：

1. 本地构建完成
2. rsync 到远端 `releases/<build_id>`
3. 远端校验通过
4. 切换 `current`

## 10. 与群组能力的关系

这块最适合放进群组协作模型里，而不是个人私有能力。

建议：

- 某个群组绑定可操作的游戏项目列表
- 群组共享该项目的记忆、提示词、改动规范
- 群组共享常用的发布 SOP

这意味着：

- 群组知识库可存放项目文档、UI 规范、目录说明
- 群组记忆可存放提示词模板和改动约束
- 群组默认 Skill 可绑定 GameCenter Bridge 能力

## 11. 推荐实施顺序

### Phase 1：只读接入

- 在 MChat 中增加项目白名单配置
- 让 Agent 能列项目、读文件、看构建状态
- 不允许写入和发布

当前已落地：

- 通用 `devbridge` provider registry
- 通用 `rooted project bridge` 基类
- `gamecenter` 作为第一个 provider
- 只读 API：列项目 / 看项目状态 / 列文件 / 读文件
- 内部聊天只读工具：列项目、读文件、看构建状态

### Phase 2：受控修改与本地构建

- 通过 bridge 改源码工作副本
- 执行固定构建命令
- 生成候选 build
- 返回试玩预览地址

当前开始落实：

- `project-patch`：单文件受控改写、修改历史记录、原文备份、可撤销
- `project-build`：固定命令构建、stdout/stderr 保存、本地 snapshot 归档
- `change:list` / `change:revert`：便于审阅和撤销

### Phase 3：发布与回退

- 版本化上传到远端 releases
- 原子切换 current
- 一键回退

### Phase 4：产品化融合

- 在 MChat 对话中完整串联需求 -> 改动 -> 构建 -> 发布 -> 回退
- 记录审计日志和版本历史

## 12. 结论

如果要把这件事做好，关键不是“让 Agent 直接改代码”，而是：

1. 受控项目白名单
2. 固定构建管线
3. 版本化发布目录
4. 可回退
5. 群组级知识、记忆和项目权限绑定

只有这五件一起成立，MChat 才适合接入 `gamecenter` 的代码改动和试玩发布能力。