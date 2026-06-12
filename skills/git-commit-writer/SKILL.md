---
name: git-commit-writer
description: |
  Help write clear git commit messages after DevBridge patches.
  Use when the user asks to commit, summarize changes, or before git_commit_devbridge_project.
type: prompt
version: 1.0.0
author: MChat
tags: [git, commit, devbridge]
config:
  i18n:
    zh:
      title: Git 提交说明
    en:
      title: Git commit writer
---

# Git 提交说明助手

在用户完成 DevBridge 改码后，帮助撰写 **简洁、可检索** 的 commit message，并调用 `git_commit_devbridge_project`。

## 格式建议

```
<type>(<scope>): <summary>

<body 可选：改了什么、为什么>
```

type：`feat` | `fix` | `refactor` | `chore` | `docs`

## 流程

1. `git_status_devbridge_project` 查看变更文件
2. 必要时 `diff_devbridge_project_change` 理解 diff
3. 生成 message → `git_commit_devbridge_project`

一条 commit 只做一件事；summary 用中文或英文与团队习惯一致。
