# 去重+提示词管道+弹窗改版+上报入口 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复视频重复、用 AI 爬取提示词、弹窗左右分栏改版、网格静态缩略图、密码保护的上报入口。

**Architecture:** Python 采集端（collect_wallpapers.py 重构 + 新增 enrich_prompts.py + 共享纯函数模块），前端纯静态（CSS 弹窗分栏 + JS 缩略图/上报表单）。数据流：yt-dlp/fxtwitter/jina → wallpapers.json → 静态站。

**Tech Stack:** Python 3.12（requests、pytest）、原生 HTML/CSS/JS、WebCrypto SHA-256、GitHub Issue 中转。

## Global Constraints

- 设计文档：`specs/2026-08-21-dedup-prompts-modal-submit-design.md`（需求以此为准）
- 不引入构建工具/框架/后端；Python 仅用 requests，不用其他三方依赖
- 测试用 pytest，测试文件放 `tests/`
- 计划/spec 放仓库根 `plans/`、`specs/`（不放 `docs/`，避免发布到线上站点）
- 提交信息风格沿用现有：`feat:` / `fix:` / `docs:` 小写前缀
- LLM 环境变量：`OPENAI_API_KEY`（必需）、`OPENAI_BASE_URL`（可选）、`LW4P_MODEL`（可选）、`JINA_API_KEY`（可选）

---

### Task 1: 共享纯函数模块 + 单元测试

**Files:**
- Create: `scripts/wallpaper_core.py`
- Create: `tests/conftest.py`
- Test: `tests/test_wallpaper_core.py`

**Interfaces:**
- Produces（后续任务依赖的精确签名）:
  - `select_video(entries: list[dict], keep) -> dict | None` — keep 为 media ID 字符串（优先精确匹配）/ "first" / "last" / None(默认 last) / 1 起整数序号；找不到返回 None
  - `dedupe_by_id(items: list[dict]) -> list[dict]` — 按 id 全局去重保留先出现，跳过无 id 条目
  - `status_id_from_url(url: str) -> str | None` — 匹配 `(x|twitter).com/<user>/status/<id>`
  - `parse_issue_status_ids(issues: list[dict]) -> list[tuple]` — 输入 gh issue JSON（number/title/body），只认标题 `[壁纸上报]` 前缀，返回 `[(number, status_id)]`
  - `extract_reply_ids(markdown: str, screen_name: str, exclude_id: str | None = None) -> list[str]` — 从 jina markdown 提取作者回复 tweet ID，去重保序排除主帖

- [ ] **Step 1: 写 conftest.py 与失败测试**

```python
# tests/conftest.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
```

```python
# tests/test_wallpaper_core.py
import unittest
from wallpaper_core import (select_video, dedupe_by_id, status_id_from_url,
                            parse_issue_status_ids, extract_reply_ids)

E1 = {"id": "111", "width": 720}
E2 = {"id": "222", "width": 1080}
E3 = {"id": "333"}

class TestSelectVideo(unittest.TestCase):
    def test_empty(self):
        self.assertIsNone(select_video([], "first"))
    def test_explicit_id_wins_over_index_semantics(self):
        # media ID 是长数字串，必须先按 ID 精确匹配而不是当序号
        self.assertEqual(select_video([E1, E2], "222"), E2)
    def test_first_last(self):
        self.assertEqual(select_video([E1, E2], "first"), E1)
        self.assertEqual(select_video([E1, E2], "last"), E2)
    def test_none_defaults_to_last(self):
        self.assertEqual(select_video([E1, E2], None), E2)
    def test_index_1_based(self):
        self.assertEqual(select_video([E1, E2], 1), E1)
        self.assertEqual(select_video([E1, E2], "2"), E2)
    def test_index_out_of_range(self):
        self.assertIsNone(select_video([E1], 5))
    def test_unknown_keep(self):
        self.assertIsNone(select_video([E1], "bogus"))

class TestDedupe(unittest.TestCase):
    def test_keeps_first_occurrence(self):
        items = [E1, E2, {"id": "111", "dup": True}, E3]
        out = dedupe_by_id(items)
        self.assertEqual([i["id"] for i in out], ["111", "222", "333"])
        self.assertNotIn("dup", out[0])
    def test_skips_missing_id(self):
        self.assertEqual(dedupe_by_id([{"x": 1}, E1]), [E1])

class TestStatusUrl(unittest.TestCase):
    def test_x_com(self):
        self.assertEqual(status_id_from_url("https://x.com/i/status/123"), "123")
        self.assertEqual(status_id_from_url("https://x.com/foo/status/456?s=20"), "456")
    def test_twitter_com(self):
        self.assertEqual(status_id_from_url("http://www.twitter.com/ab/status/789"), "789")
    def test_invalid(self):
        self.assertIsNone(status_id_from_url("https://example.com/status/1"))
        self.assertIsNone(status_id_from_url(""))

class TestIssueParse(unittest.TestCase):
    def test_extracts_reported_only(self):
        issues = [
            {"number": 1, "title": "[壁纸上报] status_42", "body": "链接: https://x.com/a/status/42\n备注: 好"},
            {"number": 2, "title": "随便聊聊", "body": "https://x.com/a/status/99"},
            {"number": 3, "title": "[壁纸上报] bad", "body": "没有链接"},
        ]
        self.assertEqual(parse_issue_status_ids(issues), [(1, "42")])
    def test_empty(self):
        self.assertEqual(parse_issue_status_ids([]), [])
        self.assertEqual(parse_issue_status_ids(None), [])

class TestReplyIds(unittest.TestCase):
    MD = """
    # 夏一跳 on X: "主帖文本"
    [夏一跳](https://x.com/xiayitiaoAI) 文本 [7:51 AM](https://x.com/xiayitiaoAI/status/100)
    [Aug 19](https://x.com/xiayitiaoAI/status/200) Seedance 提示词...
    [someone](https://x.com/other/status/300) 别人的回复
    [Aug 19](https://x.com/xiayitiaoAI/status/200) 重复链接
    """
    def test_extracts_author_replies_excluding_main_and_dups(self):
        self.assertEqual(extract_reply_ids(self.MD, "xiayitiaoAI", exclude_id="100"), ["200"])
    def test_no_exclude(self):
        self.assertEqual(extract_reply_ids(self.MD, "xiayitiaoAI"), ["100", "200"])
    def test_other_author_ignored(self):
        self.assertEqual(extract_reply_ids(self.MD, "other", exclude_id="100"), ["300"])

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_wallpaper_core.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'wallpaper_core'`

