#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
生成静态站点：
1) 解析项目根目录下的 `papers.md` 表格（列：日期/标题/链接/简要总结）。
2) 从第四列提取 <details> ... </details> 中的实际内容。
3) 对内容进行“自动补换行”修复（因原始换行丢失）。
4) 将修复后的 Markdown 渲染为 HTML（无第三方依赖，内置简易渲染器）。
5) 输出站点到 `site/`：index.html、assets/style.css、assets/app.js、assets/data.json。
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_MD = PROJECT_ROOT / "papers.md"
SITE_DIR = PROJECT_ROOT / "site"
ASSETS_DIR = SITE_DIR / "assets"


def read_text(path: Path) -> str:
    with path.open("r", encoding="utf-8") as f:
        return f.read()


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write(content)


def parse_markdown_table(md_text: str) -> List[Dict[str, str]]:
    """
    解析 markdown 表格为记录列表。
    预期表头：| 日期 | 标题 | 链接 | 简要总结 |
    """
    lines = [line for line in md_text.splitlines() if line.strip()]
    if len(lines) < 3:
        return []

    records: List[Dict[str, str]] = []
    # 跳过表头两行
    for line in lines[2:]:
        if not line.strip().startswith("|"):
            continue
        # 朴素分割，并去除首尾竖线
        parts = [p.strip() for p in line.strip().strip("|").split("|")]
        if len(parts) < 4:
            continue
        date_str, title, link, summary_cell = parts[0], parts[1], parts[2], "|".join(parts[3:]).strip()

        # 提取 <details> 内容
        details_content = extract_details(summary_cell)
        records.append({
            "date": date_str,
            "title": title,
            "link": link,
            "details_raw": details_content,
        })
    return records


def extract_details(cell_html: str) -> str:
    """
    从单元格中提取 <details> 内容，去除 <summary>...
    """
    # 去壳
    m = re.search(r"<details>([\s\S]*?)</details>", cell_html, re.IGNORECASE)
    content = m.group(1) if m else cell_html
    # 去掉 <summary>...</summary>
    content = re.sub(r"<summary>[\s\S]*?</summary>", "", content, flags=re.IGNORECASE)
    # 将 <br> 标签转换回换行符，以便 Markdown 渲染器正确处理
    content = content.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    # 去掉包裹空白
    return content.strip()


def auto_add_linebreaks(text: str) -> str:
    """
    自动添加换行符的启发式规则（仅在换行已丢失时使用）：
    - 标题前换行：在 "#" 等子标题前插入换行（如果紧跟在其他内容后）
    - 项目符号：将内嵌的 " - "/" – " 转为行首列表项
    - 有序列表："1. ", "2. " 等编号若非行首，则前置换行
    - 水平分割线：在 --- 周围添加换行
    - 粗体小节：将 " - **小节**" 等模式置于新行
    
    注意：如果文本中已经包含换行符（从 <br> 转换而来），则跳过大部分启发式规则
    """
    t = text
    
    # 如果文本中已经有换行符，说明换行信息已保留，只需做轻微规范化
    has_linebreaks = "\n" in t
    
    if has_linebreaks:
        # 已有换行，只需规范化
        # 确保标题前有换行（如果紧跟在其他非空白内容后）
        # 使用负向前瞻确保不会拆分行首的标题
        # 匹配：非换行、非#的字符，后面跟着 #（且不在行首）
        t = re.sub(r"([^\n\s#])\s*(?=#+\s)", r"\1\n", t)
        # 确保水平线前后有换行
        t = re.sub(r"([^\n])\s*---\s*([^\n])", r"\1\n---\n\2", t)
        # 合并多余空行为最多两个
        t = re.sub(r"\n{3,}", "\n\n", t)
    else:
        # 没有换行，使用完整的启发式规则恢复
        # 标题前强制换行（但不要拆分行首的标题）
        # 只在非行首的 # 前添加换行
        t = re.sub(r"([^\n\s#])\s*(?=#+\s)", r"\1\n", t)
        # 如果文本开头没有换行，确保标题在行首
        if not t.startswith("#"):
            t = re.sub(r"^\s*(#+\s+)", r"\1", t)

        # 水平线周围换行
        t = re.sub(r"\s*---\s*", "\n---\n", t)

        # 列表项前换行（无序）
        t = re.sub(r"\s+[-–]\s+", "\n- ", t)

        # 有序列表：将内联的 " 1. " 变为换行起始
        # 但不要匹配在 **粗体** 内部的数字（如 **1. 标题**）
        t = re.sub(r"(?<!\n)(?<!\*\*)(\s*)(\d+\.\s+)", lambda m: "\n" + m.group(2), t)

        # 粗体小节项：" - **...**" → 换行
        t = re.sub(r"\s+-\s+\*\*(.+?)\*\*", lambda m: "\n- **" + m.group(1) + "**", t)

        # 在中文句号+标题锚点之间分段（谨慎）
        t = re.sub(r"([。！？；])\s*(#+\s+)", r"\1\n\2", t)

        # 合并多余空行为最多两个
        t = re.sub(r"\n{3,}", "\n\n", t)

    return t.strip()


