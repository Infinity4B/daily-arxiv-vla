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
      <section id=\"status\" class=\"status-panel hidden\" aria-live=\"polite\"></section>
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
        <div class=\"detail-shell\">
          <div class=\"detail-main\">
            <h2 id=\"detail-title\"></h2>
            <div id=\"detail-meta\" class=\"detail-meta\"></div>
            <article id=\"detail-body\"></article>
          </div>
          <aside id=\"detail-toc\" class=\"detail-toc hidden\" aria-label=\"内容目录\">
            <p class=\"detail-toc-title\">内容目录</p>
            <nav id=\"detail-toc-nav\" class=\"detail-toc-nav\"></nav>
          </aside>
        </div>
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

body.detail-open {
  overflow: hidden;
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

.status-panel.hidden {
  display: none;
}

.status-card {
  background: rgba(15, 20, 25, 0.82);
  border: 1px solid var(--border);
  border-radius: 24px;
  padding: 24px 28px;
  margin-bottom: 28px;
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.22);
}

.status-card[data-state="loading"] {
  border-color: rgba(99, 102, 241, 0.35);
}

.status-card[data-state="error"] {
  border-color: rgba(248, 113, 113, 0.45);
}

.status-card[data-state="empty"] {
  border-color: rgba(148, 163, 184, 0.32);
}

.status-title {
  font-size: 18px;
  font-weight: 600;
  margin-bottom: 8px;
}

.status-text {
  color: var(--text-secondary);
  line-height: 1.7;
}

.status-action {
  margin-top: 16px;
  appearance: none;
  border: 1px solid var(--border);
  background: var(--card);
  color: var(--text);
  border-radius: 999px;
  padding: 10px 16px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.status-action:hover,
.status-action:focus-visible {
  border-color: var(--accent);
  background: var(--card-hover);
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
  appearance: none;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 24px;
  padding: 32px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
  cursor: pointer;
  position: relative;
  overflow: hidden;
  min-height: 220px;
  width: 100%;
  text-align: left;
  font: inherit;
}

.card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 5px;
  background: linear-gradient(90deg, var(--gradient-from), var(--gradient-to));
  opacity: 0;
  transition: opacity 0.4s ease;
  border-radius: 24px 24px 0 0;
}

.card:hover {
  background: var(--card-hover);
  border-color: var(--accent);
  transform: translateY(-8px) scale(1.02);
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4), 0 0 0 1px rgba(99, 102, 241, 0.3);
}

.card:hover::before {
  opacity: 1;
}

.card:active {
  transform: translateY(-4px) scale(1.01);
}

.card:focus-visible,
.back-btn:focus-visible,
.detail-toc-link:focus-visible,
input[type=search]:focus-visible,
.status-action:focus-visible {
  outline: none;
  box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.16);
}

.group-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.group-count {
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 500;
}

.title {
  font-weight: 600;
  font-size: 18px;
  line-height: 1.5;
  color: var(--text);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  margin-bottom: 8px;
}

.card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.card-tag {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.03);
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.4;
}

.card-tag.primary {
  color: var(--text);
  border-color: rgba(99, 102, 241, 0.28);
  background: rgba(99, 102, 241, 0.1);
}

.summary-preview {
  font-size: 14px;
  line-height: 1.7;
  color: var(--text-secondary);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  opacity: 0.8;
  flex: 1;
}

.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: auto;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}

.read-more {
  font-size: 14px;
  color: var(--accent);
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: gap 0.3s ease;
}

.card:hover .read-more {
  gap: 10px;
}

.read-more::after {
  content: '→';
  font-size: 16px;
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
  max-width: 1180px;
  width: 100%;
  margin: 0 auto;
  padding: 40px 24px 80px;
}

.detail-shell {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 240px;
  gap: 40px;
  align-items: start;
}

.detail-main {
  min-width: 0;
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

.detail-toc {
  position: sticky;
  top: 92px;
  background: rgba(15, 20, 25, 0.82);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 18px;
}

.detail-toc.hidden {
  display: none;
}

.detail-toc-title {
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-secondary);
  margin-bottom: 14px;
}

