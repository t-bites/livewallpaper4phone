# livewallpaper4phone — 手机动态壁纸站

手机动态壁纸发现与指南站。聚合 X 上创作者发布的动态壁纸，支持按手机型号/比例/清晰度筛选，提供设置教程。

## 快速开始

```bash
# 采集壁纸数据（按推文分组，含缩略图本地化）
python3 scripts/collect_wallpapers.py --fresh

# 提取 AI 提示词（需 OPENAI_API_KEY，可选）
export OPENAI_API_KEY=sk-...
python3 scripts/enrich_prompts.py

# 处理 GitHub 上报 issue（需 gh CLI）
python3 scripts/collect_wallpapers.py --from-issues

# 运行测试
python3 -m pytest tests/ -q

# 本地预览站点
cd docs && python3 -m http.server 8000
```

## 目录结构

```
livewallpaper4phone/
├── PLAN.md            # 项目方案
├── specs/             # 设计文档
├── plans/             # 实现计划
├── scripts/
│   ├── collect_wallpapers.py   # 采集（按推文分组+去重+缩略图+issue 上报）
│   ├── enrich_prompts.py       # 提示词提取（fxtwitter+LLM）
│   └── wallpaper_core.py       # 共享纯函数
├── tests/             # 单元测试
├── data/raw/          # 抓取缓存（不入库）
└── docs/              # 静态站点（GitHub Pages）
    ├── index.html     # 首页（浏览/筛选/详情/上报）
    ├── tutorials.html # 设置教程
    └── assets/
        ├── data/wallpapers.json  # 壁纸数据（按推文分组，is_primary 标记主视频）
        ├── thumbs/               # 视频缩略图（本地化）
        ├── app.js / style.css / i18n/
```