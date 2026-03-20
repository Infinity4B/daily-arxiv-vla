#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
生成静态站点：
1) 解析项目根目录下的 `papers.md` 表格（列：日期/标题/链接/简要总结）。
2) 从第四列提取 <details> ... </details> 中的实际内容。
3) 对内容进行“自动补换行”修复（因原始换行丢失）。
4) 将修复后的 Markdown 渲染为 HTML（无第三方依赖，内置简易渲染器）。
5) 输出站点到 `site/`：
   - `index.html`
   - `assets/style.css`
   - `assets/app.js`
   - `assets/paper.js`
   - `assets/data.json`（列表页轻量数据）
   - `papers/<arxiv-id>/index.html`（每篇论文独立静态页面）
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from html import escape
from pathlib import Path
from typing import Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_MD = PROJECT_ROOT / "papers.md"
SITE_DIR = PROJECT_ROOT / "site"
ASSETS_DIR = SITE_DIR / "assets"
PAPERS_DIR = SITE_DIR / "papers"


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
    for line in lines[2:]:
        if not line.strip().startswith("|"):
            continue

        parts = [p.strip() for p in line.strip().strip("|").split("|")]
        if len(parts) < 4:
            continue

        date_str, title, link = parts[0], parts[1], parts[2]
        summary_cell = "|".join(parts[3:]).strip()
        details_content = extract_details(summary_cell)
        records.append(
            {
                "date": date_str,
                "title": title,
                "link": link,
                "details_raw": details_content,
            }
        )
    return records


def extract_details(cell_html: str) -> str:
    """
    从单元格中提取 <details> 内容，去除 <summary>...
    """
    match = re.search(r"<details>([\s\S]*?)</details>", cell_html, re.IGNORECASE)
    content = match.group(1) if match else cell_html
    content = re.sub(r"<summary>[\s\S]*?</summary>", "", content, flags=re.IGNORECASE)
    content = content.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    return content.strip()


def auto_add_linebreaks(text: str) -> str:
    """
    自动添加换行符的启发式规则（仅在换行已丢失时使用）。
    """
    fixed = text
    has_linebreaks = "\n" in fixed

    if has_linebreaks:
        fixed = re.sub(r"([^\n\s#])\s*(?=#+\s)", r"\1\n", fixed)
        fixed = re.sub(r"([^\n])\s*---\s*([^\n])", r"\1\n---\n\2", fixed)
        fixed = re.sub(r"\n{3,}", "\n\n", fixed)
        return fixed.strip()

    fixed = re.sub(r"([^\n\s#])\s*(?=#+\s)", r"\1\n", fixed)
    if not fixed.startswith("#"):
        fixed = re.sub(r"^\s*(#+\s+)", r"\1", fixed)

    fixed = re.sub(r"\s*---\s*", "\n---\n", fixed)
    fixed = re.sub(r"\s+[-–]\s+", "\n- ", fixed)
    fixed = re.sub(r"(?<!\n)(?<!\*\*)(\s*)(\d+\.\s+)", lambda m: "\n" + m.group(2), fixed)
    fixed = re.sub(r"\s+-\s+\*\*(.+?)\*\*", lambda m: "\n- **" + m.group(1) + "**", fixed)
    fixed = re.sub(r"([。！？；])\s*(#+\s+)", r"\1\n\2", fixed)
    fixed = re.sub(r"\n{3,}", "\n\n", fixed)
    return fixed.strip()


