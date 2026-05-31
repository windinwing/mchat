# 可选短信 Provider（勿提交公有仓库）

Core 仅内置 **dev**（写日志）。真发短信请在本目录添加 provider 插件：

```bash
cp ../../../docs/examples/notify-providers/smsbao.py.example smsbao.py
# 编辑 smsbao.py，填入账号；该文件已在 .gitignore
```

`auto` 会按顺序尝试：smsbao → aliyun → dev。

Provider 需暴露类 `Provider`，实现 `name`、`send_text()`、`send_template()`（可选）。