def markdown_to_html(md: str) -> str:
    """
    改进的 Markdown 渲染器，支持：
    - 所有级别标题 (#, ##, ###, ####)
    - 无序列表和有序列表（支持多行）
    - 行内格式：**粗体**、`代码`、[链接](url)
    - 段落和换行
    """
    lines = md.splitlines()
    html_lines: List[str] = []

    def render_inline(s: str) -> str:
        # 代码块
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        # 粗体
        s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
        # 链接
        s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"<a href=\"\2\" target=\"_blank\" rel=\"noopener noreferrer\">\1</a>", s)
        return s

    i = 0
    while i < len(lines):
        line = lines[i].rstrip()

        if not line:
            html_lines.append("")
            i += 1
            continue

        # 标题 - 支持所有级别（#, ##, ###, ####）
        title_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if title_match:
            level = len(title_match.group(1))
            # 限制最大级别为 h4
            level = min(level, 4)
            # h2 添加特殊类名用于样式
            title_text = title_match.group(2).strip()
            class_attr = ' class="section-title"' if level == 2 else ''
            html_lines.append(f"<h{level}{class_attr}>{render_inline(title_text)}</h{level}>")
            i += 1
            continue

        # 水平线
        if line.strip() == "---":
            html_lines.append("<hr/>")
            i += 1
            continue

        # 无序列表
        if re.match(r"^[-*]\s+", line):
            ul_items: List[str] = []
            while i < len(lines):
                curr_line = lines[i].rstrip()
                if not curr_line:
                    break
                if re.match(r"^[-*]\s+", curr_line):
                    item_text = re.sub(r"^[-*]\s+", "", curr_line).strip()
                    ul_items.append(f"<li>{render_inline(item_text)}</li>")
                    i += 1
                else:
                    break
            if ul_items:
                html_lines.append("<ul>" + "".join(ul_items) + "</ul>")
            continue

        # 有序列表
        if re.match(r"^\d+\.\s+", line):
            ol_items: List[str] = []
            while i < len(lines):
                curr_line = lines[i].rstrip()
                if not curr_line:
                    break
                if re.match(r"^\d+\.\s+", curr_line):
                    item_text = re.sub(r"^\d+\.\s+", "", curr_line).strip()
                    ol_items.append(f"<li>{render_inline(item_text)}</li>")
                    i += 1
                else:
                    break
            if ol_items:
                html_lines.append("<ol>" + "".join(ol_items) + "</ol>")
            continue

        # 普通段落
        html_lines.append(f"<p>{render_inline(line)}</p>")
        i += 1

    # 合并相邻空行
    out: List[str] = []
    prev_blank = False
    for h in html_lines:
        is_blank = (h == "")
        if is_blank and prev_blank:
            continue
        out.append(h)
        prev_blank = is_blank

    return "\n".join(out).strip()


def build_data(records: List[Dict[str, str]]) -> List[Dict[str, str]]:
    data: List[Dict[str, str]] = []
    for rec in records:
        raw = rec["details_raw"]
        fixed = auto_add_linebreaks(raw)
        html = markdown_to_html(fixed)
        data.append({
            "date": rec["date"],
            "title": rec["title"],
            "link": rec["link"],
            "summary_markdown": fixed,
            "summary_html": html,
        })
    return data