def markdown_to_html(md: str) -> str:
    """
    简易 Markdown 渲染器，支持标题、列表、行内粗体/代码/链接、段落。
    """
    lines = md.splitlines()
    html_lines: List[str] = []

    def render_inline(text: str) -> str:
        text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
        text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(
            r"\[([^\]]+)\]\(([^)]+)\)",
            r"<a href=\"\2\" target=\"_blank\" rel=\"noopener noreferrer\">\1</a>",
            text,
        )
        return text

    index = 0
    while index < len(lines):
        line = lines[index].rstrip()

        if not line:
            html_lines.append("")
            index += 1
            continue

        title_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if title_match:
            level = min(len(title_match.group(1)), 4)
            title_text = title_match.group(2).strip()
            class_attr = ' class="section-title"' if level == 2 else ""
            html_lines.append(f"<h{level}{class_attr}>{render_inline(title_text)}</h{level}>")
            index += 1
            continue

        if line.strip() == "---":
            html_lines.append("<hr/>")
            index += 1
            continue

        if re.match(r"^[-*]\s+", line):
            items: List[str] = []
            while index < len(lines):
                current = lines[index].rstrip()
                if not current:
                    break
                if re.match(r"^[-*]\s+", current):
                    item_text = re.sub(r"^[-*]\s+", "", current).strip()
                    items.append(f"<li>{render_inline(item_text)}</li>")
                    index += 1
                    continue
                break
            html_lines.append("<ul>" + "".join(items) + "</ul>")
            continue

        if re.match(r"^\d+\.\s+", line):
            items = []
            while index < len(lines):
                current = lines[index].rstrip()
                if not current:
                    break
                if re.match(r"^\d+\.\s+", current):
                    item_text = re.sub(r"^\d+\.\s+", "", current).strip()
                    items.append(f"<li>{render_inline(item_text)}</li>")
                    index += 1
                    continue
                break
            html_lines.append("<ol>" + "".join(items) + "</ol>")
            continue

        html_lines.append(f"<p>{render_inline(line)}</p>")
        index += 1

    collapsed: List[str] = []
    previous_blank = False
    for line in html_lines:
        is_blank = line == ""
        if is_blank and previous_blank:
            continue
        collapsed.append(line)
        previous_blank = is_blank

    return "\n".join(collapsed).strip()


def extract_section_block(markdown: str, titles: List[str]) -> str:
    for title in titles:
        escaped = re.escape(title)
        match = re.search(rf"##\s*{escaped}[\s\S]*?(?=##|$)", markdown)
        if match:
            return match.group(0)
    return ""


def extract_research_unit(markdown: str) -> str:
    block = extract_section_block(markdown, ["研究单位", "论文研究单位"])
    if not block:
        return ""

    first_bullet = ""
    for line in block.splitlines():
        candidate = line.strip()
        if candidate.startswith("- "):
            first_bullet = candidate
            break

    if not first_bullet:
        stripped = re.sub(r"^##\s*[^\n]+\n?", "", block).strip()
        first_line = stripped.splitlines()[0].strip() if stripped else ""
        first_bullet = first_line

    if not first_bullet:
        return ""

    return (
        first_bullet.replace("- ", "", 1)
        .replace("**", "")
        .replace("`", "")
        .replace("作者主要来自", "")
        .replace("作者来自", "")
        .strip()
    )


def strip_markdown(text: str) -> str:
    plain = text
    plain = re.sub(r"<[^>]+>", " ", plain)
    plain = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", plain)
    plain = re.sub(r"`([^`]+)`", r"\1", plain)
    plain = re.sub(r"\*\*([^*]+)\*\*", r"\1", plain)
    plain = re.sub(r"^#{1,6}\s*", "", plain, flags=re.MULTILINE)
    plain = re.sub(r"^\s*[-*]\s+", "", plain, flags=re.MULTILINE)
    plain = re.sub(r"^\s*\d+\.\s+", "", plain, flags=re.MULTILINE)
    plain = re.sub(r"\s+", " ", plain)
    return plain.strip()


def build_preview(markdown: str) -> str:
    overview = extract_section_block(markdown, ["论文概述"])
    if overview:
        text = strip_markdown(re.sub(r"^##\s*论文概述\s*", "", overview))
    else:
        text = strip_markdown(markdown)
    return text[:200].strip()


def normalize_arxiv_id(value: str) -> str:
    match = re.search(r"arxiv\.org/(?:abs|pdf)/([^?#]+)", value, re.IGNORECASE)
    if not match:
        return ""

    arxiv_id = match.group(1).strip().rstrip("/")
    if arxiv_id.lower().endswith(".pdf"):
        arxiv_id = arxiv_id[:-4]
    arxiv_id = re.sub(r"v\d+$", "", arxiv_id, flags=re.IGNORECASE)
    return arxiv_id


def get_translation_link(link: str) -> str:
    arxiv_id = normalize_arxiv_id(link)
    return f"https://hjfy.top/arxiv/{arxiv_id}" if arxiv_id else ""


def slugify_fallback(text: str) -> str:
    slug = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", text.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug or "paper"


def make_page_dir_name(arxiv_id: str, title: str) -> str:
    if arxiv_id:
        return arxiv_id.replace("/", "-")
    return slugify_fallback(title)


