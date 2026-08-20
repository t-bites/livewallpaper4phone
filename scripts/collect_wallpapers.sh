#!/bin/bash
# collect_wallpapers.sh — 壁纸元数据采集（模式1：从帖子链接提取）
# 用法: bash scripts/collect_wallpapers.sh
# 输出: site/assets/data/wallpapers.json

BASE_DIR="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
cd "$BASE_DIR" || exit 1
OUT="$BASE_DIR/site/assets/data/wallpapers.json"
PY=.venv/bin/python3
[ -f "$PY" ] || PY=python3

# 帖子列表（来源账号 + 帖子 ID）
declare -A TWEETS
TWEETS=(
  ["xiayitiaoAI"]="2089983524397007194"
  ["aestheticz_hub"]="2090330911497961531"
  ["Aesthetics_Walls"]="2090124422149710067"
  ["Unique_Wallpaper"]="2090346670672208085"
  ["Unique_Wallpaper_2"]="2090339921307267203"
  ["Edimakor_Taiwan"]="2090272078054527409"
  ["1111"]="2090099632810647930"
)

echo "📦 采集壁纸元数据..."
mkdir -p "$(dirname "$OUT")"

# 临时文件
TMP=$(mktemp)
echo "[" > "$TMP"
first=true

for author in "${!TWEETS[@]}"; do
  tid="${TWEETS[$author]}"
  url="https://x.com/i/status/$tid"
  echo "  → @$author ($tid)"

  # yt-dlp 提取每个视频的 JSON 元数据
  yt-dlp --dump-json --no-download "$url" 2>/dev/null | while read -r line; do
    vid=$(echo "$line" | $PY -c "import sys,json;d=json.load(sys.stdin);print(d.get('id',''))" 2>/dev/null)
    [ -z "$vid" ] && continue
    title=$(echo "$line" | $PY -c "import sys,json;d=json.load(sys.stdin);print(d.get('title',''))" 2>/dev/null)
    dur=$(echo "$line" | $PY -c "import sys,json;d=json.load(sys.stdin);print(d.get('duration',0))" 2>/dev/null)
    w=$(echo "$line" | $PY -c "import sys,json;d=json.load(sys.stdin);print(d.get('width',0))" 2>/dev/null)
    h=$(echo "$line" | $PY -c "import sys,json;d=json.load(sys.stdin);print(d.get('height',0))" 2>/dev/null)
    echo "    ✓ $vid ($w×$h, ${dur}s)"
  done
done

echo "]" >> "$TMP"
echo "✅ 采集完成，输出到 $OUT"