- [ ] **Step 3: 实现 wallpaper_core.py**

```python
# scripts/wallpaper_core.py
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/test_wallpaper_core.py -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/wallpaper_core.py tests/
git commit -m "feat: shared pure functions for video selection/dedupe/parsing + tests"
```

---

### Task 2: 采集器重构（keep 配置 + 全局去重 + 缩略图下载 + --from-issues）

**Files:**
- Modify: `scripts/collect_wallpapers.py`（整体重构）
- Create: `docs/assets/thumbs/`（运行时生成）

**Interfaces:**
- Consumes: Task 1 的 `select_video` / `dedupe_by_id` / `status_id_from_url` / `parse_issue_status_ids`
- Produces: `wallpapers.json` 条目新增字段 `"thumb": "assets/thumbs/<media_id>.jpg" | ""`；CLI 参数 `--url`、`--from-issues`、`--no-auto-close`、`--dry-run`、`--fresh`

- [ ] **Step 1: 目检候选视频缩略图，确定初始 keep 值**

对每个多视频帖子，从 fxtwitter API 拿缩略图 URL 并下载查看：
`curl -s https://api.fxtwitter.com/status/<tweet_id>` → `tweet.media.videos[*].thumbnail`
目视判断哪个是纯壁纸、哪个是演示/对比视频。不确定的问用户。
已知参考：xiayitiaoAI 帖子自述「右边是原视频」且 jina 页面显示第二个视频（...48832）带封面；
aestheticz_hub/Aesthetics_Walls 各有一横一竖，竖屏 9:16 为壁纸候选。

- [ ] **Step 2: 重构 collect_wallpapers.py**

关键改动（完整重写该文件）：

```python
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
import argparse, json, shutil, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import requests
from wallpaper_core import select_video, dedupe_by_id, parse_issue_status_ids

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "docs" / "assets" / "data" / "wallpapers.json"
THUMB_DIR = BASE / "docs" / "assets" / "thumbs"
REPO = "t-bites/livewallpaper4phone"

# ========== 帖子列表（author + 帖子 ID + keep 保留规则）==========
# keep: 具体 media ID | "first" | "last" | 序号(1起)；缺省= last（打印警告提醒复核）
TWEETS = [
    {"author": "xiayitiaoAI",      "id": "2089983524397007194", "keep": "<目检后填>"},
    {"author": "aestheticz_hub",   "id": "2090330911497961531", "keep": "<目检后填>"},
    {"author": "Aesthetics_Walls", "id": "2090124422149710067", "keep": "<目检后填>"},
    {"author": "Unique Wallpaper", "id": "2090346670672208085", "keep": "<目检后填>"},
    {"author": "Unique Wallpaper", "id": "2090339921307267203", "keep": "<目检后填>"},
    {"author": "Edimakor Taiwan",  "id": "2090272078054527409", "keep": "<目检后填>"},
    {"author": "11:11",            "id": "2090099632810647930", "keep": "2090099602653577217"},
    {"author": "4KWallpapers254",  "id": "2090021706593083561"},
    {"author": "4KWallpapers254",  "id": "2090545910875066528"},
    {"author": "4KWallpapers254",  "id": "2090500360947282100"},
    {"author": "4KWallpapers254",  "id": "2090454811066175547"},
    {"author": "4KWallpapers254",  "id": "2090424108739604947"},
]
```

