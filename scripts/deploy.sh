#!/bin/bash
# deploy.sh — 推送到 GitHub Pages（livewallpaper4phone）
# 站点在 docs/ 目录，GitHub Pages 自动从 /docs 部署
# 用法: bash scripts/deploy.sh "提交消息"
set -u
BASE_DIR="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
cd "$BASE_DIR" || exit 1
MSG="${1:-deploy: $(date '+%F %H:%M')}"

# .nojekyll 防 Jekyll 吞文件
touch docs/.nojekyll

git add -A
if git commit -q -m "$MSG" > /dev/null 2>&1; then
  PUSHED=0
  for try in 1 2 3; do
    if git push origin main >> /dev/null 2>&1; then
      PUSHED=1
      break
    fi
    sleep 10
  done
  if [ "$PUSHED" = "1" ]; then
    echo "✅ 已部署 → https://t-bites.github.io/livewallpaper4phone/"
  else
    echo "❌ 推送失败（$try 次尝试）" >&2
    exit 1
  fi
else
  echo "ℹ️ 无变更，跳过部署"
fi