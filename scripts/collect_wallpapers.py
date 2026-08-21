#!/usr/bin/env python3
"""collect_wallpapers.py — 壁纸元数据采集+自动分类+增量合并
模式1: 从 TWEETS 配置提取（每帖按 keep 只保留一个真壁纸视频）
模式2: --from-issues 从 GitHub issue 拉取用户上报的帖子
输出: docs/assets/data/wallpapers.json（含本地化缩略图 docs/assets/thumbs/）

用法:
  python scripts/collect_wallpapers.py                 # 按配置批量采集
  python scripts/collect_wallpapers.py --fresh         # 忽略已有数据全量重建
  python scripts/collect_wallpapers.py --from-issues   # 合并处理 GitHub 上报 issue
  python scripts/collect_wallpapers.py --dry-run       # 只打印计划不写文件
"""
import argparse, json, re, shutil, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import requests
from wallpaper_core import select_video, dedupe_by_id, parse_issue_status_ids, split_own_and_borrowed

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "docs" / "assets" / "data" / "wallpapers.json"
THUMB_DIR = BASE / "docs" / "assets" / "thumbs"
REPO = "t-bites/livewallpaper4phone"

# ========== 帖子列表（author + 帖子 ID）==========
# 同帖多个视频全部保留（按推文组织），网格默认展示组内最后一个自有视频
TWEETS = [
    {"author": "xiayitiaoAI",      "id": "2089983524397007194"},
    {"author": "aestheticz_hub",   "id": "2090330911497961531"},
    {"author": "Aesthetics_Walls", "id": "2090124422149710067"},
    {"author": "Unique Wallpaper", "id": "2090346670672208085"},
    {"author": "Unique Wallpaper", "id": "2090339921307267203"},
    {"author": "Edimakor Taiwan",  "id": "2090272078054527409"},
    {"author": "11:11",            "id": "2090099632810647930"},
    {"author": "4KWallpapers254",  "id": "2090021706593083561"},
    {"author": "4KWallpapers254",  "id": "2090545910875066528"},
    {"author": "4KWallpapers254",  "id": "2090500360947282100"},
    {"author": "4KWallpapers254",  "id": "2090454811066175547"},
    {"author": "4KWallpapers254",  "id": "2090424108739604947"},
]

# ========== 分类工具 ==========
def classify_quality(w, h):
    size = max(w, h)
    if size >= 2160: return "4K"
    if size >= 1440: return "2K"
    if size >= 1080: return "FHD"
    return "HD"

def classify_aspect(w, h):
    if w <= 0 or h <= 0: return "其他"
    r = w / h
    ratios = {
        (0.44, 0.47): "9:20",
        (0.47, 0.49): "9:19.5",
        (0.49, 0.52): "9:18",
        (0.52, 0.58): "9:16",
        (0.95, 1.05): "1:1",
    }
    for (lo, hi), label in ratios.items():
        if lo <= r < hi:
            return label
    return f"{w}:{h}"

def classify_tags(title, author):
    t = title.lower() + " " + author.lower()
    tags = []
    mapping = {
        "cat": "猫", "kitten": "猫", "猫": "猫",
        "pikachu": "皮卡丘", "皮卡丘": "皮卡丘",
        "动漫": "动漫", "anime": "动漫",
        "3d": "3D", "三维": "3D",
        "abstract": "抽象", "抽象": "抽象",
        "nature": "自然", "自然": "自然", "风景": "自然",
        "星空": "自然", "star": "自然",
        "fire": "自然", "火焰": "自然",
        "文字": "文字", "quote": "文字",
        "人物": "人物", "girl": "人物", "boy": "人物",
        "pixel": "像素", "像素": "像素",
        "minimal": "极简", "极简": "极简",
        "retro": "复古", "复古": "复古",
        "几何": "抽象", "geometric": "抽象",
        "渐变": "抽象", "gradient": "抽象",
        "fluid": "抽象", "流动": "抽象",
        "粒子": "抽象", "particle": "抽象",
        "ai": "AI生成", "aigc": "AI生成",
    }
    seen = set()
    for kw, tag in mapping.items():
        if kw in t and tag not in seen:
            tags.append(tag)
            seen.add(tag)
    if not tags:
        tags.append("其他")
    if "AI" in title or "AIGC" in title or "AI" in author:
        tags.append("AI生成")
    return tags

