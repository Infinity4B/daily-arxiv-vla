# VLA / World Action Model 每日论文卡

一个自动更新的 arXiv 论文精选静态网站：每天检索 VLA（Vision-Language-Action）与 World Action Model 相关论文，用大模型生成中文摘要，并为每篇论文生成独立的阅读页面，部署在 GitHub Pages 上。

在线访问：<https://infinity4b.github.io/daily-arxiv-vla/>

> [!IMPORTANT]
> **仓库历史改写说明（2026-11-07）**
>
> 为缩小仓库体积，本仓库于 2026-11-07 使用 `git filter-repo` 改写了全部 git 历史，并强制推送到 `master`：
>
> - **删除内容**：历史提交中 `site/assets/paper-images/` 目录下的 `*.png`、`*.jpg`、`*.jpeg` 原图（共 803 个文件，约 600MB）。这些原图早已被转换为 WebP 并从当前代码中删除，网站不再使用它们。
> - **未改变的内容**：当前代码和网站文件、每个提交的提交信息、作者和时间，以及除上述图片外的所有文件均保持不变；提交总数不变。
> - **会变化的内容**：所有提交的哈希值都已改变，旧的提交链接会失效；早期部分提交（共 42 个）中引用的 PNG/JPG 首图已不存在。
> - **效果**：仓库克隆体积从约 1.1GB 降到约 400MB。
>
> **如果你 fork 或克隆了本仓库**：旧历史与新历史已无法直接合并。没有自己改动的话，请重新克隆，或执行 `git fetch origin && git reset --hard origin/master`；有自己的改动的话，请把改动 rebase 或 cherry-pick 到新的 `master` 上。请不要把旧历史合并回来，否则这些大文件会重新进入仓库。

## 功能特性

- 🤖 **自动爬取**：每天从 arXiv 检索 VLA / World Action Model 相关新论文，只保留主类目为 cs.CV、cs.AI、cs.CL、cs.LG、cs.MM、cs.RO 的论文，并按链接去重
- 🧠 **AI 中文摘要**：读取论文的 arXiv HTML 全文，通过 ModelScope API 生成中文摘要；支持配置多个模型，某个模型被限流时自动切换到下一个
- 🖼️ **论文首图**：自动从论文 HTML 中提取首图作为卡片封面；原图无法直接下载时，用 Playwright 截取页面中的第一个 figure 兜底
- 🗜️ **图片优化**：构建时把首图统一转为 WebP，并生成 600px 宽的缩略图供首页卡片使用
- 🔍 首页实时搜索，点击卡片可在浮窗中阅读详情
- 📄 每篇论文生成独立的静态详情页，附 arXiv 原文和中文翻译链接
- 🌗 浅色 / 深色 / 跟随系统三种主题
- 💾 记住首页滚动位置，详情页按 arXiv ID 分别记住阅读进度
- 📱 响应式设计，支持移动端
- 📊 可选接入 Google Analytics 4

## 本地开发

### 安装依赖

需要 Python 3.9+；如需运行 Playwright 截图兜底，还需要 Node.js（CI 使用 Node.js 24）。

```bash
pip install -r requirements.txt

# 仅截图兜底需要
npm install
npx playwright install chromium
```

### 环境配置

```bash
cp .env.example .env
# 编辑 .env，填入 MODELSCOPE_ACCESS_TOKEN
```

> 注意：只有 `generate_summaries.py` 会自动读取 `.env`。爬虫和网站构建脚本只读取系统环境变量，如需修改它们的配置（例如检索关键词），请在运行前 `export`，例如 `export ARXIV_QUERY_KEYWORD='all:"VLA"'`。

**摘要生成**（`generate_summaries.py`）：

| 变量 | 说明 | 默认值 |
|---|---|---|
| `MODELSCOPE_ACCESS_TOKEN` | ModelScope API 密钥（**必需**） | — |
| `MODELSCOPE_BASE_URL` | API 基础 URL | `https://api-inference.modelscope.cn/v1/` |
| `MODELSCOPE_MODELS` | 逗号分隔的模型列表，按顺序尝试，被限流时切换下一个 | 空 |
| `MODELSCOPE_MODEL` | 未设置 `MODELSCOPE_MODELS` 时使用的单个模型 | `deepseek-ai/DeepSeek-V3.2` |
| `API_MAX_RETRIES` | 单个模型的调用次数，最多 2 次，超过 2 按 2 处理 | `3`（实际为 2） |
| `HTTP_MAX_RETRIES` | 抓取论文 HTML 的重试次数 | `3` |
| `HTTP_TIMEOUT` | 抓取论文 HTML 的超时时间（秒） | `30` |
| `HTML_MAX_CHARS` | 论文 HTML 送入模型前截断的最大字符数 | `180000` |
| `BATCH_WRITE_SIZE` | 每生成 N 篇摘要写入一次 `papers.md` | `5` |

