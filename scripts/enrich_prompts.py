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
