#!/usr/bin/env python3
"""collect_wallpapers.py — 壁纸元数据采集+自动分类+增量合并
模式1: 从 X 帖子链接提取（支持单链接或批量列表）
输出: site/assets/data/wallpapers.json

用法:
  python scripts/collect_wallpapers.py              # 批量采集帖子列表
  python scripts/collect_wallpapers.py --url <URL>  # 单链接采集
"""
import json, os, re, subprocess, sys, time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "site" / "assets" / "data" / "wallpapers.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

# ========== 帖子列表（来源账号 + 帖子 ID）==========
TWEETS = [
    ("xiayitiaoAI", "2089983524397007194"),
    ("aestheticz_hub", "2090330911497961531"),
    ("Aesthetics_Walls", "2090124422149710067"),
    ("Unique Wallpaper", "2090346670672208085"),
    ("Unique Wallpaper", "2090339921307267203"),
    ("Edimakor Taiwan", "2090272078054527409"),
    ("11:11", "2090099632810647930"),
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
    # 常见手机壁纸比例（竖屏）
    ratios = {
        (0.45, 0.47): "9:20",   # 20:9=0.45
        (0.47, 0.49): "9:19.5", # 19.5:9=0.4615
        (0.49, 0.52): "9:18",   # 18:9=0.5
        (0.52, 0.58): "9:16",   # 16:9=0.5625
        (0.95, 1.05): "1:1",
    }
    for (lo, hi), label in ratios.items():
        if lo <= r < hi:
            return label
    return f"{w}:{h}"

def classify_tags(title, author):
    """从标题/作者关键词自动打标签"""
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
    """从比例推荐手机型号"""
    m = {
        "9:16": ["iPhone 6/7/8/SE", "Samsung A系列", "通用"],
        "9:18": ["Samsung S8/S9", "通用"],
        "9:19.5": ["iPhone X/11/12/13/14/15", "Samsung S20/S23", "华为 Mate 60"],
        "9:20": ["Samsung S20+/S22+", "小米 14", "OPPO Find X7"],
        "1:1": ["通用（方形裁剪）"],
        "其他": ["通用"],
    }
    return m.get(ar, ["通用"])

def extract_prompt(title, body_hint=""):
    """从标题和正文中提取提示词（初始阶段手动补充）"""
    # 自动检测标题中的 prompt 部分
    t = title
    patterns = [
        r'prompt[:\s]*["\']?(.*?)(?:["\']?$|https|\s{2,})',
        r'提示词[：:\s]*(.*?)(?:$|https|\s{2,})',
    ]
    for p in patterns:
        m = re.search(p, t, re.I)
        if m:
            return m.group(1).strip()
    return None

# ========== 采集核心 ==========
def extract_video_metadata(tweet_url, author):
    """用 yt-dlp 提取帖子中每个视频的元数据"""
    try:
        result = subprocess.run(
            ["yt-dlp", "--dump-json", "--no-download", tweet_url],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            print(f"  ⚠️ yt-dlp 失败: {result.stderr[:100]}")
            return []
        items = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            vid = d.get("id", "")
            if not vid:
                continue
            title = d.get("title", "").strip()
            w = d.get("width", 0) or 0
            h = d.get("height", 0) or 0
            dur = d.get("duration", 0) or 0
            # 获取视频直链（提取 http-* 格式的 URL）
            formats = d.get("formats", [])
            video_url = ""
            best_res = 0
            for f in formats:
                if f.get("protocol", "").startswith("http") and not f.get("acodec"):
                    res = (f.get("width", 0) or 0) * (f.get("height", 0) or 0)
                    if res > best_res:
                        best_res = res
                        video_url = f.get("url", "")
            if not video_url:
                # 兜底：用 m3u8 中的最高画质
                for f in formats:
                    if f.get("protocol") == "m3u8_native" and not f.get("acodec"):
                        res = (f.get("width", 0) or 0) * (f.get("height", 0) or 0)
                        if res > best_res:
                            best_res = res
                            video_url = f.get("url", "")
            ar = classify_aspect(w, h)
            item = {
                "id": vid,
                "title": title,
                "author": author,
                "author_url": f"https://x.com/{author.split()[0]}" if author else "",
                "tweet_url": tweet_url,
                "video_url": video_url,
                "width": w,
                "height": h,
                "aspect_ratio": ar,
                "quality": classify_quality(w, h),
                "duration": dur,
                "tags": classify_tags(title, author),
                "prompt": extract_prompt(title),
                "prompt_source": "tweet" if extract_prompt(title) else "unknown",
                "source": author,
                "phone_types": phone_types_from_ratio(ar),
                "collected_at": time.strftime("%Y-%m-%d"),
            }
            items.append(item)
            print(f"    ✓ {vid} {w}x{h} {ar} {dur}s {item['quality']}")
        return items
    except subprocess.TimeoutExpired:
        print(f"  ⚠️ 超时: {tweet_url}")
        return []
    except Exception as e:
        print(f"  ⚠️ 错误: {e}")
        return []

def merge_new(items, existing):
    """增量合并：已存在的保留，新的追加"""
    existing_ids = {e["id"] for e in existing}
    new = [it for it in items if it["id"] not in existing_ids]
    if new:
        existing.extend(new)
        print(f"  ➕ 新增 {len(new)} 条")
    else:
        print(f"  ✅ 无新增（全部已存在）")
    return existing

def main():
    # 加载已有数据
    existing = []
    if OUT.exists():
        existing = json.load(open(OUT))
        print(f"📂 已有壁纸: {len(existing)} 条")

    all_items = []
    for author, tid in TWEETS:
        url = f"https://x.com/i/status/{tid}"
        print(f"📡 @{author} ({tid})")
        items = extract_video_metadata(url, author)
        all_items.extend(items)
        time.sleep(1)  # 间隔，防限流

    print(f"\n📊 本次采集: {len(all_items)} 个视频")
    merged = merge_new(all_items, existing)
    print(f"📊 合并后总数: {len(merged)}")

    # 写出
    OUT.write_text(json.dumps(merged, ensure_ascii=False, indent=1))
    print(f"✅ 已写入: {OUT}")

    # 统计
    from collections import Counter
    ratios = Counter(it["aspect_ratio"] for it in merged)
    quals = Counter(it["quality"] for it in merged)
    print(f"📐 比例分布: {dict(ratios)}")
    print(f"🔍 清晰度分布: {dict(quals)}")

if __name__ == "__main__":
    main()