def generate_index_html() -> str:
    # 从环境变量读取关键词，生成动态标题
    keyword = os.getenv("ARXIV_QUERY_KEYWORD", "VLA")
    site_title = f"{keyword} 论文精选"
    site_subtitle = f"精选 {keyword} 相关的最新 arXiv 论文"

    return f"""<!doctype html>
<html lang=\"zh-CN\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>{site_title} - ArXiv Papers</title>
    <meta name=\"description\" content=\"{site_subtitle}\" />
    <link rel=\"preconnect\" href=\"https://fonts.googleapis.com\" />
    <link rel=\"preconnect\" href=\"https://fonts.gstatic.com\" crossorigin />
    <link href=\"https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap\" rel=\"stylesheet\" />
    <link rel=\"stylesheet\" href=\"assets/style.css\" />
  </head>
  <body>
    <div class=\"bg-gradient\"></div>
    <header class=\"header\">
      <div class=\"container\">
        <div class=\"header-content\">
          <div class=\"header-text\">
            <h1 class=\"site-title\">
              <span class=\"icon\">📚</span>
              {site_title}
            </h1>
            <p class=\"site-subtitle\">{site_subtitle}</p>
          </div>
          <div class=\"search-wrapper\">
            <svg class=\"search-icon\" width=\"20\" height=\"20\" viewBox=\"0 0 20 20\" fill=\"none\">
              <path d=\"M9 17A8 8 0 1 0 9 1a8 8 0 0 0 0 16zM18 18l-4-4\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/>
            </svg>
            <input id=\"search\" type=\"search\" placeholder=\"搜索论文标题或内容...\" aria-label=\"搜索\" />
          </div>
        </div>
      </div>
    </header>

    <main class=\"container main-content\">
      <section id=\"groups\"></section>
    </main>

    <footer class=\"footer\">
      <div class=\"container\">
        <p>数据来源：<a href=\"https://arxiv.org\" target=\"_blank\" rel=\"noopener noreferrer\">arXiv.org</a></p>
      </div>
    </footer>

    <div id=\"detail-view\" class=\"detail-view hidden\">
      <div class=\"detail-header\">
        <button id=\"detail-back\" class=\"back-btn\" aria-label=\"返回\">
          <svg width=\"20\" height=\"20\" viewBox=\"0 0 20 20\" fill=\"none\">
            <path d=\"M15 10H5M5 10l5 5M5 10l5-5\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/>
          </svg>
          返回
        </button>
      </div>
      <div class=\"detail-content\">
        <h2 id=\"detail-title\"></h2>
        <div id=\"detail-meta\" class=\"detail-meta\"></div>
        <article id=\"detail-body\"></article>
      </div>
    </div>

    <script src=\"assets/app.js\"></script>
  </body>
</html>
""".strip()