分类函数（classify_quality/classify_aspect/classify_tags/phone_types_from_ratio/extract_prompt）原样保留。
`extract_video_metadata(tweet_url, author)` 改名 `fetch_entries(tweet_url, author)`，逻辑不变但不再直接组 item，
返回 yt-dlp 原始条目列表（含 thumbnail 字段）。新增：

```python
def build_item(d, author, tweet_url):
    """yt-dlp 原始条目 → wallpapers.json 条目"""
    vid = d.get("id", "")
    w = d.get("width", 0) or 0
    h = d.get("height", 0) or 0
    dur = d.get("duration", 0) or 0
    title = d.get("title", "").strip()
    video_url = pick_best_video_url(d.get("formats", []))
    ar = classify_aspect(w, h)
    return {
        "id": vid, "title": title, "author": author,
        "author_url": f"https://x.com/{author.split()[0]}" if author else "",
        "tweet_url": tweet_url, "video_url": video_url,
        "thumb": download_thumb(vid, d.get("thumbnail")),
        "width": w, "height": h, "aspect_ratio": ar,
        "quality": classify_quality(w, h), "duration": dur,
        "tags": classify_tags(title, author),
        "prompt": extract_prompt(title), "prompt_source": "tweet" if extract_prompt(title) else "unknown",
        "source": author, "phone_types": phone_types_from_ratio(ar),
        "collected_at": time.strftime("%Y-%m-%d"),
    }

def download_thumb(media_id, url):
    """下载缩略图到本地 docs/assets/thumbs/<id>.jpg，返回相对路径；失败返回 ''"""
    if not media_id:
        return ""
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

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", help="单帖采集")
    ap.add_argument("--from-issues", action="store_true", help="拉取 GitHub 上报 issue 并入队列")
    ap.add_argument("--no-auto-close", action="store_true", help="--from-issues 时采集成功后不关闭 issue")
    ap.add_argument("--fresh", action="store_true", help="忽略已有 wallpapers.json 全量重建")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划，不请求网络不写文件")
    args = ap.parse_args()

    queue = [(t["author"], t["id"], t.get("keep")) for t in TWEETS]
    issue_map = {}
    if args.from_issues:
        issues = fetch_issues()
        issue_map = {sid: num for num, sid in parse_issue_status_ids(issues)}
        known = {tid for _, tid, _ in queue}
        new = [(f"@issue#{num}", sid, None) for _, sid in parse_issue_status_ids(issues)
               if sid not in known]
        queue.extend(new)
        print(f"📋 issue 上报新增 {len(new)} 帖")

    if args.dry_run:
        for a, tid, k in queue:
            print(f"  将采集 @{a} status={tid} keep={k or '(默认last)'}")
        print(f"共 {len(queue)} 帖（dry-run 结束）"); return

    existing = [] if args.fresh else (json.load(open(OUT)) if OUT.exists() else [])
    existing = dedupe_by_id(existing)  # 清理历史重复
    all_items, collected_sids = [], set()
    for author, tid, keep in queue:
        url = f"https://x.com/i/status/{tid}"
        print(f"📡 {author} ({tid})")
        entries = fetch_entries(url, author)
        kept = select_video(entries, keep)
        if kept is None:
            print("  ⚠️ 未匹配到可保留的视频，跳过"); continue
        if keep in (None, ""):
            print("  ⚠️ 该帖未配置 keep，默认保留最后一个，请人工复核！")
        all_items.append(build_item(kept, author.lstrip("@").split("#")[0] if author.startswith("@issue") else author, url))
        collected_sids.add(tid)
        time.sleep(1)

    merged = dedupe_by_id(all_items)          # 本次运行内去重（跨帖引用）
    merged = merge_new(merged, existing)       # 与已有合并
    OUT.write_text(json.dumps(merged, ensure_ascii=False, indent=1))
    print(f"✅ 已写入 {OUT}（共 {len(merged)} 条）")

    if args.from_issues and not args.no_auto_close:
        for sid, num in issue_map.items():
            if sid in collected_sids:
                close_issue(num); print(f"🔒 已关闭 issue #{num}")

if __name__ == "__main__":
    main()
```

