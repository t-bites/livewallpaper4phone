# livewallpaper4phone — 手机动态壁纸站

手机动态壁纸发现与指南站。聚合 X 上创作者发布的动态壁纸，支持按手机型号/比例/清晰度筛选，提供设置教程。

## 快速开始

```bash
# 采集壁纸数据
chmod +x scripts/collect_wallpapers.sh
bash scripts/collect_wallpapers.sh

# 本地预览站点
cd site && python3 -m http.server 8000
```

## 目录结构

```
livewallpaper4phone/
├── PLAN.md          # 项目方案
├── AGENTS.md        # 执行手册
├── todo.md          # 改进队列
├── scripts/
│   └── collect_wallpapers.*  # 壁纸数据采集
├── site/             # 静态站点
│   ├── index.html    # 首页（壁纸浏览）
│   ├── tutorials.html # 设置教程
│   └── assets/
└── data/             # 本地数据（不入库）
```