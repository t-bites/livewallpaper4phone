#!/bin/bash
# deploy.sh — 推送到 GitHub Pages（livewallpaper4phone 公开仓）
# 用法: bash scripts/deploy.sh "消息"
set -u
BASE_DIR="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
cd "$BASE_DIR" || exit 1
SITE_REPO="https://github.com/t-bites/livewallpaper4phone.git"
MSG="${1:-deploy: $(date '+%F %H:%M')}"

# .nojekyll 防 Jekyll 吞文件
touch docs/.nojekyll

TMP=$(mktemp -d)
cp -r docs/* "$TMP/"
cd "$TMP" || exit 1
git init -b main 2>/dev/null
git config user.name "t-bites"
git config user.email "taoy3260@gmail.com"
git add -A
if git commit -q -m "$MSG" > /dev/null 2>&1; then
  PUSHED=0
  for try in 1 2 3; do
    if git push -f "$SITE_REPO" main >> /dev/null 2>&1; then
      PUSHED=1
      break
    fi
    sleep 10
  done
  if [ "$PUSHED" = "1" ]; then
    echo "✅ 已部署 → https://t-bites.github.io/livewallpaper4phone/"
  else
    echo "❌ 部署失败（push 挂起）"
  fi
else
  echo "✅ 无变更（已是最新部署）"
fi
cd "$BASE_DIR"
rm -rf "$TMP"