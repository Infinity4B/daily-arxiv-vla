# ArXiv Papers 网站

这是一个展示ArXiv论文精选的静态网站，支持搜索和详情查看功能。

## 功能特性

- 📚 从 `papers.md` 自动解析论文信息
- 🔍 实时搜索功能
- 📱 响应式设计，支持移动端
- 🎨 现代化暗色主题界面
- 📄 论文详情弹窗展示

## 本地开发

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

### 2. 自动部署

每次推送到 `master` 或 `main` 分支时，GitHub Actions 会自动：

1. 检出代码
2. 运行构建脚本
3. 部署到 GitHub Pages

### 3. 访问网站

部署完成后，你的网站将在以下地址可访问：
```
https://你的用户名.github.io/仓库名/vla
```

例如：`https://username.github.io/arxiv/vla`

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
├── papers.md              # 论文数据源文件
├── scripts/
│   └── build_site.py      # 构建脚本
├── site/                  # 生成的静态网站
│   ├── index.html
│   └── assets/
│       ├── style.css
│       ├── app.js
│       └── data.json
└── .github/
    └── workflows/
        └── deploy.yml     # GitHub Actions 部署配置
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
- **前端**: 原生 HTML/CSS/JavaScript
- **部署**: GitHub Pages + GitHub Actions
- **字体**: Google Fonts (Inter)
