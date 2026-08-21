# 设计文档：数据去重、提示词管道、弹窗改版与上报入口

> 日期：2026-08-21
> 状态：已与需求方确认设计，待实现
> 注：本文件放仓库根 `specs/`（不放 `docs/`，避免发布到线上站点）

## 背景与目标

站点聚合 X 上的手机动态壁纸视频。当前存在四个问题：

1. 同一帖子常提取出 2 个视频（一个是演示/对比视频，一个是真壁纸），被拆成两条记录；另有跨帖引用导致的完全重复条目
2. AI 提示词大多不在帖子正文而在评论区/thread 中，现有正则提取拿不到
3. 视频预览弹窗太小（600px 宽、视频限高 500px），详情在视频下方需滚动
4. 缺少便捷的壁纸上报入口，新发现的好帖要手动改脚本配置
5. 网格卡片默认黑屏（鼠标移入才加载视频），缺少静态预览图

## 模块 1：视频去重（人工指定）

### 配置格式

`scripts/collect_wallpapers.py` 的 `TWEETS` 改为结构化列表：

```python
TWEETS = [
    {"author": "xiayitiaoAI", "id": "2089983524397007194",
     "keep": "2089982426051448832"},          # 指定保留的 media ID
    {"author": "...", "id": "...", "keep": "last"},  # 或 "first"/"last"/整数序号
]
```

### 解析规则

优先级：显式 media ID > `"first"`/`"last"` > 整数序号（1 起）。
未配置 `keep` 的新帖：默认 `"last"` 并打印醒目警告提醒人工复核。

### 全局去重

- 以 X media ID 为全局主键，单次运行内 + 与已有 `wallpapers.json` 双重去重
- 重复时保留配置顺序中先出现的条目（原帖作者优先于引用者，如 Edimakor 引用夏一跳的视频归夏一跳）
- 首次运行用新逻辑重建 `wallpapers.json`（现 23 条含 4 条完全重复，去重后约 15 条有效）

### 初始 keep 值确定

实现时下载每对候选视频的缩略图目视比对，确定初始 `keep` 配置；不确定的标记出来请需求方复核。

## 模块 2：提示词 AI 爬取管道

新建 `scripts/enrich_prompts.py`。技术路径已实测验证：

```
① GET api.fxtwitter.com/status/<id>
      → 帖子完整正文（JSON、免认证、无截断）
② GET r.jina.ai/https://x.com/<author>/status/<id>
      → 会话页 markdown，正则提取作者本人回复的 tweet ID
③ 对每个回复 ID 再走 ①
      → 回复全文（绕过页面 "Show more" 截断）
④ LLM 从「正文 + 作者回复」中提取提示词
```

### LLM 接入

OpenAI 兼容 `/chat/completions` 接口：
- `OPENAI_API_KEY`（必需）
- `OPENAI_BASE_URL`（可选，默认官方地址）
- `LW4P_MODEL`（可选，默认 `gpt-4o-mini`）

LLM 返回结构化 JSON：`{prompt: str|null, source: "tweet"|"thread_reply"|null}`。
要求返回干净的提示词正文（剥离「Seedance 2.5提示词：」等前缀说明）。

### 缓存与合并

- 原始抓取缓存：`data/raw/tweet_<id>.json`（fxtwitter 与 jina 响应）
- 提取结果缓存：`data/raw/prompts.json`，键为 status ID；已有缓存不重复调 LLM
- 合并进 `wallpapers.json`：按 `tweet_url` 解析 status ID 匹配条目，写入 `prompt` 与 `prompt_source`（`tweet` / `thread_reply` / `unknown`）

### 错误处理

- 无 API key：打印配置说明后优雅退出
- 网络/接口失败：跳过该帖并汇总报告，不影响其他帖子
- LLM 调用失败：重试一次，仍失败则 `prompt_source="unknown"`
- jina 免费档限速：请求间 sleep，支持可选 `JINA_API_KEY`

## 模块 3：预览弹窗左右分栏改版

仅改 `docs/assets/style.css`（及必要的 app.js 内联样式），无新增文案。

