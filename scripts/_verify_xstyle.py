#!/usr/bin/env python3
"""_verify_xstyle.py — X 风格移动端改版验证（390×844 视口 + 桌面回归）
期望值由本地 wallpapers.json 独立重算。
"""
import json, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = Path(__file__).resolve().parent.parent
PORT = 8956
URL = f"http://localhost:{PORT}/index.html"
TUT = f"http://localhost:{PORT}/tutorials.html"

data = json.load(open(BASE / "docs/assets/data/wallpapers.json"))
primaries = [w for w in data if w.get("is_primary")]

results = []
def check(name, cond):
    results.append((name, bool(cond)))

with sync_playwright() as p:
    b = p.chromium.launch()

    # ================= 移动端 390×844 =================
    pg = b.new_page(viewport={"width": 390, "height": 844},
                    user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148",
                    is_mobile=True, has_touch=True)
    errors = []
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errors.append(str(e)))
    req_fail = []
    pg.on("response", lambda r: req_fail.append((r.url, r.status)) if r.status >= 400 else None)

    pg.goto(URL + "?cb=" + str(int(time.time())), wait_until="networkidle")
    time.sleep(2)

    # 1. Feed 结构：单列、X 卡片
    posts = pg.query_selector_all(".wallpaper-card.x-post")
    check(f"X 卡片渲染 {len(posts)} == primaries {len(primaries)}", len(posts) == len(primaries))
    grid_cols = pg.evaluate("() => getComputedStyle(document.getElementById('grid')).display")
    check(f"grid display={grid_cols} (block=feed)", grid_cols == "block")

    # 2. 卡片头部：头像/显示名/handle/时间
    first = posts[0]
    check("头像存在", first.query_selector(".x-avatar") is not None)
    display = first.query_selector(".x-display").inner_text()
    handle = first.query_selector(".x-handle").inner_text()
    w0 = primaries[0]
    check(f"显示名 '{display}' 含作者", w0["author"].replace("_", " ").split()[0].lower() in display.lower())
    check(f"handle '@{w0['author']}' 正确", handle.startswith("@" + w0["author"]))
    check("时间文案非空", "·" in handle and len(handle.split("·")) == 2)

    # 3. 操作栏：下载/原帖/点赞
    acts = first.query_selector_all(".x-action")
    check("操作栏 3 个动作", len(acts) == 3)
    dl_btn = first.query_selector(".x-action.dl")
    check("下载按钮带真实视频URL", dl_btn.get_attribute("data-url").startswith("https://"))
    link_btn = first.query_selector(".x-action.link")
    check("原帖链接指向 x.com", "x.com" in (link_btn.get_attribute("href") or ""))
    check("桌面 overlay 已隐藏", pg.evaluate("() => { const o = document.querySelector('.wallpaper-card .overlay'); return o ? getComputedStyle(o).display : 'absent'; }") in ("none", "absent"))

    # 4. 点赞交互：点击变红 + localStorage 持久化
    like_btn = first.query_selector(".x-action.like")
    wid = like_btn.get_attribute("data-id")
    like_btn.click(); time.sleep(0.3)
    stored = json.loads(pg.evaluate("() => localStorage.getItem('lw4p_likes')"))
    check("点赞写入 localStorage", wid in stored)
    check("点赞样式 .liked", "liked" in (like_btn.get_attribute("class") or ""))
    like_btn.click(); time.sleep(0.2)
    stored2 = json.loads(pg.evaluate("() => localStorage.getItem('lw4p_likes')"))
    check("取消点赞移除", wid not in stored2)

    # 5. TabBar：3 tab、当前页高亮、提交弹窗
    tabs = pg.query_selector_all(".tabbar a")
    check(f"TabBar {len(tabs)} 个 tab == 3", len(tabs) == 3)
    check("壁纸 tab active", "active" in (tabs[0].get_attribute("class") or ""))
    bar_h = pg.evaluate("() => document.querySelector('.tabbar').getBoundingClientRect().height")
    check(f"TabBar 高度 {bar_h:.0f}px ≥ 48", bar_h >= 48)
    tabs[1].click(); time.sleep(0.5)
    submit_visible = pg.evaluate("() => document.getElementById('submit-modal').style.display === 'flex'")
    check("提交 tab 打开上报弹窗", submit_visible)
    pg.evaluate("() => closeSubmit()")

    # 6. IO 自动播放：滚到第 2 张卡片，等待 blob 拉取后应自动播
    pg.evaluate("() => document.querySelectorAll('.wallpaper-card')[1].scrollIntoView({block:'center'})")
    time.sleep(6)   # fetch-blob 2-5MB 需要时间
    vid_state = pg.evaluate("""() => {
        const vs = [...document.querySelectorAll('.wallpaper-card video')];
        return vs.map(v => ({paused: v.paused, ready: v.readyState >= 2}));
    }""")
    playing = [v for v in vid_state if not v["paused"] and v["ready"]]
    check(f"IO 自动播放生效（{len(playing)} 条在播）", len(playing) >= 1)
    n_vids = pg.evaluate("() => document.querySelectorAll('.wallpaper-card video').length")
    check(f"同时最多 2 条 video DOM（实际 {n_vids}）", n_vids <= 2)

    # 7. 弹窗全屏 sheet
    posts[2].click(); time.sleep(4)
    modal_css = pg.evaluate("""() => {
        const m = document.querySelector('#modal .modal');
        const cs = getComputedStyle(m);
        const rect = m.getBoundingClientRect();
        return {radius: cs.borderRadius, w: rect.width, vw: window.innerWidth};
    }""")
    check("弹窗全屏宽", abs(modal_css["w"] - modal_css["vw"]) < 2)
    check("弹窗直角(radius 0)", modal_css["radius"] == "0px")
    mv = pg.evaluate("() => { const v = document.querySelector('#modal-video video'); return v ? {ready: v.readyState, paused: v.paused} : null; }")
    check("弹窗视频播放中", mv and not mv["paused"] and mv["ready"] >= 2)
    pg.evaluate("() => closeModal()")
    time.sleep(0.5)

    # 8. 筛选 chips 横排 + 有值高亮
    sel_ar = pg.query_selector("#filter-ar")
    sel_ar.select_option(index=1); time.sleep(0.6)
    check("筛选选中 chip 高亮", "filled" in (sel_ar.get_attribute("class") or ""))
    filt_overflow = pg.evaluate("() => { const f = document.getElementById('filters'); return f.scrollWidth > f.clientWidth; }")
    check("筛选条横向可滚动", filt_overflow)
    n_after = len(pg.query_selector_all(".wallpaper-card.x-post"))
    check(f"筛选后卡片减少（{n_after} < {len(primaries)}）", n_after < len(primaries))
    pg.click("#clear-all"); time.sleep(0.4)
    check("清除后 chip 取消高亮", "filled" not in (pg.query_selector("#filter-ar").get_attribute("class") or ""))

    # 9. 无横向溢出 + 底部留白
    ox = pg.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 2")
    check("无横向溢出", ox)
    body_pb = pg.evaluate("() => getComputedStyle(document.body).paddingBottom")
    check(f"body 底部留白({body_pb}) ≥ 56px", float(body_pb.replace("px", "")) >= 56)

    # 10. 教程页 TabBar
    pg.goto(TUT, wait_until="networkidle"); time.sleep(1.5)
    tut_tabs = pg.query_selector_all(".tabbar a")
    check("教程页也有 TabBar", len(tut_tabs) == 3)
    check("教程页 tab 高亮正确", "active" in (tut_tabs[2].get_attribute("class") or ""))
    tut_ox = pg.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 2")
    check("教程页无溢出", tut_ox)

    check("移动端 console 零错误", len(errors) == 0)
    check("移动端无 4xx+ 请求", len(req_fail) == 0)
    if errors: print("MOBILE ERRORS:", errors[:5])
    if req_fail: print("REQ FAIL:", req_fail[:5])
    pg.close()

    # ================= 桌面 1280 回归 =================
    d = b.new_page(viewport={"width": 1280, "height": 900})
    derr = []
    d.on("pageerror", lambda e: derr.append(str(e)))
    d.goto(URL + "?d=" + str(int(time.time())), wait_until="networkidle")
    time.sleep(2)
    d_posts = d.query_selector_all(".wallpaper-card.x-post")
    d_cards = d.query_selector_all(".wallpaper-card:not(.x-post)")
    check(f"桌面仍是网格卡片（{len(d_cards)}），无 X 卡片", len(d_cards) == len(primaries) and len(d_posts) == 0)
    check("桌面无 TabBar", d.query_selector(".tabbar") is None or d.evaluate("() => getComputedStyle(document.querySelector('.tabbar')).display") == "none")
    cols = d.evaluate("() => getComputedStyle(document.getElementById('grid')).gridTemplateColumns.trim().split(/\\s+/).length")
    check(f"桌面多列网格（{cols} 列）", cols >= 3)
    # 桌面 hover 播放回归
    d.hover(".wallpaper-card >> nth=0")
    time.sleep(5)
    hov = d.evaluate("() => { const v = document.querySelector('.wallpaper-card video'); return v ? !v.paused : false; }")
    check("桌面 hover 自动播放保留", hov)
    check("桌面零 pageerror", len(derr) == 0)
    if derr: print("DESKTOP ERRORS:", derr[:3])
    d.close()
    b.close()

passed = sum(1 for _, ok in results if ok)
print(f"\n{'='*44}")
for name, ok in results:
    print(f"  {'✅' if ok else '❌'} {name}")
print(f"{'='*44}\n{passed}/{len(results)} passed")
sys.exit(0 if passed == len(results) else 1)