def build_site_records(records: List[Dict[str, str]]) -> List[Dict[str, str]]:
    built: List[Dict[str, str]] = []
    for record in records:
        summary_markdown = auto_add_linebreaks(record["details_raw"])
        summary_html = markdown_to_html(summary_markdown)
        arxiv_id = normalize_arxiv_id(record["link"])
        page_dir = make_page_dir_name(arxiv_id, record["title"])
        preview_text = build_preview(summary_markdown)
        research_unit = extract_research_unit(summary_markdown)

        built.append(
            {
                "date": record["date"],
                "title": record["title"],
                "link": record["link"],
                "arxiv_id": arxiv_id,
                "page_dir": page_dir,
                "detail_path": f"papers/{page_dir}/",
                "preview_text": preview_text,
                "research_unit": research_unit,
                "translation_link": get_translation_link(record["link"]),
                "summary_markdown": summary_markdown,
                "summary_html": summary_html,
            }
        )
    return built


def build_list_data(records: List[Dict[str, str]]) -> List[Dict[str, str]]:
    return [
        {
            "date": record["date"],
            "title": record["title"],
            "link": record["link"],
            "arxiv_id": record["arxiv_id"],
            "detail_path": record["detail_path"],
            "preview_text": record["preview_text"],
            "research_unit": record["research_unit"],
        }
        for record in records
    ]


def render_detail_meta(record: Dict[str, str]) -> str:
    parts = [escape(record["date"])]
    parts.append(
        f'<a href="{escape(record["link"], quote=True)}" target="_blank" rel="noopener noreferrer">原文链接</a>'
    )
    if record["translation_link"]:
        parts.append(
            f'<a href="{escape(record["translation_link"], quote=True)}" target="_blank" rel="noopener noreferrer">幻觉翻译</a>'
        )
    if record["arxiv_id"]:
        parts.append(f'<span class="meta-id">{escape(record["arxiv_id"])}</span>')
    return " · ".join(parts)


def generate_index_html() -> str:
    keyword = os.getenv("ARXIV_QUERY_KEYWORD", "VLA")
    site_title = f"{keyword} 论文精选"
    site_subtitle = f"精选 {keyword} 相关的最新 arXiv 论文"

    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{escape(site_title)} - ArXiv Papers</title>
    <meta name="description" content="{escape(site_subtitle, quote=True)}" />
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet" />
    <link rel="stylesheet" href="assets/style.css" />
  </head>
  <body>
    <div class="bg-gradient"></div>
    <header class="header">
      <div class="container">
        <div class="header-content">
          <div class="header-text">
            <h1 class="site-title">
              <span class="icon">📚</span>
              {escape(site_title)}
            </h1>
            <p class="site-subtitle">{escape(site_subtitle)}</p>
          </div>
          <div class="search-wrapper">
            <svg class="search-icon" width="20" height="20" viewBox="0 0 20 20" fill="none">
              <path d="M9 17A8 8 0 1 0 9 1a8 8 0 0 0 0 16zM18 18l-4-4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            <input id="search" type="search" placeholder="搜索论文标题、摘要预览或 arXiv ID..." aria-label="搜索" />
          </div>
        </div>
      </div>
    </header>

    <main class="container main-content">
      <section id="status" class="status-panel hidden" aria-live="polite"></section>
      <section id="groups"></section>
    </main>

    <footer class="footer">
      <div class="container">
        <p>数据来源：<a href="https://arxiv.org" target="_blank" rel="noopener noreferrer">arXiv.org</a></p>
      </div>
    </footer>

    <script src="assets/app.js"></script>
  </body>