### 桌面端 ≥900px

- 弹窗宽度 `min(1100px, 92vw)`，flex 左右布局
- 左侧视频区：高 `min(82vh)`，黑底居中，`object-fit: contain` 保持比例大屏播放
- 右侧详情面板：固定宽 380px，内部可滚动；标题/元信息/提示词/适配机型/下载按钮默认全部展开可见

### 移动端 <900px

退化为上下堆叠（现状逻辑），视频限高 55vh，详情在下方随弹窗滚动。

## 模块 4：壁纸上报入口（GitHub Issue 中转）

仓库：`t-bites/livewallpaper4phone`。纯静态站无法直接写数据，用 GitHub Issue 中转。

### 前端（index.html + app.js + style.css + i18n）

- 导航栏新增「提交壁纸」按钮（新增 i18n key：`nav_submit` 及表单相关文案，zh/en 各一份）
- 点击打开上报弹窗：
  1. **密码校验**：输入密码 → WebCrypto SHA-256 → 与 JS 中哈希常量 `SUBMIT_PASSWORD_SHA256` 比对（不存明文）。通过后写入 `localStorage`，后续免输。错误则提示且不跳转
  2. **表单**：X 帖子链接（必填，正则校验 `(x|twitter).com/<user>/status/<数字ID>`）+ 备注（选填）
  3. **提交**：拼接预填参数在新标签页打开
     `https://github.com/t-bites/livewallpaper4phone/issues/new?title=[壁纸上报]+status_<id>&body=<链接+备注+时间>`
- 密码值由实现方生成随机密码，交付时告知需求方，并说明更换方法（本地计算新 SHA-256 替换常量）

### 采集端（collect_wallpapers.py 新增 --from-issues）

- `gh issue list -R t-bites/livewallpaper4phone --state open --json number,title,body`
- 过滤标题前缀 `[壁纸上报]`，正则提取 status ID，与 TWEETS 配置去重后并入本次采集队列
- 采集成功后自动关闭对应 issue（`--auto-close` 开关控制，默认开）；gh 不可用时打印提示跳过，不阻塞主流程

## 模块 5：网格静态缩略图

现状：卡片默认黑底占位，hover 才 fetch 视频播放（移动端无 hover，永远黑屏）。

### 采集端

- yt-dlp 元数据含 `thumbnail` 字段（`pbs.twimg.com/amplify_video_thumb/<id>/img/*.jpg`，已实测可直连、无 referer 限制）
- 采集时下载缩略图到 `docs/assets/thumbs/<media_id>.jpg`（本地化，避免热链失效），字段名 `thumb` 存相对路径
- 已有条目补跑时增量下载缺失的缩略图；下载失败不阻塞，`thumb` 留空走黑底兜底

### 前端

- 卡片占位层渲染 `<img src="assets/thumbs/..." loading="lazy">` 铺满（`object-fit: cover`），替代纯黑背景
- hover 换成视频播放的逻辑不变（视频盖在缩略图上）
- 弹窗 `<video>` 加 `poster` 属性，加载中也有画面

## 测试与验收

- **Python 单元测试**（纯函数，无需网络）：keep 解析优先级、同运行内去重、跨运行去重保留原帖、issue 正文解析 status ID。LLM/fxtwitter/jina 用保存的原始响应 fixture 离线测解析逻辑
- **采集冒烟**：`--dry-run` 标志只打印计划不写文件；真实跑一遍核对输出条数与去重结果
- **前端手测清单**：桌面/移动断点弹窗布局、详情默认可见、网格缩略图默认显示（含移动端）、hover 视频正常替换、上报弹窗密码错误/正确两态、非法链接拦截、zh/en 文案切换
- **端到端**：跑通 enrich_prompts.py 后抽查夏一跳帖的提示词与原帖评论区一致

## 不做的事（YAGNI）

- 不引入任何构建工具/框架/后端服务
- 不做用户系统——密码哈希属弱防护，仅挡随手滥用，接受此限制
- 不自动回复/评论 issue，不做提交统计