def generate_style_css() -> str:
    return """
:root {
  --bg: #0a0e1a;
  --bg-secondary: #0f1419;
  --card: #161b26;
  --card-hover: #1a2030;
  --text: #e8eaed;
  --text-secondary: #9ca3af;
  --border: #1f2937;
  --accent: #6366f1;
  --accent-hover: #4f46e5;
  --gradient-from: #6366f1;
  --gradient-to: #8b5cf6;
  --shadow: rgba(0, 0, 0, 0.3);
}

* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

html, body {
  background: var(--bg);
  color: var(--text);
  font-family: Inter, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
  line-height: 1.6;
  overflow-x: hidden;
}

.bg-gradient {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 400px;
  background: radial-gradient(ellipse at top, rgba(99, 102, 241, 0.15), transparent 60%);
  pointer-events: none;
  z-index: 0;
}

.container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 24px;
}

.header {
  position: relative;
  padding: 48px 0 32px;
  z-index: 1;
}

.header-content {
  display: flex;
  flex-direction: column;
  gap: 32px;
}

.header-text {
  text-align: center;
}

.site-title {
  font-size: 48px;
  font-weight: 700;
  background: linear-gradient(135deg, var(--gradient-from), var(--gradient-to));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
}

.site-title .icon {
  font-size: 42px;
  filter: drop-shadow(0 4px 12px rgba(99, 102, 241, 0.4));
}

.site-subtitle {
  font-size: 18px;
  color: var(--text-secondary);
  font-weight: 400;
}

.search-wrapper {
  position: relative;
  max-width: 600px;
  margin: 0 auto;
  width: 100%;
}

.search-icon {
  position: absolute;
  left: 16px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-secondary);
  pointer-events: none;
}

input[type=search] {
  width: 100%;
  padding: 14px 16px 14px 48px;
  border-radius: 12px;
  border: 2px solid var(--border);
  background: var(--bg-secondary);
  color: var(--text);
  font-size: 16px;
  outline: none;
  transition: all 0.3s ease;
}

input[type=search]:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.1);
}

input[type=search]::placeholder {
  color: var(--text-secondary);
}

.main-content {
  position: relative;
  z-index: 1;
  padding-bottom: 80px;
}

.group {
  margin: 48px 0;
}

.group h2 {
  font-size: 20px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 20px;
  padding-bottom: 12px;
  border-bottom: 2px solid var(--border);
  display: flex;
  align-items: center;
  gap: 8px;
}

.group h2::before {
  content: '📅';
  font-size: 18px;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 24px;
}

.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  transition: all 0.3s ease;
  cursor: pointer;
  position: relative;
  overflow: hidden;
}

.card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg, var(--gradient-from), var(--gradient-to));
  opacity: 0;
  transition: opacity 0.3s ease;
}

.card:hover {
  background: var(--card-hover);
  border-color: var(--accent);
  transform: translateY(-4px);
  box-shadow: 0 12px 24px var(--shadow);
}

.card:hover::before {
  opacity: 1;
}

.title {
  font-weight: 600;
  font-size: 16px;
  line-height: 1.5;
  color: var(--text);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.btn-row {
  display: flex;
  gap: 12px;
  margin-top: auto;
}

.btn {
  appearance: none;
  border: 1px solid var(--border);
  background: var(--bg-secondary);
  color: var(--text);
  padding: 10px 16px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.2s ease;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.btn:hover {
  border-color: var(--accent);
  background: var(--card-hover);
}

.btn.primary {
  background: linear-gradient(135deg, var(--gradient-from), var(--gradient-to));
  border-color: var(--accent);
  color: white;
  font-weight: 600;
}

.btn.primary:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 16px rgba(99, 102, 241, 0.3);
}

.footer {
  position: relative;
  z-index: 1;
  padding: 32px 0;
  border-top: 1px solid var(--border);
  text-align: center;
  color: var(--text-secondary);
  font-size: 14px;
}

.footer a {
  color: var(--accent);
  text-decoration: none;
  transition: color 0.2s ease;
}

.footer a:hover {
  color: var(--accent-hover);
}

.detail-view {
  position: fixed;
  inset: 0;
  background: var(--bg);
  z-index: 1000;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
}

.detail-view.hidden {
  display: none;
}

.detail-header {
  position: sticky;
  top: 0;
  border-bottom: 1px solid var(--border);
  padding: 16px 24px;
  z-index: 10;
  backdrop-filter: blur(12px);
  background: rgba(10, 14, 26, 0.95);
}

.back-btn {
  appearance: none;
  background: var(--card);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 10px 20px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 15px;
  font-weight: 500;
  transition: all 0.2s ease;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.back-btn:hover {
  border-color: var(--accent);
  background: var(--card-hover);
}

.back-btn svg {
  width: 20px;
  height: 20px;
}

.detail-content {
  flex: 1;
  max-width: 900px;
  width: 100%;
  margin: 0 auto;
  padding: 40px 24px 80px;
}

#detail-title {
  font-size: 32px;
  font-weight: 700;
  line-height: 1.3;
  margin-bottom: 16px;
  color: var(--text);
}

.detail-meta {
  color: var(--text-secondary);
  font-size: 15px;
  margin-bottom: 32px;
  padding-bottom: 24px;
  border-bottom: 1px solid var(--border);
}

.detail-meta a {
  color: var(--accent);
  text-decoration: none;
  transition: color 0.2s ease;
}

.detail-meta a:hover {
  color: var(--accent-hover);
}

article h2 {
  font-size: 22px;
  font-weight: 700;
  margin: 40px 0 20px;
  color: var(--text);
  padding-bottom: 12px;
  border-bottom: 2px solid var(--border);
  position: relative;
}

article h2.section-title::before {
  content: '';
  position: absolute;
  bottom: -2px;
  left: 0;
  width: 60px;
  height: 2px;
  background: linear-gradient(90deg, var(--gradient-from), var(--gradient-to));
}

article h3, article h4 {
  margin: 32px 0 16px;
  color: var(--text);
  font-weight: 600;
}

article h3 {
  font-size: 20px;
}

article h4 {
  font-size: 18px;
}

article p {
  margin: 16px 0;
  line-height: 1.8;
  color: var(--text-secondary);
}

article ul, article ol {
  margin: 16px 0;
  padding-left: 28px;
  line-height: 1.8;
}

article li {
  margin: 10px 0;
  color: var(--text-secondary);
}

article ul li {
  list-style-type: disc;
}

article ol li {
  list-style-type: decimal;
}

article li::marker {
  color: var(--accent);
  font-weight: 600;
}

article strong {
  color: var(--text);
  font-weight: 600;
}

article code {
  background: var(--card);
  border: 1px solid var(--border);
  padding: 3px 8px;
  border-radius: 6px;
  font-size: 14px;
  font-family: 'Courier New', monospace;
  color: var(--accent);
}

article a {
  color: var(--accent);
  text-decoration: none;
  transition: color 0.2s ease;
}

article a:hover {
  color: var(--accent-hover);
  text-decoration: underline;
}

hr {
  border: none;
  border-top: 1px solid var(--border);
  margin: 32px 0;
}

@media (max-width: 768px) {
  .site-title {
    font-size: 32px;
  }

  .site-title .icon {
    font-size: 28px;
  }

  .site-subtitle {
    font-size: 16px;
  }

  .header {
    padding: 32px 0 24px;
  }

  .grid {
    grid-template-columns: 1fr;
  }

  #detail-title {
    font-size: 24px;
  }

  .detail-content {
    padding: 24px 16px 60px;
  }
}
""".strip()