def phone_types_from_ratio(ar):
    m = {
        "9:16": ["iPhone 6/7/8/SE", "Samsung A系列", "通用"],
        "9:18": ["Samsung S8/S9", "通用"],
        "9:19.5": ["iPhone X/11/12/13/14/15", "Samsung S20/S23", "华为 Mate 60"],
        "9:20": ["Samsung S20+/S22+", "小米 14", "OPPO Find X7"],
        "1:1": ["通用（方形裁剪）"],
        "其他": ["通用"],
    }
    return m.get(ar, ["通用"])

# ========== 采集核心 ==========
def fetch_own_video_ids(tid):
    """fxtwitter 取帖子自有视频 media ID 列表（带缓存）；失败返回 None"""
    cache = BASE / "data" / "raw" / f"tweet_{tid}.json"
    try:
        if cache.exists():
            d = json.load(open(cache))
        else:
            r = requests.get(f"https://api.fxtwitter.com/status/{tid}", timeout=30)
            r.raise_for_status()
            d = r.json()
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(d, ensure_ascii=False, indent=1))
        vids = (d.get("tweet", {}).get("media") or {}).get("videos") or []
        return [v.get("id") for v in vids if v.get("id")]
    except Exception as e:
        print(f"  ⚠️ fxtwitter 自有视频列表获取失败 {tid}: {e}")
        return None

def pick_best_video_url(formats):
    best_res, url = 0, ""
    for f in formats:
        if f.get("protocol", "").startswith("http") and not f.get("acodec"):
            res = (f.get("width", 0) or 0) * (f.get("height", 0) or 0)
            if res > best_res:
                best_res, url = res, f.get("url", "")
    if not url:
        for f in formats:
            if f.get("protocol") == "m3u8_native" and not f.get("acodec"):
                res = (f.get("width", 0) or 0) * (f.get("height", 0) or 0)
                if res > best_res:
                    best_res, url = res, f.get("url", "")
    return url

def download_thumb(media_id, url):
    """下载缩略图到本地 docs/assets/thumbs/<id>.jpg，返回相对路径；失败返回 ''"""
    if not media_id:
        return ""
    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    dest = THUMB_DIR / f"{media_id}.jpg"
    if dest.exists():
        return f"assets/thumbs/{media_id}.jpg"
    if not url:
        return ""
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        dest.write_bytes(r.content)
        print(f"    🖼 缩略图已保存 {media_id}")
        return f"assets/thumbs/{media_id}.jpg"
    except Exception as e:
        print(f"    ⚠️ 缩略图下载失败 {media_id}: {e}")
        return ""

