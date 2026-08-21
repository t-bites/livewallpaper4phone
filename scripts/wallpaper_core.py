"""wallpaper_core.py — 纯函数集合：视频选择/去重/链接解析（采集与提示词脚本共用）"""
import re

STATUS_URL_RE = re.compile(r"https?://(?:www\.)?(?:x|twitter)\.com/[A-Za-z0-9_]{1,15}/status/(\d+)")


def select_video(entries, keep):
    """从同一帖子的视频条目中按 keep 规则选出一条。
    keep: media ID 字符串 | "first" | "last" | 整数序号(1起) | None(默认 last)
    """
    if not entries:
        return None
    if keep in (None, ""):
        keep = "last"
    for e in entries:  # 精确 media ID 匹配优先于序号语义
        if e.get("id") == str(keep):
            return e
    if keep == "first":
        return entries[0]
    if keep == "last":
        return entries[-1]
    try:
        idx = int(keep)
    except (TypeError, ValueError):
        return None
    return entries[idx - 1] if 1 <= idx <= len(entries) else None


def dedupe_by_id(items):
    """按 id 全局去重，保留先出现的条目。"""
    seen, out = set(), []
    for it in items or []:
        iid = it.get("id")
        if not iid or iid in seen:
            continue
        seen.add(iid)
        out.append(it)
    return out


def status_id_from_url(url):
    m = STATUS_URL_RE.search(url or "")
    return m.group(1) if m else None


def parse_issue_status_ids(issues):
    """从 GitHub issue 列表提取上报的 status ID，返回 [(number, status_id)]。"""
    out = []
    for it in issues or []:
        title = it.get("title") or ""
        if not title.startswith("[壁纸上报]"):
            continue
        sid = status_id_from_url(it.get("body") or "")
        if sid:
            out.append((it.get("number"), sid))
    return out


def extract_reply_ids(markdown, screen_name, exclude_id=None):
    """从 jina 会话页 markdown 提取作者回复 tweet ID（去重、保序、排除主帖）。"""
    ids = []
    pat = re.compile(r"https://x\.com/%s/status/(\d+)" % re.escape(screen_name or ""))
    for m in pat.finditer(markdown or ""):
        tid = m.group(1)
        if tid != exclude_id and tid not in ids:
            ids.append(tid)
    return ids


def split_own_and_borrowed(entries, own_ids):
    """按自有 media ID 集合把 yt-dlp 条目分为 (own, borrowed)，保持原顺序。"""
    own, borrowed = [], []
    for e in entries or []:
        (own if e.get("id") in own_ids else borrowed).append(e)
    return own, borrowed