</html>
""".strip()


def generate_paper_html(record: Dict[str, str]) -> str:
    keyword = os.getenv("ARXIV_QUERY_KEYWORD", "VLA")
    site_title = f"{keyword} 论文精选"
    page_title = record["title"]
    page_description = record["preview_text"] or f"{keyword} 论文详情"
    meta_html = render_detail_meta(record)

    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{escape(page_title)} - {escape(site_title)}</title>
    <meta name="description" content="{escape(page_description, quote=True)}" />
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet" />
    <link rel="stylesheet" href="../../assets/style.css" />
  </head>
  <body class="detail-page" data-paper-id="{escape(record["arxiv_id"] or record["page_dir"], quote=True)}">
    <div class="bg-gradient"></div>
    <header class="header detail-page-header">
      <div class="container">
        <div class="detail-page-topbar">
          <a class="back-link" href="../../index.html">返回列表</a>
          <span class="detail-site-name">{escape(site_title)}</span>
        </div>
        <div class="detail-hero">
          <p class="detail-kicker">论文详情</p>
          <h1 class="detail-page-title">{escape(page_title)}</h1>
          <div class="detail-meta">{meta_html}</div>
        </div>
      </div>
    </header>

    <main class="container detail-layout">
      <div class="detail-shell">
        <div class="detail-main">
          <article id="detail-body">{record["summary_html"]}</article>
        </div>
        <aside id="detail-toc" class="detail-toc hidden" aria-label="内容目录">
          <p class="detail-toc-title">内容目录</p>
          <nav id="detail-toc-nav" class="detail-toc-nav"></nav>
        </aside>
      </div>
    </main>

    <footer class="footer">
      <div class="container">
        <p>数据来源：<a href="https://arxiv.org" target="_blank" rel="noopener noreferrer">arXiv.org</a></p>
      </div>
    </footer>

    <script src="../../assets/paper.js"></script>
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
}

* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

html {
  scroll-behavior: smooth;
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

.main-content,
.detail-layout {
  position: relative;
  z-index: 1;
  padding-bottom: 80px;
}

.status-panel.hidden,
.detail-toc.hidden {
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

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 24px;
}

.card-link {
  text-decoration: none;
  color: inherit;
  display: block;
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

.card-link:focus-visible,
.back-link:focus-visible,
.detail-toc-link:focus-visible,
input[type=search]:focus-visible,
.status-action:focus-visible {
  outline: none;
  box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.16);
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

.detail-page-header {
  padding-bottom: 12px;
}

.detail-page-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 28px;
}

.back-link {
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
  text-decoration: none;
}

.back-link::before {
  content: '←';
}

.back-link:hover {
  border-color: var(--accent);
  background: var(--card-hover);
}

.detail-site-name,
.detail-kicker,
.detail-meta,
.footer,
.group-count {
  color: var(--text-secondary);
}

.detail-site-name {
  font-size: 14px;
}

.detail-kicker {
  font-size: 13px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  margin-bottom: 12px;
}

.detail-page-title {
  font-size: 40px;
  font-weight: 700;
  line-height: 1.25;
  margin-bottom: 16px;
}

.detail-meta {
  font-size: 15px;
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

.meta-id {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.03);
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

.detail-toc {
  position: sticky;
  top: 24px;
  background: rgba(15, 20, 25, 0.82);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 18px;
}

.detail-toc-title {
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
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

article a,
.footer a {
  color: var(--accent);
  text-decoration: none;
  transition: color 0.2s ease;
}

article a:hover,
.footer a:hover {
  color: var(--accent-hover);
}

article a:hover {
  text-decoration: underline;
}

hr {
  border: none;
  border-top: 1px solid var(--border);
  margin: 32px 0;
}

.footer {
  position: relative;
  z-index: 1;
  padding: 32px 0;
  border-top: 1px solid var(--border);
  text-align: center;
  font-size: 14px;
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

  .status-card {
    padding: 20px;
  }

  .group-heading {
    align-items: flex-start;
    flex-direction: column;
  }

  .detail-page-topbar {
    align-items: flex-start;
    flex-direction: column;
  }

  .detail-page-title {
    font-size: 28px;
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
 * @description 首页逻辑：加载轻量 data.json，渲染卡片与搜索。
 */
(function(){
  /** @type {Array<{date:string,title:string,link:string,arxiv_id:string,detail_path:string,preview_text:string,research_unit:string}>} */
  let DATA = [];

  const $ = (sel) => document.querySelector(sel);
  const statusEl = $('#status');
  const groupsEl = $('#groups');
  const searchEl = $('#search');

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

  function buildSearchText(item){
    return [
      item.title || '',
      item.preview_text || '',
      item.research_unit || '',
      item.arxiv_id || ''
    ].join(' ').toLowerCase();
  }

  function filterItems(items, query){
    const keyword = (query || '').trim().toLowerCase();
    if(!keyword){
      return items;
    }
    return items.filter((item) => buildSearchText(item).includes(keyword));
  }

  function renderGroups(items){
    if(!items.length){
      groupsEl.innerHTML = '';
      return;
    }

    const grouped = new Map();
    items.forEach((item) => {
      if(!grouped.has(item.date)){
        grouped.set(item.date, []);
      }
      grouped.get(item.date).push(item);
    });

    const dates = Array.from(grouped.keys()).sort((a, b) => b.localeCompare(a));
    groupsEl.innerHTML = '';

    dates.forEach((date) => {
      const group = document.createElement('section');
      group.className = 'group';

      const heading = document.createElement('div');
      heading.className = 'group-heading';

      const h2 = document.createElement('h2');
      h2.textContent = date;

      const count = document.createElement('div');
      count.className = 'group-count';
      count.textContent = `${grouped.get(date).length} 篇`;

      const grid = document.createElement('div');
      grid.className = 'grid';

      grouped.get(date).forEach((item) => {
        const cardLink = document.createElement('a');
        cardLink.className = 'card-link';
        cardLink.href = item.detail_path;
        cardLink.setAttribute('aria-label', `查看论文：${item.title}`);

        const card = document.createElement('article');
        card.className = 'card';

        const tags = document.createElement('div');
        tags.className = 'card-tags';

        if(item.research_unit){
          const orgTag = document.createElement('div');
          orgTag.className = 'card-tag primary';
          orgTag.textContent = item.research_unit;
          tags.appendChild(orgTag);
        }

        if(item.arxiv_id){
          const idTag = document.createElement('div');
          idTag.className = 'card-tag';
          idTag.textContent = item.arxiv_id;
          tags.appendChild(idTag);
        }

        const title = document.createElement('div');
        title.className = 'title';
        title.textContent = item.title;

        const preview = document.createElement('div');
        preview.className = 'summary-preview';
        preview.textContent = item.preview_text || '暂无摘要预览';

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
        cardLink.appendChild(card);
        grid.appendChild(cardLink);
      });

      heading.appendChild(h2);
      heading.appendChild(count);
      group.appendChild(heading);
      group.appendChild(grid);
      groupsEl.appendChild(group);
    });
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


def generate_paper_js() -> str:
    return """
