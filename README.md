# ArXiv Papers 网站

这是一个展示ArXiv论文精选的静态网站，支持搜索和详情查看功能。项目会自动爬取包含"VLA"关键词的论文，并使用AI生成摘要。

## 功能特性

- 🤖 **自动爬取**: 每日自动从ArXiv爬取包含"VLA"关键词的最新论文
- 🧠 **AI摘要生成**: 使用ModelScope API自动为论文生成中文摘要
- 📚 从 `papers.md` 自动解析论文信息
- 🔍 实时搜索功能
- 📱 响应式设计，支持移动端
- 🎨 现代化暗色主题界面
- 📄 论文详情弹窗展示
- ⏰ **定时任务**: 每日中午12点自动更新内容

## 本地开发

### 环境配置

首先需要配置ModelScope API密钥：

```bash
# 创建.env文件
echo "MODELSCOPE_ACCESS_TOKEN=你的API密钥" > .env
```

### 爬取论文数据

```bash
# 初始化爬取（首次运行）
python scripts/arxiv_crawler.py

# 生成论文摘要
python scripts/generate_summaries.py
```

### 构建网站

```bash
python scripts/build_site.py
```

这将在 `site/` 目录下生成静态网站文件。

### 本地预览

可以使用任何静态文件服务器预览网站：

```bash
# 使用Python内置服务器
cd site
python -m http.server 8000

# 或使用Node.js serve
npx serve site
```

## GitHub Pages 部署

### 1. 配置仓库

1. 确保你的仓库是公开的
2. 在仓库设置中启用 GitHub Pages
3. 选择 "GitHub Actions" 作为部署源

### 2. 配置环境变量

在仓库设置中添加以下Secret：
- `MODELSCOPE_ACCESS_TOKEN`: 你的ModelScope API密钥

### 3. 自动部署

每次推送到 `master` 或 `main` 分支时，GitHub Actions 会自动：

1. 检出代码
2. 运行构建脚本
3. 部署到 GitHub Pages

### 4. 定时任务

GitHub Actions 还会在每日中午12点自动执行：

1. 爬取ArXiv上的新论文
2. 为待生成的论文生成AI摘要
3. 提交更改到仓库
4. 重新构建和部署网站

### 5. 访问网站

部署完成后，你的网站将在以下地址可访问：
```
https://你的用户名.github.io/仓库名
```

例如：`https://username.github.io/arxiv`

## 自定义配置

### 修改子路径

如果你想修改网站的访问路径，编辑 `scripts/build_site.py` 中的 `BASE_PATH` 变量：

```python
BASE_PATH = "/你的路径"  # 例如 "/my-papers"
```

### 修改网站标题

编辑 `scripts/build_site.py` 中的 `generate_index_html()` 函数来修改网站标题。

## 项目结构

```
arxiv/
├── papers.md                    # 论文数据源文件
├── scripts/
│   ├── arxiv_crawler.py         # ArXiv论文爬虫
│   ├── generate_summaries.py    # AI摘要生成脚本
│   └── build_site.py            # 网站构建脚本
├── site/                        # 生成的静态网站
│   ├── index.html
│   └── assets/
│       ├── style.css
│       ├── app.js
│       └── data.json
└── .github/
    └── workflows/
        └── deploy.yml           # GitHub Actions 部署配置
```

## 数据格式

`papers.md` 文件应包含以下格式的表格：

```markdown
| 日期 | 标题 | 链接 | 简要总结 |
|------|------|------|----------|
| 2024-01-01 | 论文标题 | https://arxiv.org/abs/xxx | <details><summary>点击查看</summary>详细内容...</details> |
```

## 技术栈

- **后端**: Python 3.9+
- **爬虫**: arxiv Python库
- **AI摘要**: ModelScope API (DeepSeek-R1模型)
- **前端**: 原生 HTML/CSS/JavaScript
- **部署**: GitHub Pages + GitHub Actions
- **定时任务**: GitHub Actions Cron
- **字体**: Google Fonts (Inter)
