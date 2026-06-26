#!/usr/bin/env bash
# 在 Mac 上执行：把 10.98.8.15 配成通过 Windows/Mac 编译机远程 pipeline 构建
# Usage: configure-gamecenter-remote-build.sh <windows_user> [windows_ip]
set -euo pipefail

WIN_USER="${1:-}"
WIN_IP="${2:-10.98.8.186}"
REMOTE="${3:-10.98.8.15}"
REMOTE_DIR="${MCHAT_DEPLOY_DIR:-/opt/xiaoxiao/mchat}"

if [[ -z "$WIN_USER" ]]; then
  echo "usage: $0 <windows_username> [windows_ip] [mchat_server]" >&2
  echo "example: $0 ZhangSan 10.98.8.186 10.98.8.15" >&2
  exit 1
fi

PIPELINE="/c/Users/${WIN_USER}/dev/mchat/ops/scripts/gamecenter-local-pipeline.sh"
SSH_TARGET="xiaoxiao@${REMOTE}"

echo "==> 测试 10.98.8.15 -> ${WIN_USER}@${WIN_IP}"
if ! ssh "$SSH_TARGET" "ssh -o BatchMode=yes -o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new '${WIN_USER}@${WIN_IP}' 'echo ok'"; then
  echo "WARN: 服务器尚无法 SSH 到 Windows，请先在 Windows 完成 OpenSSH + authorized_keys" >&2
fi

echo "==> 更新 ${REMOTE} .env GameCenter 变量"
ssh "$SSH_TARGET" "bash -s" <<EOF
set -euo pipefail
ENV_FILE='${REMOTE_DIR}/.env'
touch "\$ENV_FILE"

upsert() {
  local key="\$1" val="\$2"
  if grep -q "^\${key}=" "\$ENV_FILE" 2>/dev/null; then
    sed -i "s|^\${key}=.*|\${key}=\${val}|" "\$ENV_FILE"
  else
    echo "\${key}=\${val}" >> "\$ENV_FILE"
  fi
}

upsert GAMECENTER_BUILD_SSH_HOST '${WIN_IP}'
upsert GAMECENTER_BUILD_SSH_USER '${WIN_USER}'
upsert GAMECENTER_BUILD_PIPELINE_SCRIPT '${PIPELINE}'
upsert GAMECENTER_DEPLOY_HOST '${REMOTE}'
upsert GAMECENTER_AUTO_BUILD_AFTER_PATCH 'true'
upsert GAMECENTER_BUILD_COMMAND 'bash ${REMOTE_DIR}/ops/scripts/gamecenter-remote-pipeline-build.sh {slug}'

grep -E '^GAMECENTER_BUILD_|^GAMECENTER_AUTO|^GAMECENTER_DEPLOY' "\$ENV_FILE" || true
EOF

echo "==> 更新 DevBridge admin-settings build_command"
ssh "$SSH_TARGET" "python3 - <<'PY'
import json
from pathlib import Path
p = Path('${REMOTE_DIR}/data/devbridge/admin-settings.json')
data = {}
if p.exists():
    data = json.loads(p.read_text(encoding='utf-8', errors='replace'))
gc = data.setdefault('gamecenter', {})
gc['build_command'] = 'bash ${REMOTE_DIR}/ops/scripts/gamecenter-remote-pipeline-build.sh {slug}'
gc['auto_build_after_patch'] = True
gc['cocos_creator_bin'] = ''
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
print('admin-settings updated')
PY"

echo "==> 重启 Cloud 后端"
ssh "$SSH_TARGET" "systemctl --user restart mchat-cloud 2>/dev/null || systemctl --user restart mchat 2>/dev/null || true"

echo ""
echo "Done. DevBridge build_command -> gamecenter-remote-pipeline-build.sh"
echo "Test: ssh ${SSH_TARGET} 'bash ${REMOTE_DIR}/ops/scripts/gamecenter-remote-pipeline-build.sh pkg0002-3-x-3-8-3ts'"