注意：issue 来源帖的 author 用占位（爬到 yt-dlp 后其实有真实作者，可用 `d.get("uploader")` 兜底——在 fetch_entries 里若 author 以 "@issue" 开头则取 uploader 字段替换）。

- [ ] **Step 3: 按 Step 1 目检结果填写 TWEETS 的 keep 值**

- [ ] **Step 4: 冒烟运行**

Run: `python3 scripts/collect_wallpapers.py --dry-run` → 打印 12 帖队列
Run: `python3 scripts/collect_wallpapers.py --fresh`
Expected: 每帖恰好 1 条；总数 ≈12-15；`docs/assets/thumbs/` 出现对应 jpg；JSON 无重复 id：

```bash
python3 -c "
import json
from collections import Counter
d = json.load(open('docs/assets/data/wallpapers.json'))
c = Counter(i['id'] for i in d)
assert not [k for k,v in c.items() if v>1], '仍有重复'
print('OK', len(d), '条，缩略图:', sum(1 for i in d if i['thumb']))"
```

- [ ] **Step 5: pytest 回归 + Commit**

```bash
python3 -m pytest tests/ -q
git add scripts/collect_wallpapers.py docs/assets/data/wallpapers.json docs/assets/thumbs/
git commit -m "feat: collector keep-config dedupe + local thumbnails + issue intake"
```

---

### Task 3: 提示词管道 enrich_prompts.py

**Files:**
- Create: `scripts/enrich_prompts.py`
- Test: `tests/test_enrich.py`

**Interfaces:**
- Consumes: `status_id_from_url`、`extract_reply_ids`（Task 1）；`wallpapers.json`（Task 2 产出）
- Produces: `data/raw/prompts.json`（缓存 `{sid: {prompt, source, _done, _extracted_at}}`）；`wallpapers.json` 条目的 `prompt`/`prompt_source` 更新

- [ ] **Step 1: 写失败测试（LLM 输出容错解析）**

```python
# tests/test_enrich.py
import unittest, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from enrich_prompts import parse_llm_json

class TestParseLlmJson(unittest.TestCase):
    def test_plain(self):
        d = parse_llm_json('{"prompt": "A cat", "source": "thread_reply"}')
        self.assertEqual(d, {"prompt": "A cat", "source": "thread_reply"})
    def test_fenced(self):
        d = parse_llm_json('```json\n{"prompt": "A cat", "source": "tweet"}\n```')
        self.assertEqual(d["prompt"], "A cat")
    def test_surrounding_text(self):
        d = parse_llm_json('结果如下：{"prompt": " A cat ", "source": "tweet"} 完毕')
        self.assertEqual(d["prompt"], "A cat")
    def test_null_prompt(self):
        d = parse_llm_json('{"prompt": null, "source": null}')
        self.assertEqual(d, {"prompt": None, "source": None})
    def test_garbage(self):
        self.assertEqual(parse_llm_json("没有json"), {"prompt": None, "source": None})
    def test_bad_source_normalized(self):
        d = parse_llm_json('{"prompt": "cat", "source": "comment"}')
        self.assertEqual(d["source"], "unknown")

if __name__ == "__main__":
    unittest.main()
```

Run: `python3 -m pytest tests/test_enrich.py -q` → Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 2: 实现 enrich_prompts.py**