/**
 * @file paper.js
 * @description 论文详情页逻辑：构建目录并按 arXiv id 记录滚动进度。
 */
(function(){
  const $ = (sel) => document.querySelector(sel);
  const detailBody = $('#detail-body');
  const detailToc = $('#detail-toc');
  const detailTocNav = $('#detail-toc-nav');
  const paperId = document.body.dataset.paperId || '';

  function slugifyHeading(text, index){
    const slug = (text || '')
      .trim()
      .toLowerCase()
      .replace(/[^\\w\\u4e00-\\u9fff]+/g, '-')
      .replace(/^-+|-+$/g, '');
    return slug ? `section-${index}-${slug}` : `section-${index}`;
  }

  function buildDetailToc(){
    if(!detailBody || !detailToc || !detailTocNav){
      return;
    }

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
      detailTocNav.appendChild(link);
    });

    detailToc.classList.remove('hidden');
  }

  function getStorageKey(){
    return paperId ? `paper-scroll:${paperId}` : '';
  }

  function restoreScroll(){
    if(!paperId || window.location.hash){
      return;
    }

    const storageKey = getStorageKey();
    if(!storageKey){
      return;
    }

    try{
      const saved = window.localStorage.getItem(storageKey);
      if(saved === null){
        return;
      }

      const scrollY = Number(saved);
      if(!Number.isFinite(scrollY) || scrollY <= 0){
        return;
      }

      window.requestAnimationFrame(() => {
        window.scrollTo(0, scrollY);
      });
    } catch (error) {
      console.warn('恢复滚动进度失败', error);
    }
  }

  function saveScroll(){
    const storageKey = getStorageKey();
    if(!storageKey){
      return;
    }

    try{
      window.localStorage.setItem(storageKey, String(window.scrollY || 0));
    } catch (error) {
      console.warn('保存滚动进度失败', error);
    }
  }

  let ticking = false;
  window.addEventListener('scroll', () => {
    if(ticking){
      return;
    }

    ticking = true;
    window.requestAnimationFrame(() => {
      saveScroll();
      ticking = false;
    });
  }, { passive: true });

  window.addEventListener('pagehide', saveScroll);

  buildDetailToc();
  restoreScroll();
})();
""".strip()


def main() -> int:
    if not INPUT_MD.exists():
        print(f"未找到 {INPUT_MD}", file=sys.stderr)
        return 1

    md_text = read_text(INPUT_MD)
    records = parse_markdown_table(md_text)
    site_records = build_site_records(records)
    list_data = build_list_data(site_records)

    shutil.rmtree(PAPERS_DIR, ignore_errors=True)

    write_text(SITE_DIR / "index.html", generate_index_html())
    write_text(ASSETS_DIR / "style.css", generate_style_css())
    write_text(ASSETS_DIR / "app.js", generate_app_js())
    write_text(ASSETS_DIR / "paper.js", generate_paper_js())
    write_text(ASSETS_DIR / "data.json", json.dumps(list_data, ensure_ascii=False, indent=2))

    for record in site_records:
        write_text(PAPERS_DIR / record["page_dir"] / "index.html", generate_paper_html(record))

    print(f"生成完成：{SITE_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