**arXiv 爬虫**（`arxiv_crawler.py`）：

| 变量 | 说明 | 默认值 |
|---|---|---|
| `ARXIV_QUERY_KEYWORD` | 检索语句，支持 arXiv 查询语法 | 见下方「默认检索语句」 |
| `ARXIV_INIT_RESULTS` | 首次运行（`papers.md` 不存在或为空）时抓取的数量 | `500` |
| `ARXIV_DAILY_RESULTS` | 每日增量更新时抓取的数量 | `20` |
| `ARXIV_PAGE_SIZE` | 每次请求 arXiv API 的分页大小 | `20` |
| `ARXIV_DELAY_SECONDS` | 两次 arXiv 请求之间的间隔（秒），避免被限流 | `10` |
| `ARXIV_MAX_RETRIES` | 检索失败时的重试次数 | `3` |
| `ARXIV_RETRY_BASE_SECONDS` | 重试等待的基础时间（秒） | `30` |

默认检索语句：

```
all:"VLA" OR all:"Vision-Language-Action" OR all:"World Action Model" OR all:"World-Action Model" OR all:"action world model"
```

**网站构建**（`build_site.py`）：

| 变量 | 说明 | 默认值 |
|---|---|---|
| `ARXIV_QUERY_KEYWORD` | 同上，用于生成网站标题 | 默认检索语句 |
| `GA_MEASUREMENT_ID` | Google Analytics 4 的 Measurement ID（如 `G-XXXXXXXXXX`），未配置或格式不对时不加载 GA | 空 |
| `PAPER_IMAGE_REMOTE_BASE` | 全尺寸首图的外部地址前缀，设置后详情页和图片放大从该地址加载全尺寸图（见「部署产物精简」） | 空（使用站内相对路径） |

### 运行流程

```bash
# 1. 爬取论文：papers.md 不存在或为空时做初始化抓取，否则做每日增量更新
python scripts/arxiv_crawler.py

# 2. 为「待生成」的论文生成摘要
python scripts/generate_summaries.py

# 3. 抓取论文首图（已下载过的会自动跳过）
python scripts/fetch_paper_images.py --max-items 30

# 4.（可选）为仍缺图的论文执行 Playwright 截图兜底
python scripts/build_paper_image_fallback_queue.py --max-items 20
npm run paper-image:fallbacks
python scripts/register_paper_image_fallbacks.py

# 5. 构建网站
python scripts/build_site.py
```

`build_site.py` 会在 `site/` 下生成首页、`data.json`、每篇论文的详情页和封面卡页面，并把首图转为 WebP、生成缩略图。

辅助脚本：

- `scripts/clean_summaries.py`：规范化 `papers.md` 中的摘要（去掉代码块标记、调整标题层级，删除缺少「论文概述」的摘要）
- `scripts/clear_summaries.py`：把所有摘要重置为「待生成」，用于整体重新生成

### Google Analytics 4

如需统计页面浏览、搜索和论文阅读行为，在构建前设置 Measurement ID：

```bash
export GA_MEASUREMENT_ID=G-XXXXXXXXXX
python scripts/build_site.py
```

验证时可以打开浏览器开发者工具的 **Network** 面板，搜索 `googletagmanager` 或 `collect`；GA4 后台的实时报告通常会有几分钟延迟。

> Google Analytics 会涉及 Cookie、隐私和数据跨境等合规问题。面向公众提供服务时，请根据所在地法规补充隐私说明，并在必要时增加用户同意机制。

### 本地预览

```bash
cd site
python -m http.server 8000
# 或：npx serve site
```

## GitHub Pages 部署

### 1. 配置仓库

1. 使用公开仓库。私有仓库使用 GitHub Pages 需要付费计划，而且全尺寸首图从 `raw.githubusercontent.com` 加载，私有仓库无法访问。
2. 在 `Settings → Pages` 中，把部署来源（Source）设为 **GitHub Actions**。

### 2. 配置密钥和变量

- **Secret** `MODELSCOPE_ACCESS_TOKEN`（必需）：在 `Settings → Secrets and variables → Actions → Secrets` 中添加。
- **Variable** `GA_MEASUREMENT_ID`（可选）：在同一页面的 **Variables** 中添加。Measurement ID 本来就会出现在网页 HTML 中，放在 Variables 即可；工作流也兼容同名 Secret。

检索关键词、抓取数量、模型列表等都直接写在 `.github/workflows/deploy.yml` 各步骤的 `env` 中，按需修改即可。当前工作流的设置是：每日抓取 80 篇（`ARXIV_DAILY_RESULTS`），分页 10，请求间隔 15 秒；摘要模型通过 `MODELSCOPE_MODELS` 配置多个候选。

### 3. 自动运行

工作流 `.github/workflows/deploy.yml` 在以下两种情况触发：