```python
#!/usr/bin/env python3
"""enrich_prompts.py — 抓取帖子正文+作者回复，LLM 提取 AI 生成提示词
流水线: fxtwitter 正文 → jina 会话页找作者回复 ID → fxtwitter 回复全文 → LLM 提取
缓存: data/raw/tweet_<id>.json / jina_<id>.md / prompts.json（重跑不重复调 LLM）
环境变量: OPENAI_API_KEY(必需) OPENAI_BASE_URL(可选) LW4P_MODEL(可选) JINA_API_KEY(可选)
"""
import argparse, json, os, re, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import requests
from wallpaper_core import status_id_from_url, extract_reply_ids

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "docs" / "assets" / "data" / "wallpapers.json"
RAW = BASE / "data" / "raw"
PROMPTS_CACHE = RAW / "prompts.json"

SYSTEM_PROMPT = (
    "你是壁纸提示词提取器。输入是 X 帖子及其作者回复的文本 JSON。"
    "判断其中是否包含 AI 生成视频/壁纸的提示词(prompt)。"
    "若有，返回干净的提示词正文本身（去掉「提示词：」「Seedance 2.5提示词：」等前缀与无关说明），"
    "source 标注它来自主帖(tweet)还是作者回复(thread_reply)；若没有，prompt 和 source 均为 null。"
    '只输出 JSON：{"prompt": string|null, "source": "tweet"|"thread_reply"|null}'
)


def fetch_fxtwitter(sid):
    cache = RAW / f"tweet_{sid}.json"
    if cache.exists():
        return json.load(open(cache))
    r = requests.get(f"https://api.fxtwitter.com/status/{sid}", timeout=30)
    r.raise_for_status()
    d = r.json()
    cache.write_text(json.dumps(d, ensure_ascii=False, indent=1))
    return d


def fetch_jina(page_url, sid):
    cache = RAW / f"jina_{sid}.md"
    if cache.exists():
        return cache.read_text()
    headers = {}
    if os.environ.get("JINA_API_KEY"):
        headers["Authorization"] = f"Bearer {os.environ['JINA_API_KEY']}"
    r = requests.get(f"https://r.jina.ai/{page_url}", headers=headers, timeout=60)
    r.raise_for_status()
    cache.write_text(r.text)
    time.sleep(2)  # jina 免费档限速友好
    return r.text


def gather_texts(entry):
    """返回 (status_id, {"main": 正文, "replies": [作者回复全文...]})"""
    sid = status_id_from_url(entry["tweet_url"])
    tw = fetch_fxtwitter(sid).get("tweet", {})
    texts = {"main": tw.get("text") or "", "replies": []}
    sn = (tw.get("author") or {}).get("screen_name") or ""
    if sn:
        md = fetch_jina(f"https://x.com/{sn}/status/{sid}", sid)
        for rid in extract_reply_ids(md, sn, exclude_id=sid):
            try:
                rt = fetch_fxtwitter(rid).get("tweet", {})
                if rt.get("text"):
                    texts["replies"].append(rt["text"])
            except Exception as e:
                print(f"    ⚠️ 回复 {rid} 抓取失败: {e}")
    return sid, texts


def parse_llm_json(content):
    """容错解析 LLM 输出中的 JSON（容忍代码围栏与前后杂文字）。"""
    content = (content or "").strip()
    m = re.search(r"\{.*\}", content, re.S)
    if not m:
        return {"prompt": None, "source": None}
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"prompt": None, "source": None}
    p = d.get("prompt")
    src = d.get("source")
    prompt = p.strip() if isinstance(p, str) and p.strip() else None
    if prompt and src not in ("tweet", "thread_reply"):
        src = "unknown"
    return {"prompt": prompt, "source": src if prompt else None}


def call_llm(cfg, texts, attempts=2):
    body = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(texts, ensure_ascii=False)},
        ],
        "temperature": 0,
    }
    last = None
    for _ in range(attempts):
        try:
            r = requests.post(
                cfg["base_url"].rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {cfg['api_key']}"},
                json=body, timeout=120)
            r.raise_for_status()
            return parse_llm_json(r.json()["choices"][0]["message"]["content"])
        except Exception as e:
            last = e
            time.sleep(2)
    raise last


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 条（调试）")
    ap.add_argument("--force", action="store_true", help="忽略缓存重新提取")
    args = ap.parse_args()

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("❌ 缺少 OPENAI_API_KEY。示例:\n"
              "  export OPENAI_API_KEY=sk-...\n"
              "  export OPENAI_BASE_URL=https://api.deepseek.com/v1  # 可选\n"
              "  export LW4P_MODEL=deepseek-chat                     # 可选")
        return 1
    cfg = {
        "api_key": api_key,
        "base_url": os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "model": os.environ.get("LW4P_MODEL", "gpt-4o-mini"),
    }
    RAW.mkdir(parents=True, exist_ok=True)
    wallpapers = json.load(open(DATA))
    cache = json.load(open(PROMPTS_CACHE)) if PROMPTS_CACHE.exists() else {}

    ok = fail = skip = 0
    targets = wallpapers[: args.limit] if args.limit else wallpapers
    for w in targets:
        sid = status_id_from_url(w.get("tweet_url", ""))
        if not sid:
            continue
        if not args.force and cache.get(sid, {}).get("_done"):
            skip += 1
            continue
        try:
            _, texts = gather_texts(w)
            result = call_llm(cfg, texts)
            result["_done"] = True
            result["_extracted_at"] = time.strftime("%Y-%m-%d")
            cache[sid] = result
            ok += 1
            has = "有" if result["prompt"] else "无"
            print(f"  ✓ {sid}: {has}提示词 ({result['source']})")
        except Exception as e:
            print(f"  ⚠️ {sid}: {e}")
            cache.setdefault(sid, {"prompt": None, "source": "unknown", "_done": False})
            fail += 1
        time.sleep(1)

    for w in wallpapers:
        c = cache.get(status_id_from_url(w.get("tweet_url", "")) or "", {})
        w["prompt"] = c.get("prompt")
        w["prompt_source"] = c.get("source") or "unknown"

    DATA.write_text(json.dumps(wallpapers, ensure_ascii=False, indent=1))
    PROMPTS_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1))
    print(f"✅ 成功 {ok} 失败 {fail} 缓存跳过 {skip} → {DATA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: 测试通过 + 无 key 优雅退出验证**

Run: `python3 -m pytest tests/ -q` → PASS
Run: `unset OPENAI_API_KEY; python3 scripts/enrich_prompts.py` → 打印配置说明退出码 1

- [ ] **Step 4: Commit**

```bash
git add scripts/enrich_prompts.py tests/test_enrich.py
git commit -m "feat: AI prompt enrichment pipeline (fxtwitter+jina+LLM)"
```

---

### Task 4: 弹窗左右分栏改版

**Files:**
- Modify: `docs/assets/style.css:122-171`（弹窗样式段整体替换）
- Modify: `docs/assets/app.js:337-344`（openModal 视频 markup 去内联样式）

- [ ] **Step 1: style.css 弹窗段替换为分栏布局**

删除旧 `.modal { max-width:600px ... }`、`.modal-video { aspect-ratio:9/16 }` 等，替换：

```css
/* 详情弹窗 —— 桌面左右分栏 */
.modal-overlay {
  position: fixed; inset: 0; z-index: 200;
  background: rgba(0,0,0,0.85);
  display: flex; align-items: center; justify-content: center;
  padding: 20px;
}
.modal {
  background: var(--card-bg);
  border-radius: 16px;
  width: min(1100px, 92vw);
  max-height: 92vh;
  overflow: hidden;
  position: relative;
  display: flex;
}
.modal-close {
  position: absolute; top: 12px; right: 12px; z-index: 10;
  background: rgba(0,0,0,0.5); border: none; color: #fff;
  width: 32px; height: 32px; border-radius: 50%;
  cursor: pointer; font-size: 18px;
  display: flex; align-items: center; justify-content: center;
}
.modal-video {
  flex: 1 1 auto; min-width: 0;
  background: #000;
  display: flex; align-items: center; justify-content: center;
  height: min(82vh, 88vh);
}
.modal-video video { width: 100%; height: 100%; object-fit: contain; }
.modal-body {
  width: 380px; flex: 0 0 380px;
  max-height: 92vh; overflow-y: auto;
  border-left: 1px solid var(--border);
  padding: 20px;
}
```

（`.modal-body h2/.meta/.prompt-box/.phone-types/.download-btn` 等子样式保留不动）

移动端断点（并入文件底部已有 @media (max-width: 600px) 或独立块）：

```css
@media (max-width: 899px) {
  .modal { flex-direction: column; width: 100%; max-height: 90vh; overflow-y: auto; }
  .modal-video { flex: none; height: auto; aspect-ratio: 9/16; max-height: 55vh; }
  .modal-body { flex: none; width: 100%; max-height: none; border-left: none; border-top: 1px solid var(--border); padding: 16px; }
}
```

- [ ] **Step 2: app.js openModal 去 inline 样式 + poster**

app.js:340 替换为：

```js
modalVideo.innerHTML = `<video src="${blobUrl}" autoplay loop muted playsinline controls${w.thumb ? ` poster="${w.thumb}"` : ''}></video>`;
```

- [ ] **Step 3: 本地手测**

```bash
cd docs && python3 -m http.server 8000
```
浏览器检查：桌面 ≥900px 左视频右详情同屏可见无需滚动；<900px 上下堆叠；Esc/遮罩点击关闭正常。

- [ ] **Step 4: Commit**

```bash
git add docs/assets/style.css docs/assets/app.js
git commit -m "feat: side-by-side detail modal layout"
```

---

### Task 5: 网格静态缩略图

**Files:**
- Modify: `docs/assets/app.js:247-260`（renderGrid 占位层加 img）
- Modify: `docs/assets/style.css`（缩略图样式）

- [ ] **Step 1: renderGrid 占位层插入缩略图**

app.js 卡片模板 `.video-placeholder` 内、quality-badge 之前加：

```js
${w.thumb ? `<img class="thumb" src="${w.thumb}" alt="" loading="lazy">` : ''}
```

- [ ] **Step 2: CSS**

```css
.video-placeholder .thumb {
  position: absolute; inset: 0;
  width: 100%; height: 100%;
  object-fit: cover;
}
```

hover 播放逻辑不变（现有代码清空 placeholder 后追加 video，自然盖掉 img）。

- [ ] **Step 3: 手测**

刷新页面：卡片默认显示静态图非黑屏；hover 换成视频播放；无 thumb 的条目保持黑底兜底。

- [ ] **Step 4: Commit**

```bash
git add docs/assets/app.js docs/assets/style.css
git commit -m "feat: static thumbnails on grid cards"
```

---

### Task 6: 上报入口（密码校验 + GitHub Issue 中转 + i18n）

**Files:**
- Modify: `docs/index.html`（nav 按钮 + 上报弹窗 markup）
- Modify: `docs/assets/app.js`（密码/表单/跳转逻辑 + i18n 应用）
- Modify: `docs/assets/style.css`（表单样式）
- Modify: `docs/assets/i18n/zh.json`、`en.json`（新 key）

**Interfaces:**
- Consumes: 无后端；GitHub issues/new URL 参数
- Produces: localStorage key `lw4p_submit_ok`；常量 `SUBMIT_PASSWORD_SHA256`（执行时生成随机密码并计算哈希嵌入，交付时告知用户明文）

- [ ] **Step 1: i18n key**

zh.json 追加：

```json
"nav_submit": "提交壁纸",
"submit_title": "提交壁纸",
"submit_pw": "访问密码",
"submit_pw_ph": "输入访问密码",
"submit_url": "X 帖子链接",
"submit_url_ph": "https://x.com/user/status/...",
"submit_note": "备注（可选）",
"submit_note_ph": "补充说明…",
"submit_go": "提交",
"submit_hint": "提交后将跳转 GitHub 创建 Issue，由维护者收录",
"submit_err_pw": "密码错误",
"submit_err_url": "请输入有效的 X 帖子链接"
```

en.json 对应英文（nav_submit:"Submit", submit_title:"Submit a Wallpaper", submit_pw:"Access Password", submit_pw_ph:"Enter password", submit_url:"X Post URL", submit_note:"Note (optional)", submit_go:"Submit", submit_hint:"You'll be redirected to GitHub to create an Issue", submit_err_pw:"Wrong password", submit_err_url:"Please enter a valid X post URL"）。

- [ ] **Step 2: index.html**

nav 加 `<a href="#" id="nav-submit">提交壁纸</a>`；body 尾部加上报弹窗：

```html
<div class="modal-overlay" id="submit-modal" style="display:none" onclick="closeSubmit(event)">
  <div class="modal submit-modal" onclick="event.stopPropagation()">
    <button class="modal-close" onclick="closeSubmit()">✕</button>
    <div class="modal-body submit-body">
      <h2 id="submit-title"></h2>
      <label class="form-label" id="label-pw"></label>
      <input type="password" id="submit-pw" autocomplete="off">
      <label class="form-label" id="label-url"></label>
      <input type="url" id="submit-url">
      <label class="form-label" id="label-note"></label>
      <textarea id="submit-note" rows="2"></textarea>
      <div class="form-error" id="submit-error"></div>
      <button class="download-btn" id="submit-go"></button>
      <div class="download-hint" id="submit-hint"></div>
    </div>
  </div>