def fetch_entries(tweet_url):
    """yt-dlp 提取帖子中全部视频的原始条目（含被引用帖子里的视频）"""
    try:
        result = subprocess.run(
            ["yt-dlp", "--dump-json", "--no-download", tweet_url],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            print(f"  ⚠️ yt-dlp 失败: {result.stderr[:100]}")
            return []
        entries = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("id"):
                entries.append(d)
        return entries
    except subprocess.TimeoutExpired:
        print(f"  ⚠️ 超时: {tweet_url}")
        return []
    except Exception as e:
        print(f"  ⚠️ 错误: {e}")
        return []

def build_item(d, author, tweet_url):
    """yt-dlp 原始条目 → wallpapers.json 条目"""
    vid = d.get("id", "")
    w = d.get("width", 0) or 0
    h = d.get("height", 0) or 0
    dur = d.get("duration", 0) or 0
    title = d.get("title", "").strip()
    ar = classify_aspect(w, h)
    return {
        "id": vid,
        "title": title,
        "author": author,
        "author_url": f"https://x.com/{author.split()[0]}" if author else "",
        "tweet_url": tweet_url,
        "video_url": pick_best_video_url(d.get("formats", [])),
        "thumb": download_thumb(vid, d.get("thumbnail")),
        "width": w,
        "height": h,
        "aspect_ratio": ar,
        "quality": classify_quality(w, h),
        "duration": dur,
        "tags": classify_tags(title, author),
        "source": author,
        "phone_types": phone_types_from_ratio(ar),
        "collected_at": time.strftime("%Y-%m-%d"),
    }

def merge_new(items, existing):
    existing_ids = {e["id"] for e in existing}
    new = [it for it in items if it["id"] not in existing_ids]
    if new:
        existing.extend(new)
        print(f"  ➕ 新增 {len(new)} 条")
    else:
        print(f"  ✅ 无新增（全部已存在）")
    return existing

# ========== GitHub issue 上报 ==========
def fetch_issues():
    """gh CLI 拉取 open issue；gh 不可用返回 []"""
    if shutil.which("gh") is None:
        print("⚠️ gh CLI 未安装，跳过 issue 拉取")
        return []
    r = subprocess.run(
        ["gh", "issue", "list", "-R", REPO, "--state", "open", "--json", "number,title,body"],
        capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        print(f"⚠️ gh issue list 失败: {r.stderr[:100]}")
        return []
    return json.loads(r.stdout or "[]")

def close_issue(number):
    subprocess.run(["gh", "issue", "close", str(number), "-R", REPO],
                   capture_output=True, text=True, timeout=30)

# ========== 主流程 ==========
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", help="单帖采集")
    ap.add_argument("--from-issues", action="store_true", help="拉取 GitHub 上报 issue 并入队列")
    ap.add_argument("--no-auto-close", action="store_true", help="--from-issues 时采集成功后不关闭 issue")
    ap.add_argument("--fresh", action="store_true", help="忽略已有 wallpapers.json 全量重建")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划，不请求网络不写文件")
    args = ap.parse_args()

    queue = [(t["author"], t["id"]) for t in TWEETS]
    issue_map = {}
    if args.from_issues:
        issues = fetch_issues()
        reported = parse_issue_status_ids(issues)
        issue_map = {sid: num for num, sid in reported}
        known = {tid for _, tid in queue}
        new = [(f"@issue#{num}", sid) for num, sid in reported if sid not in known]
        queue.extend(new)
        print(f"📋 issue 上报新增 {len(new)} 帖")

    if args.dry_run:
        for a, tid in queue:
            print(f"  将采集 {a} status={tid}")
        print(f"共 {len(queue)} 帖（dry-run 结束）")
        return

    existing = [] if args.fresh else (json.load(open(OUT)) if OUT.exists() else [])
    existing = dedupe_by_id(existing)  # 清理历史重复

    # 预取各帖自有视频 ID（用于引用归属判定）
    own_map = {}
    for _, tid in queue:
        ids = fetch_own_video_ids(tid)
        own_map[tid] = set(ids) if ids is not None else None
    claimed = {}  # media_id -> 认领的帖子（配置顺序先到先得）
    for _, tid in queue:
        for mid in own_map[tid] or []:
            claimed.setdefault(mid, tid)

    all_items, collected_sids = [], set()
    for author, tid in queue:
        url = f"https://x.com/i/status/{tid}"
        print(f"📡 {author} ({tid})")
        entries = fetch_entries(url)
        if not entries:
            continue
        own_ids = own_map.get(tid)
        own, borrowed = split_own_and_borrowed(entries, own_ids or set())
        if own_ids is None:
            print("  ⚠️ 未获取到自有视频列表，全部条目归本组（降级模式）")
            group_entries = entries
        else:
            group_entries = own + [b for b in borrowed if b["id"] not in claimed]
        primary_id = group_entries[1]["id"] if len(group_entries) > 1 else group_entries[0]["id"]
        for e in group_entries:
            real_author = author
            if author.startswith("@issue"):  # issue 上报帖：用 yt-dlp 的真实作者名
                real_author = e.get("uploader") or "unknown"
            item = build_item(e, real_author, url)
            item["group"] = tid
            item["is_primary"] = (e["id"] == primary_id)
            all_items.append(item)
        collected_sids.add(tid)
        print(f"  ✓ {len(group_entries)} 个视频，主视频 {primary_id}")
        time.sleep(1)

    merged = dedupe_by_id(all_items)      # 本次运行内去重（跨帖引用兜底）
    merged = merge_new(merged, existing)   # 与已有合并
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(merged, ensure_ascii=False, indent=1))
    print(f"\n✅ 已写入 {OUT}（共 {len(merged)} 条）")

    if args.from_issues and not args.no_auto_close:
        for sid, num in issue_map.items():
            if sid in collected_sids:
                close_issue(num)
                print(f"🔒 已关闭 issue #{num}")

    from collections import Counter
    ratios = Counter(it["aspect_ratio"] for it in merged)
    quals = Counter(it["quality"] for it in merged)
    print(f"📐 比例分布: {dict(ratios)}")
    print(f"🔍 清晰度分布: {dict(quals)}")

if __name__ == "__main__":
    main()