- 推送到 `master` 或 `main` 分支
- 定时任务：cron `0 4 * * *`，即北京时间每天 12:00。GitHub 的定时任务在高峰期经常延迟，实际开始时间可能晚几个小时。

每次运行依次执行：

1. 爬取 arXiv 新论文
2. 为待生成的论文生成 AI 摘要
3. 抓取论文首图，对仍缺图的论文执行 Playwright 截图兜底（失败不影响后续步骤）
4. 构建网站
5. 把 `papers.md` 和 `site/` 的变化提交回仓库（提交信息带 `[skip ci]`，不会再次触发工作流）
6. 生成精简后的部署产物，部署到 GitHub Pages

### 4. 部署产物精简

全尺寸首图数量多、体积大，全部放进 Pages 产物会让部署变慢甚至超时。因此工作流：

- 构建时设置 `PAPER_IMAGE_REMOTE_BASE=https://raw.githubusercontent.com/<仓库>/<分支>/site`，详情页和图片放大改为从仓库的 raw 地址加载全尺寸图（这些图片已随 `site/` 提交进仓库）；
- 上传 Pages 产物前，从 `site/` 复制出 `_pages/`，排除 `assets/paper-images/` 下的全尺寸图，只保留缩略图；
- `deploy-pages` 的超时放宽到 30 分钟。

### 5. 访问网站

部署完成后，网站地址为 `https://<用户名>.github.io/<仓库名>/`，例如本项目：<https://infinity4b.github.io/daily-arxiv-vla/>。

## 自定义配置

### 修改网站标题

网站标题为「<关键词标签> 每日论文卡」。使用默认检索语句时，关键词标签取 `scripts/build_site.py` 中的 `DEFAULT_ARXIV_KEYWORD_LABEL`（当前为 `VLA / World Action Model`）；设置了自定义的 `ARXIV_QUERY_KEYWORD` 时，标签直接显示检索语句本身。如需修改，编辑 `DEFAULT_ARXIV_KEYWORD_LABEL` 或 `get_arxiv_keyword_label()`。

### 修改样式

页面样式由 `scripts/build_site.py` 生成，并合并 `scripts/modern_ui.css` 中的样式。

## 项目结构

```
daily-arxiv-vla/
├── papers.md                              # 论文数据源（Markdown 表格）
├── requirements.txt                       # Python 依赖
├── package.json                           # Playwright 依赖与截图脚本
├── scripts/
│   ├── arxiv_crawler.py                   # arXiv 爬虫
│   ├── generate_summaries.py              # AI 摘要生成
│   ├── fetch_paper_images.py              # 从论文 HTML 提取首图
│   ├── build_paper_image_fallback_queue.py  # 生成截图兜底队列（tmp/）
│   ├── render_paper_image_fallbacks.mjs   # Playwright 截图兜底
│   ├── register_paper_image_fallbacks.py  # 把截图结果写入首图 manifest
│   ├── build_site.py                      # 网站构建
│   ├── modern_ui.css                      # 附加样式
│   ├── clean_summaries.py                 # 规范化摘要
│   └── clear_summaries.py                 # 重置全部摘要
├── site/                                  # 生成的静态网站（由工作流提交进仓库）
│   ├── index.html
│   ├── papers/<arxiv-id>/index.html       # 论文详情页
│   ├── covers/<arxiv-id>/index.html       # 论文封面卡
│   └── assets/
│       ├── paper-images/                  # 全尺寸首图（WebP）
│       │   └── thumbs/                    # 缩略图
│       ├── paper-images.json              # 首图 manifest
│       ├── data.json                      # 首页数据
│       ├── app.js / paper.js / media.js / theme.js / analytics.js
│       └── style.css
└── .github/workflows/deploy.yml           # 爬取、构建与部署工作流
```

## 数据格式

`papers.md` 是一个 Markdown 表格，每行一篇论文：

```markdown
| 日期 | 标题 | 链接 | 简要总结 |
| --- | --- | --- | --- |
| 2026-11-05 | 论文标题 | http://arxiv.org/abs/2611.08462 | <details><summary>展开</summary>## 研究单位<br>- ...</details> |
```

- 新爬取的论文，摘要列为 `<details><summary>展开</summary>待生成</details>`，`generate_summaries.py` 只处理含「待生成」的行。
- 摘要内容是 Markdown，换行用 `<br>` 表示。

## 技术栈

- **语言**：Python 3.9+，Node.js（仅截图兜底）
- **爬虫**：[arxiv](https://pypi.org/project/arxiv/) Python 库
- **AI 摘要**：ModelScope API（OpenAI 兼容接口）
- **图片处理**：Pillow（WebP 转换与缩略图）、Playwright（截图兜底）
- **前端**：原生 HTML / CSS / JavaScript，字体 Manrope + Noto Sans SC（Google Fonts）
- **部署**：GitHub Actions + GitHub Pages