</div>
```

- [ ] **Step 3: app.js 逻辑**

```js
// ========== 上报入口 ==========
const SUBMIT_PASSWORD_SHA256 = '<执行时生成>';
const SUBMIT_URL_RE = /^https?:\/\/(www\.)?(x|twitter)\.com\/[A-Za-z0-9_]{1,15}\/status\/(\d+)/;

async function sha256Hex(s) {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
  return [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('');
}

function applySubmitI18n() {
  const set = (id, key) => { const el = document.getElementById(id); if (el) el.textContent = t(key); };
  const ph = (id, key) => { const el = document.getElementById(id); if (el) el.placeholder = t(key); };
  set('submit-title', 'submit_title'); set('label-pw', 'submit_pw'); set('label-url', 'submit_url');
  set('label-note', 'submit_note'); set('submit-go', 'submit_go'); set('submit-hint', 'submit_hint');
  ph('submit-pw', 'submit_pw_ph'); ph('submit-url', 'submit_url_ph'); ph('submit-note', 'submit_note_ph');
}

window.openSubmit = function() {
  applySubmitI18n();
  document.getElementById('submit-error').textContent = '';
  const pw = document.getElementById('submit-pw');
  if (localStorage.getItem('lw4p_submit_ok') === '1') pw.closest('.form-row, div')?.classList.add('hidden') ?? null;
  document.getElementById('submit-modal').style.display = 'flex';
};
window.closeSubmit = function(e) {
  if (e && e.target !== e.currentTarget) return;
  document.getElementById('submit-modal').style.display = 'none';
};

async function doSubmit() {
  const err = document.getElementById('submit-error');
  err.textContent = '';
  const pwEl = document.getElementById('submit-pw');
  if (localStorage.getItem('lw4p_submit_ok') !== '1') {
    if (!pwEl.value) { err.textContent = t('submit_err_pw'); return; }
    const hex = await sha256Hex(pwEl.value);
    if (hex !== SUBMIT_PASSWORD_SHA256) { err.textContent = t('submit_err_pw'); return; }
    localStorage.setItem('lw4p_submit_ok', '1');
    pwEl.parentElement.style.display = 'none';
  }
  const url = document.getElementById('submit-url').value.trim();
  const m = url.match(SUBMIT_URL_RE);
  if (!m) { err.textContent = t('submit_err_url'); return; }
  const note = document.getElementById('submit-note').value.trim();
  const title = `[壁纸上报] status_${m[3]}`;
  const body = `链接: ${url}\n备注: ${note || '-'}\n时间: ${new Date().toISOString()}\n来源: ${location.href}\n`;
  window.open(`https://github.com/t-bites/livewallpaper4phone/issues/new?title=${encodeURIComponent(title)}&body=${encodeURIComponent(body)}`, '_blank', 'noopener');
  window.closeSubmit();
}
// nav 绑定 + submit-go 点击绑定（DOMContentLoaded 段落里）
```

nav-submit 点击 `e.preventDefault(); openSubmit()`；`applyI18nToDOM()` 里调用 `applySubmitI18n()`（元素判空兼容教程页）。

- [ ] **Step 4: CSS 表单样式**

```css
.submit-body input, .submit-body textarea {
  width: 100%; background: #1e1e1e; color: var(--text);
  border: 1px solid var(--border); border-radius: 8px;
  padding: 8px 10px; font-size: 13px; margin-bottom: 10px; outline: none;
}
.submit-body input:focus, .submit-body textarea:focus { border-color: var(--accent); }
.form-label { display:block; font-size: 12px; color: var(--text-muted); margin-bottom: 4px; }
.form-error { color: #ff7675; font-size: 12px; min-height: 16px; margin-bottom: 6px; }
.submit-modal { width: min(420px, 94vw); display: block; }
.hidden { display: none; }
```

- [ ] **Step 5: 生成密码并嵌入**

```bash
openssl rand -hex 8                      # 明文密码，交付时告知用户
python3 -c "import hashlib;print(hashlib.sha256(b'<明文>').hexdigest())"
```
把哈希填入 `SUBMIT_PASSWORD_SHA256`。

- [ ] **Step 6: 手测**

错误密码→红字提示不跳转；正确密码→记住后密码栏隐藏；非法链接→提示；合法链接→新标签打开预填 issue 页；zh/en 切换文案跟随。

- [ ] **Step 7: Commit**

```bash
git add docs/index.html docs/assets/app.js docs/assets/style.css docs/assets/i18n/
git commit -m "feat: password-gated wallpaper submission via GitHub Issues"
```

---

### Task 7: 端到端验证 + README + 收尾

**Files:**
- Modify: `README.md`（目录结构补 enrich_prompts.py/tests/specs/plans）
- Run: 全流程验证

- [ ] **Step 1: 全量重建数据**

```bash
python3 scripts/collect_wallpapers.py --fresh
```
核对：无重复 id、每条有 thumb、比例/清晰度分布合理。

- [ ] **Step 2: 提示词提取（需要用户提供 OPENAI_API_KEY）**

⚠️ 检查点：向用户索取 `OPENAI_API_KEY`（及可选 base_url/model），然后：

```bash
export OPENAI_API_KEY=<用户提供>
python3 scripts/enrich_prompts.py
```
抽查夏一跳帖 prompt 与其评论区原文一致；无提示词条目 prompt_source=unknown。

- [ ] **Step 3: 站点冒烟**

```bash
cd docs && python3 -m http.server 8000 &
curl -sf http://localhost:8000/ | grep -c nav-submit
curl -sf http://localhost:8000/assets/data/wallpapers.json | python3 -c "import json,sys;d=json.load(sys.stdin);print(len(d),'entries')"
kill %1
```

- [ ] **Step 4: README 更新 + 最终回归**

README 目录结构补：`scripts/enrich_prompts.py`、`tests/`、`specs/`、`plans/`、`docs/assets/thumbs/`。
`python3 -m pytest tests/ -q` 全绿后 commit：

```bash
git add README.md
git commit -m "docs: update readme structure"
```

- [ ] **Step 5: 向用户交付密码**

最终总结中告知：上报入口明文密码、更换方法（改 app.js 中 SUBMIT_PASSWORD_SHA256）、enrich_prompts 用法。

## Self-Review 结论

- Spec 覆盖：模块1→Task1/2，模块2→Task3，模块3→Task4，模块4→Task6，模块5→Task2(采集端)/Task5(前端)，测试验收→各任务步骤+Task7 ✓
- 类型一致性：select_video/dedupe_by_id/status_id_from_url/parse_issue_status_ids/extract_reply_ids/parse_llm_json 签名前后一致 ✓
- 无占位符：keep 初值标注"<目检后填>"属 Task2 Step1/3 的显式动作，非遗留 TBD ✓