.detail-toc-nav {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.detail-toc-link {
  color: var(--text-secondary);
  text-decoration: none;
  font-size: 14px;
  line-height: 1.5;
  transition: color 0.2s ease, transform 0.2s ease;
}

.detail-toc-link:hover {
  color: var(--text);
  transform: translateX(2px);
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

  .status-card {
    padding: 20px;
  }

  .group-heading {
    align-items: flex-start;
    flex-direction: column;
  }

  .detail-shell {
    grid-template-columns: 1fr;
    gap: 20px;
  }

  .detail-toc {
    position: static;
    order: -1;
  }
}
""".strip()


def generate_app_js() -> str:
    return """
/**
 * @file app.js
 * @description 前端逻辑：加载 data.json，渲染卡片、搜索、状态反馈、详情目录与键盘交互。
 */
(function(){
  /** @type {Array<{date:string,title:string,link:string,summary_markdown:string,summary_html:string}>} */
  let DATA = [];

  const $ = (sel) => document.querySelector(sel);
  const statusEl = $('#status');
  const groupsEl = $('#groups');
  const searchEl = $('#search');
  const detailView = $('#detail-view');
  const detailTitle = $('#detail-title');
  const detailMeta = $('#detail-meta');
  const detailBody = $('#detail-body');
  const detailToc = $('#detail-toc');
  const detailTocNav = $('#detail-toc-nav');
  const detailBack = $('#detail-back');
  let currentItem = null;
  let lastScrollY = 0;
  let lastFocusedCard = null;

  /**
   * @param {Array} items
   * @param {string} q
   */
  function filterItems(items, q){
    const kw = (q||'').trim().toLowerCase();
    return items.filter(it => {
      if(!kw) return true;
      const hay = (it.title + ' ' + it.summary_markdown).toLowerCase();
      return hay.includes(kw);
    });
  }

  function extractSectionBlock(markdown, title){
    const escaped = title.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&');
    const match = markdown.match(new RegExp(`##\\\\s*${escaped}[\\\\s\\\\S]*?(?=##|$)`));
    return match ? match[0] : '';
  }

  function extractResearchUnit(markdown){
    const block = extractSectionBlock(markdown, '研究单位');
    if(!block){
      return '';
    }

    const firstBullet = block
      .split('\\n')
      .map((line) => line.trim())
      .find((line) => line.startsWith('- '));

    if(!firstBullet){
      return '';
    }

    return firstBullet
      .replace(/^-\\s*/, '')
      .replace(/\\*\\*/g, '')
      .replace(/`/g, '')
      .replace(/作者主要来自/g, '')
      .replace(/作者来自/g, '')
      .trim();
  }

  function getArxivId(link){
    const match = link.match(/arxiv\\.org\\/(?:abs|pdf)\\/([^/?#]+)/i);
    return match ? match[1] : '';
  }

  function clearStatus(){
    statusEl.innerHTML = '';
    statusEl.classList.add('hidden');
  }

  function renderStatus(state, title, text, action){
    statusEl.classList.remove('hidden');
    statusEl.innerHTML = '';

    const card = document.createElement('div');
    card.className = 'status-card';
    card.dataset.state = state;

    const titleEl = document.createElement('div');
    titleEl.className = 'status-title';
    titleEl.textContent = title;

    const textEl = document.createElement('div');
    textEl.className = 'status-text';
    textEl.textContent = text;

    card.appendChild(titleEl);
    card.appendChild(textEl);

    if(action){
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'status-action';
      button.textContent = action.label;
      button.addEventListener('click', action.onClick);
      card.appendChild(button);
    }

    statusEl.appendChild(card);
  }

  /**
   * 提取论文概述部分作为预览
   * @param {string} markdown
   * @returns {string}
   */
  function extractOverview(markdown){
    // 尝试提取 "## 论文概述" 部分
    const overviewMatch = markdown.match(/##\\s*论文概述[\\s\\S]*?(?=##|$)/);
    if(overviewMatch){
      // 移除标题行和标记符号，只保留内容
      let content = overviewMatch[0]
        .replace(/##\\s*论文概述\\s*/, '')
        .replace(/#+\\s+/g, '')
        .replace(/\\*\\*/g, '')
        .replace(/`/g, '')
        .trim();
      return content.substring(0, 200);
    }
    // 回退：如果找不到论文概述，使用原有逻辑
    return markdown.replace(/#+\\s+/g, '').replace(/\\*\\*/g, '').substring(0, 200);
  }

  /**
   * @param {Array} items  已过滤后的项目
   */
  function renderGroups(items){
    if(!items.length){
      groupsEl.innerHTML = '';
      return;
    }

    const map = new Map();
    items.forEach(it=>{ if(!map.has(it.date)) map.set(it.date, []); map.get(it.date).push(it); });
    const dates = Array.from(map.keys()).sort((a,b)=> b.localeCompare(a));

    groupsEl.innerHTML = '';
    dates.forEach(d => {
      const group = document.createElement('section');
      group.className = 'group';

      const heading = document.createElement('div');
      heading.className = 'group-heading';

      const h = document.createElement('h2');
      h.textContent = d;

      const count = document.createElement('div');
      count.className = 'group-count';
      count.textContent = `${map.get(d).length} 篇`;

      const grid = document.createElement('div');
      grid.className = 'grid';

      map.get(d).forEach(it => {
        const card = document.createElement('button');
        card.type = 'button';
        card.className = 'card';
        card.setAttribute('aria-label', `查看论文：${it.title}`);
        card.addEventListener('click', ()=> openDetail(it, card));

        const title = document.createElement('div');
        title.className = 'title';
        title.textContent = it.title;

        const tags = document.createElement('div');
        tags.className = 'card-tags';

        const researchUnit = extractResearchUnit(it.summary_markdown);
        if(researchUnit){
          const orgTag = document.createElement('div');
          orgTag.className = 'card-tag primary';
          orgTag.textContent = researchUnit;
          tags.appendChild(orgTag);
        }

        const arxivId = getArxivId(it.link);
        if(arxivId){
          const idTag = document.createElement('div');
          idTag.className = 'card-tag';
          idTag.textContent = arxivId;
          tags.appendChild(idTag);
        }

        const preview = document.createElement('div');
        preview.className = 'summary-preview';
        preview.textContent = extractOverview(it.summary_markdown);

        const footer = document.createElement('div');
        footer.className = 'card-footer';
        const readMore = document.createElement('div');
        readMore.className = 'read-more';
        readMore.textContent = '阅读详情';

        footer.appendChild(readMore);
        if(tags.childNodes.length){
          card.appendChild(tags);
        }
        card.appendChild(title);
        card.appendChild(preview);
        card.appendChild(footer);
        grid.appendChild(card);
      });
      heading.appendChild(h);
      heading.appendChild(count);
      group.appendChild(heading);
      group.appendChild(grid);
      groupsEl.appendChild(group);
    });
  }

  /**
   * 从 arxiv.org 链接中提取论文 ID，并生成幻觉翻译链接
   * @param {string} link
   * @returns {string|null} 幻觉翻译链接，如果不是 arxiv 链接则返回 null
   */
  function getTranslationLink(link){
    // 匹配 arxiv.org/abs/ 或 arxiv.org/pdf/ 等格式
    const match = link.match(/arxiv\\.org\\/(?:abs|pdf)\\/([\\d.]+)/i);
    if(match && match[1]){
      return `https://hjfy.top/arxiv/${match[1]}`;
    }
    return null;
  }

  function renderDetailMeta(it){
    detailMeta.innerHTML = '';
    detailMeta.append(document.createTextNode(it.date));

    const sourceLink = document.createElement('a');
    sourceLink.href = it.link;
    sourceLink.target = '_blank';
    sourceLink.rel = 'noopener noreferrer';
    sourceLink.textContent = '原文链接';

    detailMeta.append(document.createTextNode(' · '));
    detailMeta.appendChild(sourceLink);

    const translationLink = getTranslationLink(it.link);
    if(translationLink){
      const translated = document.createElement('a');
      translated.href = translationLink;
      translated.target = '_blank';
      translated.rel = 'noopener noreferrer';
      translated.textContent = '幻觉翻译';
      detailMeta.append(document.createTextNode(' · '));
      detailMeta.appendChild(translated);
    }
  }

  function slugifyHeading(text, index){
    const slug = (text || '')
      .trim()
      .toLowerCase()
      .replace(/[^\\w\\u4e00-\\u9fff]+/g, '-')
      .replace(/^-+|-+$/g, '');
    return slug ? `section-${index}-${slug}` : `section-${index}`;
  }

  function buildDetailToc(){
    detailTocNav.innerHTML = '';
    const headings = Array.from(detailBody.querySelectorAll('h2'));

    if(!headings.length){
      detailToc.classList.add('hidden');
      return;
    }

    headings.forEach((heading, index) => {
      if(!heading.id){
        heading.id = slugifyHeading(heading.textContent, index + 1);
      }
      const link = document.createElement('a');
      link.className = 'detail-toc-link';
      link.href = `#${heading.id}`;
      link.textContent = heading.textContent || `章节 ${index + 1}`;
      link.addEventListener('click', (event) => {
        event.preventDefault();
        heading.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
      detailTocNav.appendChild(link);
    });

    detailToc.classList.remove('hidden');
  }

  function showDetail(it){
    currentItem = it;
    detailTitle.textContent = it.title;
    renderDetailMeta(it);
    detailBody.innerHTML = it.summary_html; // 已在后端修复换行并渲染
    buildDetailToc();
    detailView.classList.remove('hidden');
    document.body.classList.add('detail-open');
    window.scrollTo(0, 0);
    detailBack.focus();
  }

  function openDetail(it, card){
    lastScrollY = window.scrollY || 0;
    lastFocusedCard = card || document.activeElement;
    showDetail(it);
    history.pushState({ view: 'detail', item: it }, '', window.location.href);
  }

  function hideDetail(){
    detailView.classList.add('hidden');
    detailToc.classList.add('hidden');
    detailTocNav.innerHTML = '';
    currentItem = null;
    document.body.classList.remove('detail-open');
  }

  function restoreListState(){
    requestAnimationFrame(() => window.scrollTo(0, lastScrollY));
    if(lastFocusedCard && typeof lastFocusedCard.focus === 'function'){
      lastFocusedCard.focus();
    }
  }

  function closeDetail(){
    if(history.state && history.state.view === 'detail'){
      history.back();
      return;
    }
    hideDetail();
    restoreListState();
  }

  function sync(){
    const items = filterItems(DATA, searchEl.value);

    if(!DATA.length){
      renderGroups([]);
      renderStatus('empty', '还没有论文数据', '当前数据集中没有可展示的论文。等抓取任务跑完后，这里会自动显示。');
      return;
    }

    if(!items.length){
      renderGroups([]);
      renderStatus(
        'empty',
        '没有找到匹配结果',
        `试试换个关键词，当前一共收录了 ${DATA.length} 篇论文。`,
        {
          label: '清空搜索',
          onClick: () => {
            searchEl.value = '';
            sync();
            searchEl.focus();
          }
        }
      );
      return;
    }

    clearStatus();
    renderGroups(items);
  }

  detailBack.addEventListener('click', closeDetail);
  document.addEventListener('keydown', (event) => {
    if(event.key === 'Escape' && !detailView.classList.contains('hidden')){
      event.preventDefault();
      closeDetail();
    }
  });

  window.addEventListener('popstate', (e) => {
    if (e.state && e.state.view === 'detail' && e.state.item) {
      showDetail(e.state.item);
    } else {
      hideDetail();
      restoreListState();
    }
  });

  searchEl.addEventListener('input', sync);

  async function loadData(){
    renderStatus('loading', '正在加载论文列表', '页面正在读取静态数据并构建卡片，你可以稍后直接开始搜索。');
    try{
      const response = await fetch('assets/data.json');
      if(!response.ok){
        throw new Error(`HTTP ${response.status}`);
      }
      DATA = await response.json();
      sync();
    } catch (error) {
      console.error(error);
      renderGroups([]);
      renderStatus(
        'error',
        '论文数据加载失败',
        '无法读取 data.json。你可以刷新页面重试，或者确认静态资源是否已成功构建。',
        { label: '重新加载', onClick: loadData }
      );
    }
  }

  loadData();
})();
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