def generate_app_js() -> str:
    return f"""
/**
 * @file app.js
 * @description 前端逻辑：加载 data.json，渲染卡片、搜索、日期筛选、详情弹窗。
 */
(function(){{
  /** @type {{Array<{{date:string,title:string,link:string,summary_markdown:string,summary_html:string}}>}} */
  let DATA = [];

  const $ = (sel) => document.querySelector(sel);
  const groupsEl = $('#groups');
  const searchEl = $('#search');
  const detailView = $('#detail-view');
  const detailTitle = $('#detail-title');
  const detailMeta = $('#detail-meta');
  const detailBody = $('#detail-body');
  const detailBack = $('#detail-back');
  let currentItem = null;
  let lastScrollY = 0;

  /**
   * @param {{Array}} items
   * @param {{string}} q
   * @param {{string|null}} date
   */
  function filterItems(items, q){{
    const kw = (q||'').trim().toLowerCase();
    return items.filter(it => {{
      if(!kw) return true;
      const hay = (it.title + ' ' + it.summary_markdown).toLowerCase();
      return hay.includes(kw);
    }});
  }}

  /**
   * @param {{Array}} items  已过滤后的项目
   */
  function renderGroups(items){{
    // 分组：按日期降序
    const map = new Map();
    items.forEach(it=>{{ if(!map.has(it.date)) map.set(it.date, []); map.get(it.date).push(it); }});
    const dates = Array.from(map.keys()).sort((a,b)=> b.localeCompare(a));

    groupsEl.innerHTML = '';
    dates.forEach(d => {{
      const group = document.createElement('section');
      group.className = 'group';
      const h = document.createElement('h2');
      h.textContent = d;
      const grid = document.createElement('div');
      grid.className = 'grid';
      map.get(d).forEach(it => {{
        const card = document.createElement('div');
        card.className = 'card';
        const title = document.createElement('div');
        title.className = 'title';
        title.textContent = it.title;
        const btnRow = document.createElement('div');
        btnRow.className = 'btn-row';
        const viewBtn = document.createElement('a');
        viewBtn.className = 'btn';
        viewBtn.href = it.link; viewBtn.target = '_blank'; viewBtn.rel = 'noopener noreferrer';
        viewBtn.textContent = '查看原文';
        const detailBtn = document.createElement('button');
        detailBtn.className = 'btn primary';
        detailBtn.textContent = '详情';
        detailBtn.onclick = ()=> openDetail(it);
        btnRow.appendChild(viewBtn);
        btnRow.appendChild(detailBtn);
        card.appendChild(title);
        card.appendChild(btnRow);
        grid.appendChild(card);
      }});
      group.appendChild(h);
      group.appendChild(grid);
      groupsEl.appendChild(group);
    }});
  }}

  /**
   * 从 arxiv.org 链接中提取论文 ID，并生成幻觉翻译链接
   * @param {{string}} link
   * @returns {{string|null}} 幻觉翻译链接，如果不是 arxiv 链接则返回 null
   */
  function getTranslationLink(link){{
    // 匹配 arxiv.org/abs/ 或 arxiv.org/pdf/ 等格式
    const match = link.match(/arxiv\\.org\\/(?:abs|pdf)\\/([\\d.]+)/i);
    if(match && match[1]){{
      return `https://hjfy.top/arxiv/${{match[1]}}`;
    }}
    return null;
  }}

  /**
   * @param {{title:string,date:string,summary_html:string,link:string}} it
   */
  function openDetail(it){{
    lastScrollY = window.scrollY || 0;
    currentItem = it;
    detailTitle.textContent = it.title;
    const translationLink = getTranslationLink(it.link);
    let metaHtml = `${{it.date}} · <a href="${{it.link}}" target="_blank" rel="noopener noreferrer">原文链接</a>`;
    if(translationLink){{
      metaHtml += ` · <a href="${{translationLink}}" target="_blank" rel="noopener noreferrer">幻觉翻译</a>`;
    }}
    detailMeta.innerHTML = metaHtml;
    detailBody.innerHTML = it.summary_html; // 已在后端修复换行并渲染
    detailView.classList.remove('hidden');
    // 使用 pushState 添加历史记录，但不改变 URL
    history.pushState({{ view: 'detail', item: it }}, '', window.location.href);
    // 滚动到顶部
    window.scrollTo(0, 0);
  }}

  function closeDetail(){{ 
    detailView.classList.add('hidden');
    currentItem = null;
    requestAnimationFrame(() => window.scrollTo(0, lastScrollY));
    // 如果当前在详情页面状态，替换为列表状态（不跳转）
    if (history.state && history.state.view === 'detail') {{
      history.replaceState({{ view: 'list' }}, '', window.location.href);
    }}
  }}

  function sync(){{
    const items = filterItems(DATA, searchEl.value);
    renderGroups(items);
  }}

  detailBack.addEventListener('click', closeDetail);
  
  // 监听浏览器前进/后退事件
  window.addEventListener('popstate', (e) => {{
    if (e.state && e.state.view === 'detail' && e.state.item) {{
      // 前进到详情页面（不添加新的历史记录）
      currentItem = e.state.item;
      detailTitle.textContent = e.state.item.title;
      const translationLink = getTranslationLink(e.state.item.link);
      let metaHtml = `${{e.state.item.date}} · <a href="${{e.state.item.link}}" target="_blank" rel="noopener noreferrer">原文链接</a>`;
      if(translationLink){{
        metaHtml += ` · <a href="${{translationLink}}" target="_blank" rel="noopener noreferrer">幻觉翻译</a>`;
      }}
      detailMeta.innerHTML = metaHtml;
      detailBody.innerHTML = e.state.item.summary_html;
      detailView.classList.remove('hidden');
      window.scrollTo(0, 0);
    }} else {{
      // 返回到列表页面（包括 view 为 'list' 或 null 的情况）
      detailView.classList.add('hidden');
      currentItem = null;
      requestAnimationFrame(() => window.scrollTo(0, lastScrollY));
    }}
  }});

  searchEl.addEventListener('input', sync);

  fetch('assets/data.json').then(r=>r.json()).then(arr=>{{ DATA = arr; sync(); }});
}})();
""".strip()


def main() -> int:
    if not INPUT_MD.exists():
        print(f"未找到 {INPUT_MD}", file=sys.stderr)
        return 1

    md_text = read_text(INPUT_MD)
    records = parse_markdown_table(md_text)
    data = build_data(records)

    # 输出静态资源
    write_text(SITE_DIR / "index.html", generate_index_html())
    write_text(ASSETS_DIR / "style.css", generate_style_css())
    write_text(ASSETS_DIR / "app.js", generate_app_js())
    write_text(ASSETS_DIR / "data.json", json.dumps(data, ensure_ascii=False, indent=2))

    print(f"生成完成：{SITE_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())


