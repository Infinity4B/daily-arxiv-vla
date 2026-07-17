#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
生成静态站点：
1) 解析项目根目录下的 `papers.md` 表格（列：日期/标题/链接/简要总结）。
2) 从第四列提取 <details> ... </details> 中的实际内容。
3) 对内容进行“自动补换行”修复。
4) 生成首页信息流、详情页阅读卡片，以及每篇论文独立的封面 HTML。
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import sys
from html import escape
from pathlib import Path
from typing import Dict, List

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_MD = PROJECT_ROOT / "papers.md"
SITE_DIR = PROJECT_ROOT / "site"
ASSETS_DIR = SITE_DIR / "assets"
PAPERS_DIR = SITE_DIR / "papers"
COVERS_DIR = SITE_DIR / "covers"
IMAGE_DIR = ASSETS_DIR / "paper-images"
PAPER_IMAGES_MANIFEST = ASSETS_DIR / "paper-images.json"
DEFAULT_ARXIV_QUERY = 'all:"VLA" OR all:"Vision-Language-Action"'
DEFAULT_ARXIV_KEYWORD_LABEL = "VLA / Vision-Language-Action"

COVER_THEMES = [
    {
        "from": "#ef6c3f",
        "to": "#f6b13d",
        "spot": "#ffd59c",
        "ink": "#fff8ef",
        "muted": "rgba(255, 248, 239, 0.82)",
        "chip": "rgba(255, 248, 239, 0.16)",
        "stroke": "rgba(255, 248, 239, 0.26)",
    },
    {
        "from": "#d84f61",
        "to": "#f29c6b",
        "spot": "#ffd6c4",
        "ink": "#fff7f4",
        "muted": "rgba(255, 247, 244, 0.82)",
        "chip": "rgba(255, 247, 244, 0.16)",
        "stroke": "rgba(255, 247, 244, 0.24)",
    },
    {
        "from": "#177e89",
        "to": "#5ec2a8",
        "spot": "#c5f0de",
        "ink": "#f5fffb",
        "muted": "rgba(245, 255, 251, 0.82)",
        "chip": "rgba(245, 255, 251, 0.16)",
        "stroke": "rgba(245, 255, 251, 0.24)",
    },
    {
        "from": "#3f6ee8",
        "to": "#6fa7ff",
        "spot": "#d5e6ff",
        "ink": "#f7fbff",
        "muted": "rgba(247, 251, 255, 0.82)",
        "chip": "rgba(247, 251, 255, 0.16)",
        "stroke": "rgba(247, 251, 255, 0.24)",
    },
    {
        "from": "#6f4cc9",
        "to": "#c57be8",
        "spot": "#efd9ff",
        "ink": "#fdf7ff",
        "muted": "rgba(253, 247, 255, 0.82)",
        "chip": "rgba(253, 247, 255, 0.16)",
        "stroke": "rgba(253, 247, 255, 0.24)",
    },
    {
        "from": "#316b57",
        "to": "#8bb174",
        "spot": "#d9e7c7",
        "ink": "#fbfff6",
        "muted": "rgba(251, 255, 246, 0.82)",
        "chip": "rgba(251, 255, 246, 0.16)",
        "stroke": "rgba(251, 255, 246, 0.24)",
    },
]

SECTION_TITLE_ALIASES = {
    "论文研究单位": "研究单位",
    "研究单位": "研究单位",
    "论文概述": "论文概述",
    "论文总结": "论文概述",
    "核心贡献": "核心贡献",
    "论文核心贡献点": "核心贡献",
    "论文核心贡献": "核心贡献",
    "方法描述": "方法描述",
    "论文方法描述": "方法描述",
    "数据集与资源": "数据集与资源",
    "论文使用数据集和训练资源": "数据集与资源",
    "论文使用数据集与训练资源": "数据集与资源",
    "评估与结果": "评估与结果",
    "论文使用的评估环境和评估指标": "评估与结果",
    "论文使用评估环境和评估指标": "评估与结果",
}


def read_text(path: Path) -> str:
    with path.open("r", encoding="utf-8") as file:
        return file.read()


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        file.write(content)


def load_json(path: Path) -> object:
    if not path.exists():
        return {}
    try:
        return json.loads(read_text(path))
    except json.JSONDecodeError:
        return {}


def get_arxiv_keyword_label() -> str:
    keyword = os.getenv("ARXIV_QUERY_KEYWORD") or DEFAULT_ARXIV_QUERY
    if keyword == DEFAULT_ARXIV_QUERY:
        return DEFAULT_ARXIV_KEYWORD_LABEL
    return keyword


def parse_markdown_table(md_text: str) -> List[Dict[str, str]]:
    lines = [line for line in md_text.splitlines() if line.strip()]
    if len(lines) < 3:
        return []

    records: List[Dict[str, str]] = []
    for line in lines[2:]:
        if not line.strip().startswith("|"):
            continue

        parts = [part.strip() for part in line.strip().strip("|").split("|")]
        if len(parts) < 4:
            continue

        date_str, title, link = parts[0], parts[1], parts[2]
        summary_cell = "|".join(parts[3:]).strip()
        records.append(
            {
                "date": date_str,
                "title": title,
                "link": link,
                "details_raw": extract_details(summary_cell),
            }
        )

    return records


def extract_details(cell_html: str) -> str:
    match = re.search(r"<details>([\s\S]*?)</details>", cell_html, re.IGNORECASE)
    content = match.group(1) if match else cell_html
    content = re.sub(r"<summary>[\s\S]*?</summary>", "", content, flags=re.IGNORECASE)
    content = content.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    return content.strip()


def auto_add_linebreaks(text: str) -> str:
    fixed = text
    has_linebreaks = "\n" in fixed

    if has_linebreaks:
        fixed = re.sub(r"([^\n\s#])\s*(?=#+\s)", r"\1\n", fixed)
        fixed = re.sub(r"([^\n])\s*---\s*([^\n])", r"\1\n---\n\2", fixed)
        fixed = re.sub(r"\n{3,}", "\n\n", fixed)
        return fixed.strip()

    fixed = re.sub(r"([^\n\s#])\s*(?=#+\s)", r"\1\n", fixed)
    fixed = re.sub(r"\s*---\s*", "\n---\n", fixed)
    fixed = re.sub(r"\s+[-–]\s+", "\n- ", fixed)
    fixed = re.sub(r"(?<!\n)(?<!\*\*)(\s*)(\d+\.\s+)", lambda m: "\n" + m.group(2), fixed)
    fixed = re.sub(r"\s+-\s+\*\*(.+?)\*\*", lambda m: "\n- **" + m.group(1) + "**", fixed)
    fixed = re.sub(r"([。！？；])\s*(#+\s+)", r"\1\n\2", fixed)
    fixed = re.sub(r"\n{3,}", "\n\n", fixed)
    return fixed.strip()


def markdown_to_html(md: str) -> str:
    lines = md.splitlines()
    html_lines: List[str] = []

    def render_inline(text: str) -> str:
        text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
        text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(
            r"\[([^\]]+)\]\(([^)]+)\)",
            r'<a href="\2" target="_blank" rel="noopener noreferrer">\1</a>',
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
            html_lines.append(f"<h{level}>{render_inline(title_text)}</h{level}>")
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


def normalize_section_title(title: str) -> str:
    normalized = re.sub(r"\s+", " ", title).strip()
    normalized = normalized.replace("：", "").replace(":", "")
    if normalized in SECTION_TITLE_ALIASES:
        return SECTION_TITLE_ALIASES[normalized]
    normalized = re.sub(r"^论文", "", normalized).strip()
    return SECTION_TITLE_ALIASES.get(normalized, normalized or "摘要")


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


def truncate_text(text: str, limit: int) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 1)].rstrip(" ，,.;；。:：") + "…"


def extract_bullets(markdown: str) -> List[str]:
    bullets: List[str] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        bullet_match = re.match(r"^[-*]\s+(.+)$", stripped)
        if bullet_match:
            bullets.append(strip_markdown(bullet_match.group(1)))
            continue

        numbered_match = re.match(r"^\d+\.\s+(.+)$", stripped)
        if numbered_match:
            bullets.append(strip_markdown(numbered_match.group(1)))

    if bullets:
        return [bullet for bullet in bullets if bullet]

    plain = strip_markdown(markdown)
    if not plain:
        return []

    sentences = re.split(r"(?<=[。！？；;.!?])\s+", plain)
    return [sentence.strip() for sentence in sentences if sentence.strip()][:3]


def parse_markdown_sections(markdown: str) -> List[Dict[str, str]]:
    lines = markdown.splitlines()
    sections: List[Dict[str, str]] = []
    current_title = ""
    current_lines: List[str] = []

    def flush() -> None:
        nonlocal current_title, current_lines
        body_md = "\n".join(current_lines).strip()
        if not current_title and not body_md:
            return

        title = normalize_section_title(current_title or "论文概述")
        body_md = body_md or "- 暂无内容"
        sections.append(
            {
                "title": title,
                "markdown": body_md,
                "html": markdown_to_html(body_md),
                "plain_text": strip_markdown(body_md),
                "bullets": extract_bullets(body_md),
            }
        )
        current_title = ""
        current_lines = []

    for line in lines:
        title_match = re.match(r"^##\s+(.+)$", line.strip())
        if title_match:
            flush()
            current_title = title_match.group(1).strip()
            continue
        current_lines.append(line)

    flush()

    if sections:
        return sections

    plain_markdown = markdown.strip() or "待生成"
    return [
        {
            "title": "论文概述",
            "markdown": plain_markdown,
            "html": markdown_to_html(plain_markdown),
            "plain_text": strip_markdown(plain_markdown),
            "bullets": extract_bullets(plain_markdown),
        }
    ]


def find_section(sections: List[Dict[str, str]], *keywords: str) -> Dict[str, str] | None:
    for section in sections:
        title = section["title"]
        if any(keyword in title for keyword in keywords):
            return section
    return None


def extract_research_unit(sections: List[Dict[str, str]]) -> str:
    section = find_section(sections, "研究单位")
    if not section:
        return ""

    bullets = section["bullets"]
    if bullets:
        return truncate_text(bullets[0], 52)

    return truncate_text(section["plain_text"], 52)


def build_preview(sections: List[Dict[str, str]]) -> str:
    overview = find_section(sections, "论文概述", "摘要")
    if overview and overview["plain_text"]:
        return overview["plain_text"].strip()

    for section in sections:
        if section["plain_text"]:
            return section["plain_text"].strip()

    return "待生成"


def build_key_points(sections: List[Dict[str, str]], preview_text: str) -> List[str]:
    preferred_sections = [
        find_section(sections, "论文概述", "摘要"),
        find_section(sections, "核心贡献"),
        find_section(sections, "评估与结果"),
        find_section(sections, "方法描述"),
    ]

    points: List[str] = []
    for section in preferred_sections:
        if not section:
            continue
        for bullet in section["bullets"]:
            if bullet and bullet not in points:
                points.append(bullet.strip())
            if len(points) >= 3:
                return points

    if preview_text:
        return [preview_text.strip()]

    return ["摘要还在生成中"]


def build_hook_text(key_points: List[str], preview_text: str) -> str:
    if key_points:
        return key_points[0].strip()
    if preview_text:
        return preview_text.strip()
    return "打开这张卡片，快速看懂论文重点。"


def estimate_reading_minutes(text: str) -> int:
    plain = strip_markdown(text)
    if not plain:
        return 1
    return max(1, math.ceil(len(plain) / 280))


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


def load_paper_image_manifest() -> Dict[str, Dict[str, object]]:
    data = load_json(PAPER_IMAGES_MANIFEST)
    return data if isinstance(data, dict) else {}


def get_paper_image_path(manifest: Dict[str, Dict[str, object]], arxiv_id: str) -> str:
    if not arxiv_id:
        return ""

    entry = manifest.get(arxiv_id)
    if not isinstance(entry, dict):
        return ""

    relative_path = entry.get("path")
    if not isinstance(relative_path, str) or not relative_path:
        return ""

    if not (SITE_DIR / relative_path).exists():
        return ""

    return relative_path


def slugify_fallback(text: str) -> str:
    slug = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", text.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug or "paper"


def make_page_dir_name(arxiv_id: str, title: str) -> str:
    if arxiv_id:
        return arxiv_id.replace("/", "-")
    return slugify_fallback(title)


def pick_cover_theme(seed: str) -> Dict[str, str]:
    total = sum(ord(char) for char in seed)
    return COVER_THEMES[total % len(COVER_THEMES)]


def theme_style(theme: Dict[str, str]) -> str:
    style_map = {
        "from": "--cover-from",
        "to": "--cover-to",
        "spot": "--cover-spot",
        "ink": "--cover-ink",
        "muted": "--cover-muted",
        "chip": "--cover-chip",
        "stroke": "--cover-stroke",
    }
    pairs = [f"{style_map[key]}: {value}" for key, value in theme.items() if key in style_map]
    return "; ".join(pairs)


def render_note_cover(record: Dict[str, object], standalone: bool = False) -> str:
    compact_class = " note-cover-standalone" if standalone else ""

    return f"""
<article class="note-cover note-cover-title-only{compact_class}" style="{escape(theme_style(record["cover_theme"]), quote=True)}">
  <div class="note-cover-mesh"></div>
  <div class="note-cover-title-shell">
    <h1 class="note-cover-title">{escape(str(record["title"]))}</h1>
  </div>
</article>
""".strip()


def render_paper_figure(record: Dict[str, object], image_src: str, context: str) -> str:
    caption = escape(str(record["hook_text"]))
    title = escape(str(record["title"]))

    return f"""
<figure class="paper-figure-card paper-figure-card-{context}">
  <img class="paper-figure-image" src="{escape(image_src, quote=True)}" alt="{title}" loading="lazy" onclick="window.openPaperFigureImage && window.openPaperFigureImage(this)" />
  <figcaption class="paper-figure-caption">{caption}</figcaption>
</figure>
""".strip()


def render_detail_intro(record: Dict[str, object]) -> str:
    point_items = "".join(f"<li>{escape(point)}</li>" for point in record["key_points"])  # type: ignore[index]
    cover_link = f"../../covers/{record['page_dir']}/"

    return f"""
<section class="reading-card reading-card-intro">
  <div class="reading-card-topline">
    <span class="reading-badge">一眼看懂</span>
    <a class="cover-preview-link" href="{escape(cover_link, quote=True)}">封面预览</a>
  </div>
  <p class="reading-intro-hook">{escape(str(record["hook_text"]))}</p>
  <ul class="reading-intro-points">{point_items}</ul>
</section>
""".strip()


def render_detail_sections(record: Dict[str, object]) -> str:
    parts = [render_detail_intro(record)]
    sections: List[Dict[str, str]] = record["sections"]  # type: ignore[assignment]

    for index, section in enumerate(sections, start=1):
        parts.append(
            f"""
<section class="reading-card reading-card-section">
  <div class="reading-card-topline">
    <span class="reading-step">Card {index:02d}</span>
    <span class="reading-step-note">{escape(section["title"])}</span>
  </div>
  <h2>{escape(section["title"])}</h2>
  <div class="reading-card-content">{section["html"]}</div>
</section>
""".strip()
        )

    return "\n".join(parts)


def build_site_records(records: List[Dict[str, str]], paper_image_manifest: Dict[str, Dict[str, object]]) -> List[Dict[str, object]]:
    built: List[Dict[str, object]] = []

    for record in records:
        summary_markdown = auto_add_linebreaks(record["details_raw"])
        sections = parse_markdown_sections(summary_markdown)
        preview_text = build_preview(sections)
        key_points = build_key_points(sections, preview_text)
        hook_text = build_hook_text(key_points, preview_text)
        arxiv_id = normalize_arxiv_id(record["link"])
        page_dir = make_page_dir_name(arxiv_id, record["title"])
        cover_theme = pick_cover_theme(arxiv_id or record["title"])
        reading_minutes = estimate_reading_minutes(summary_markdown)
        research_unit = extract_research_unit(sections)
        paper_image_path = get_paper_image_path(paper_image_manifest, arxiv_id)

        built.append(
            {
                "date": record["date"],
                "title": record["title"],
                "link": record["link"],
                "arxiv_id": arxiv_id,
                "page_dir": page_dir,
                "detail_path": f"papers/{page_dir}/",
                "cover_path": f"covers/{page_dir}/",
                "paper_image_path": paper_image_path,
                "translation_link": get_translation_link(record["link"]),
                "summary_markdown": summary_markdown,
                "sections": sections,
                "preview_text": preview_text,
                "research_unit": research_unit,
                "key_points": key_points,
                "hook_text": hook_text,
                "reading_minutes": reading_minutes,
                "section_count": len(sections),
                "cover_theme": cover_theme,
            }
        )

    return built


def build_list_data(records: List[Dict[str, object]], thumb_map: Dict[str, str] | None = None) -> List[Dict[str, object]]:
    thumb_map = thumb_map or {}
    return [
        {
            "date": record["date"],
            "title": record["title"],
            "link": record["link"],
            "arxiv_id": record["arxiv_id"],
            "detail_path": record["detail_path"],
            "cover_path": record["cover_path"],
            "paper_image_path": thumb_map.get(str(record["paper_image_path"]), record["paper_image_path"]),
            "paper_image_full_path": record["paper_image_path"],
            "preview_text": record["preview_text"],
            "research_unit": record["research_unit"],
            "hook_text": record["hook_text"],
            "key_points": record["key_points"],
            "reading_minutes": record["reading_minutes"],
            "section_count": record["section_count"],
            "cover_theme": record["cover_theme"],
        }
        for record in records
    ]


def render_detail_meta(record: Dict[str, object]) -> str:
    parts = [escape(str(record["date"]))]
    parts.append(f'<a href="{escape(str(record["link"]), quote=True)}" target="_blank" rel="noopener noreferrer">原文</a>')
    if record["translation_link"]:
        parts.append(
            f'<a href="{escape(str(record["translation_link"]), quote=True)}" target="_blank" rel="noopener noreferrer">翻译</a>'
        )
    if record["arxiv_id"]:
        parts.append(f'<span class="meta-pill">{escape(str(record["arxiv_id"]))}</span>')
    return " · ".join(parts)


def generate_head(title: str, description: str, stylesheet_prefix: str = "") -> str:
    stylesheet_path = f"{stylesheet_prefix}assets/style.css"
    favicon = (
        "data:image/svg+xml,"
        "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E"
        "%3Crect width='64' height='64' rx='18' fill='%23111827'/%3E"
        "%3Ctext x='50%25' y='55%25' text-anchor='middle' dominant-baseline='middle' "
        "font-size='30' font-family='Arial, sans-serif' fill='white'%3EV%3C/text%3E"
        "%3C/svg%3E"
    )
    return f"""
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{escape(title)}</title>
    <meta name="description" content="{escape(description, quote=True)}" />
    <script>
      (function() {{
        try {{
          var themePreference = window.localStorage.getItem('color-theme') || 'system';
          var systemUsesDarkTheme = window.matchMedia('(prefers-color-scheme: dark)').matches;
          var resolvedTheme = themePreference === 'system'
            ? (systemUsesDarkTheme ? 'dark' : 'light')
            : themePreference;
          document.documentElement.dataset.theme = resolvedTheme;
          document.documentElement.dataset.themePreference = themePreference;
          document.documentElement.style.colorScheme = resolvedTheme;
        }} catch (error) {{
          document.documentElement.dataset.theme = 'light';
          document.documentElement.dataset.themePreference = 'system';
        }}
      }})();
    </script>
    <link rel="icon" href="{favicon}" />
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Manrope:wght@500;600;700;800&family=Noto+Sans+SC:wght@400;500;600;700;800&display=swap" rel="stylesheet" />
    <link rel="stylesheet" href="{escape(stylesheet_path, quote=True)}" />
""".strip()


def render_theme_toggle() -> str:
    return """
<button class="theme-toggle" type="button" data-theme-toggle aria-label="当前主题：设备，点击切换主题" title="当前主题：设备">
  <span class="theme-toggle-icons" aria-hidden="true">
    <svg class="theme-toggle-icon theme-toggle-icon-light" viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="3.5" stroke="currentColor" stroke-width="1.8"/>
      <path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M18.7 5.3l-1.4 1.4M6.7 17.3l-1.4 1.4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
    </svg>
    <svg class="theme-toggle-icon theme-toggle-icon-dark" viewBox="0 0 24 24" fill="none">
      <path d="M20 15.2A8.1 8.1 0 0 1 8.8 4a8.2 8.2 0 1 0 11.2 11.2z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
    </svg>
    <svg class="theme-toggle-icon theme-toggle-icon-system" viewBox="0 0 24 24" fill="none">
      <rect x="3" y="4" width="18" height="13" rx="2.5" stroke="currentColor" stroke-width="1.8"/>
      <path d="M8 21h8M12 17v4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
    </svg>
  </span>
  <span class="theme-toggle-label" data-theme-toggle-label>设备</span>
</button>
""".strip()


def generate_index_html() -> str:
    keyword = get_arxiv_keyword_label()
    site_title = f"{keyword} 每日论文卡"
    site_description = f"{keyword} 论文精选卡片"

    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    {generate_head(f"{site_title} - ArXiv Papers", site_description)}
  </head>
  <body>
    <div class="page-noise"></div>
    <div class="page-blur page-blur-a"></div>
    <div class="page-blur page-blur-b"></div>

    <header class="header">
      <div class="container">
        <nav class="site-nav" aria-label="站点导航">
          <a class="site-brand" href="index.html" aria-label="返回首页">
            <span class="site-brand-mark">VLA</span>
            <span>Research Brief</span>
          </a>
          <div class="site-nav-actions">
            <span class="site-nav-status">
              <span class="site-nav-dot" aria-hidden="true"></span>
              每日自动更新
            </span>
            {render_theme_toggle()}
          </div>
        </nav>
        <div class="header-content">
          <div class="header-copy">
            <p class="eyebrow">VLA Intelligence Feed</p>
            <h1 class="site-title">{escape(keyword)} <span class="site-title-nowrap">每日论文卡</span></h1>
            <p class="site-subtitle">聚合最新论文，提炼核心贡献、方法与实验结果，用更清晰的阅读路径持续跟进前沿研究。</p>
            <div class="hero-tags" aria-label="站点特点">
              <span class="hero-tag">中文精读</span>
              <span class="hero-tag">核心贡献提炼</span>
              <span class="hero-tag">论文原图速览</span>
            </div>
          </div>
          <div class="search-panel">
            <div class="search-panel-heading">
              <span class="search-panel-title">探索论文库</span>
              <span class="search-availability"><span id="paper-count">加载中</span></span>
            </div>
            <label class="search-label" for="search">搜标题、机构、摘要亮点</label>
            <div class="search-wrapper">
              <svg class="search-icon" width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                <path d="M9 17A8 8 0 1 0 9 1a8 8 0 0 0 0 16zM18 18l-4-4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
              <input id="search" type="search" placeholder="比如：OpenVLA、香港大学、实时推理..." aria-label="搜索论文卡片" />
            </div>
            <p class="search-hint">支持同时输入多个关键词，将在标题、机构、摘要和 arXiv ID 中检索。</p>
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
        <p>内容来自 <a href="https://arxiv.org" target="_blank" rel="noopener noreferrer">arXiv.org</a>，封面与阅读卡片由静态站点生成器构建。</p>
      </div>
    </footer>

    <script src="assets/theme.js"></script>
    <script src="assets/media.js"></script>
    <script src="assets/app.js"></script>
  </body>
</html>
""".strip()


def generate_paper_html(record: Dict[str, object], prev_record: Dict[str, object] | None = None, next_record: Dict[str, object] | None = None) -> str:
    keyword = get_arxiv_keyword_label()
    site_title = f"{keyword} 每日论文卡"
    page_title = str(record["title"])
    page_description = str(record["preview_text"] or f"{keyword} 论文详情")
    meta_html = render_detail_meta(record)
    figure_src = f"../../{record['paper_image_path']}" if record["paper_image_path"] else ""
    cover_html = (
        render_paper_figure(record, figure_src, "detail")
        if figure_src
        else render_note_cover(record)
    )
    detail_body_html = render_detail_sections(record)

    nav_parts: List[str] = []
    if prev_record:
        nav_parts.append(
            f'<a class="paper-nav-link paper-nav-prev" href="../../papers/{escape(str(prev_record["page_dir"]), quote=True)}/">'
            f'<span class="paper-nav-label">\u2190 上一篇</span>'
            f'<span class="paper-nav-title">{escape(str(prev_record["title"]))}</span></a>'
        )
    if next_record:
        nav_parts.append(
            f'<a class="paper-nav-link paper-nav-next" href="../../papers/{escape(str(next_record["page_dir"]), quote=True)}/">'
            f'<span class="paper-nav-label">下一篇 \u2192</span>'
            f'<span class="paper-nav-title">{escape(str(next_record["title"]))}</span></a>'
        )
    nav_html = "\n      ".join(nav_parts)

    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    {generate_head(f"{page_title} - {site_title}", page_description, "../../")}
  </head>
  <body class="detail-page" data-paper-id="{escape(str(record["arxiv_id"] or record["page_dir"]), quote=True)}">
    <div class="page-noise"></div>
    <div class="page-blur page-blur-a"></div>
    <div class="page-blur page-blur-b"></div>

    <header class="header detail-page-header">
      <div class="container">
        <div class="detail-page-topbar">
          <a class="back-link" href="../../index.html">返回列表</a>
          <div class="detail-topbar-actions">
            <span class="detail-site-name">{escape(site_title)}</span>
            {render_theme_toggle()}
          </div>
        </div>

        <div class="detail-hero-grid">
          <div class="detail-hero-cover">{cover_html}</div>
          <div class="detail-hero-copy">
            <p class="eyebrow">论文详情</p>
            <h1 class="detail-page-title">{escape(page_title)}</h1>
            <div class="detail-meta">{meta_html}</div>
            <p class="detail-summary">{escape(str(record["preview_text"]))}</p>
            <div class="detail-micro-meta">
              <span class="meta-pill">{escape(str(record["reading_minutes"]))} 分钟读完</span>
              <span class="meta-pill">{escape(str(record["section_count"]))} 张阅读卡</span>
              {f'<span class="meta-pill">{escape(str(record["research_unit"]))}</span>' if record["research_unit"] else ''}
            </div>
          </div>
        </div>
      </div>
    </header>

    <main class="container detail-layout">
      <div class="detail-shell">
        <article id="detail-body" class="reading-flow">{detail_body_html}</article>
        <aside id="detail-toc" class="detail-toc hidden" aria-label="内容目录">
          <p class="detail-toc-title">阅读目录</p>
          <nav id="detail-toc-nav" class="detail-toc-nav"></nav>
        </aside>
      </div>
      <nav class="paper-nav">{nav_html}</nav>
    </main>

    <footer class="footer">
      <div class="container">
        <p>内容来自 <a href="https://arxiv.org" target="_blank" rel="noopener noreferrer">arXiv.org</a>，阅读卡片由静态站点生成器构建。</p>
      </div>
    </footer>

    <script src="../../assets/theme.js"></script>
    <script src="../../assets/media.js"></script>
    <script src="../../assets/paper.js"></script>
  </body>
</html>
""".strip()


def generate_cover_html(record: Dict[str, object]) -> str:
    keyword = get_arxiv_keyword_label()
    site_title = f"{keyword} 每日论文卡"
    page_title = f"{record['title']} - 封面卡"
    description = str(record["hook_text"])
    cover_html = render_note_cover(record, standalone=True)

    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    {generate_head(page_title, description, "../../")}
  </head>
  <body class="cover-page">
    <div class="page-noise"></div>
    <main class="cover-preview-page">
      <div class="cover-preview-shell">
        {cover_html}
        <div class="cover-preview-toolbar">
          <a class="back-link" href="../../papers/{escape(str(record["page_dir"]), quote=True)}/index.html">返回详情</a>
          <div class="detail-topbar-actions">
            <span class="detail-site-name">{escape(site_title)}</span>
            {render_theme_toggle()}
          </div>
        </div>
      </div>
    </main>
    <script src="../../assets/theme.js"></script>
  </body>
</html>
""".strip()


def generate_style_css() -> str:
    base_stylesheet = """
:root {
  --bg: #f7efe5;
  --bg-secondary: #fffaf3;
  --surface: rgba(255, 250, 243, 0.88);
  --paper: #fffdf8;
  --paper-strong: #fff5ea;
  --text: #24170f;
  --text-secondary: #735c49;
  --border: rgba(93, 60, 33, 0.12);
  --accent: #d75c2f;
  --accent-strong: #b74822;
  --accent-hover: #e86d3a;
  --shadow: 0 24px 64px rgba(126, 72, 37, 0.14);
  --shadow-hover: 0 32px 88px rgba(126, 72, 37, 0.22);
  --shadow-subtle: 0 8px 24px rgba(126, 72, 37, 0.08);
  --radius-xl: 32px;
  --radius-lg: 24px;
  --radius-md: 18px;
}

* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

html {
  scroll-behavior: smooth;
}

html,
body {
  min-height: 100%;
}

body {
  position: relative;
  background:
    radial-gradient(circle at top left, rgba(255, 206, 149, 0.4), transparent 38%),
    radial-gradient(circle at top right, rgba(240, 118, 78, 0.2), transparent 32%),
    radial-gradient(circle at bottom center, rgba(255, 180, 120, 0.15), transparent 45%),
    linear-gradient(180deg, #fff9f2 0%, #f7efe5 42%, #f5ece3 100%);
  color: var(--text);
  font-family: "Noto Sans SC", "PingFang SC", "Hiragino Sans GB", sans-serif;
  line-height: 1.7;
  overflow-x: hidden;
}

.page-noise {
  position: fixed;
  inset: 0;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.08) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.08) 1px, transparent 1px);
  background-size: 22px 22px;
  opacity: 0.18;
  pointer-events: none;
  z-index: 0;
}

.page-blur {
  position: fixed;
  width: 38rem;
  height: 38rem;
  border-radius: 999px;
  filter: blur(90px);
  opacity: 0.32;
  pointer-events: none;
  z-index: 0;
  animation: float 20s ease-in-out infinite;
}

@keyframes float {
  0%, 100% { transform: translate(0, 0) scale(1); }
  33% { transform: translate(20px, -30px) scale(1.05); }
  66% { transform: translate(-20px, 20px) scale(0.95); }
}

.page-blur-a {
  top: -12rem;
  left: -12rem;
  background: rgba(236, 121, 69, 0.48);
  animation-delay: 0s;
}

.page-blur-b {
  right: -12rem;
  bottom: -12rem;
  background: rgba(72, 157, 170, 0.28);
  animation-delay: -10s;
}

a {
  color: inherit;
}

.container {
  width: min(1180px, calc(100% - 40px));
  margin: 0 auto;
}

.header,
.main-content,
.footer,
.detail-layout,
.cover-preview-page {
  position: relative;
  z-index: 1;
}

.header {
  padding: 40px 0 24px;
}

.header-content {
  display: grid;
  gap: 24px;
}

.header-copy,
.search-panel,
.status-card,
.detail-toc,
.reading-card,
.detail-hero-copy {
  background: var(--surface);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid var(--border);
  box-shadow: var(--shadow);
  transition: box-shadow 0.3s ease, transform 0.3s ease;
}

.header-copy:hover,
.search-panel:hover {
  box-shadow: var(--shadow-hover);
  transform: translateY(-2px);
}

.header-copy {
  border-radius: var(--radius-xl);
  padding: 32px;
  background: linear-gradient(135deg, rgba(255, 250, 243, 0.92) 0%, rgba(255, 245, 235, 0.88) 100%);
}

.eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--accent);
  font-weight: 700;
  margin-bottom: 16px;
  position: relative;
}

.eyebrow::before {
  content: "";
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--accent);
  animation: pulse 2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.6; transform: scale(1.2); }
}

.site-title,
.detail-page-title,
.note-cover-title {
  font-family: "Outfit", "Noto Sans SC", sans-serif;
}

.site-title {
  font-size: clamp(2.1rem, 4vw, 4.25rem);
  line-height: 1.05;
  letter-spacing: -0.04em;
  margin-bottom: 12px;
  background: linear-gradient(135deg, var(--text) 0%, var(--accent-strong) 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.site-subtitle,
.detail-summary,
.status-text,
.feed-card-preview,
.detail-meta,
.detail-site-name,
.group-count,
.detail-toc-link,
.footer,
.cover-preview-toolbar {
  color: var(--text-secondary);
}

.site-subtitle {
  max-width: 44rem;
  font-size: 1rem;
}

.search-panel {
  border-radius: var(--radius-lg);
  padding: 18px;
}

.search-label {
  display: block;
  font-size: 13px;
  font-weight: 700;
  color: var(--text-secondary);
  margin-bottom: 10px;
}

.search-wrapper {
  position: relative;
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
  padding: 18px 20px 18px 52px;
  border-radius: 999px;
  border: 1px solid rgba(93, 60, 33, 0.16);
  background: rgba(255, 255, 255, 0.85);
  color: var(--text);
  font-size: 15px;
  outline: none;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: var(--shadow-subtle);
}

input[type=search]::placeholder {
  color: #a18b79;
}

input[type=search]:focus {
  border-color: rgba(215, 92, 47, 0.5);
  box-shadow: 0 0 0 5px rgba(215, 92, 47, 0.15), var(--shadow);
  transform: translateY(-2px);
  background: rgba(255, 255, 255, 0.95);
}

.main-content,
.detail-layout {
  padding-bottom: 72px;
}

.status-panel.hidden,
.detail-toc.hidden {
  display: none;
}

.status-card {
  border-radius: var(--radius-lg);
  padding: 22px 24px;
  margin-bottom: 28px;
}

.status-title {
  font-size: 17px;
  font-weight: 700;
  margin-bottom: 8px;
}

.status-action,
.back-link,
.cover-preview-link {
  appearance: none;
  border: 1px solid rgba(93, 60, 33, 0.14);
  background: rgba(255, 255, 255, 0.85);
  color: var(--text);
  border-radius: 999px;
  padding: 11px 18px;
  font-size: 14px;
  font-weight: 700;
  text-decoration: none;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: var(--shadow-subtle);
  cursor: pointer;
}

.status-action:hover,
.back-link:hover,
.cover-preview-link:hover,
.feed-card:hover,
.note-cover:hover {
  transform: translateY(-3px);
}

.status-action:hover,
.back-link:hover,
.cover-preview-link:hover {
  border-color: rgba(215, 92, 47, 0.35);
  background: rgba(255, 255, 255, 0.98);
  box-shadow: 0 12px 32px rgba(215, 92, 47, 0.18);
}

.group {
  margin: 44px 0;
}

.group-heading {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 18px;
}

.group h2 {
  font-family: "Outfit", "Noto Sans SC", sans-serif;
  font-size: 1.55rem;
  letter-spacing: -0.03em;
}

.group-count {
  font-size: 13px;
  font-weight: 700;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 22px;
}

.feed-card-link {
  text-decoration: none;
  color: inherit;
}

.feed-card {
  height: 100%;
  border-radius: 32px;
  overflow: hidden;
  background: linear-gradient(135deg, rgba(255, 252, 246, 0.95) 0%, rgba(255, 248, 238, 0.92) 100%);
  border: 1px solid rgba(93, 60, 33, 0.1);
  box-shadow: var(--shadow);
  transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
}

.feed-card::before {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, rgba(215, 92, 47, 0.03) 0%, transparent 50%);
  opacity: 0;
  transition: opacity 0.35s ease;
  pointer-events: none;
}

.feed-card:hover {
  border-color: rgba(215, 92, 47, 0.28);
  box-shadow: var(--shadow-hover);
}

.feed-card:hover::before {
  opacity: 1;
}

.feed-card-cover {
  padding: 16px;
}

.feed-card-figure,
.paper-figure-card {
  position: relative;
  overflow: hidden;
  border-radius: 26px;
  border: 1px solid rgba(93, 60, 33, 0.1);
  background: rgba(255, 255, 255, 0.72);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.7);
}

.feed-card-figure {
  aspect-ratio: 4 / 3;
}

.paper-figure-card {
  display: grid;
  gap: 0;
}

.feed-card-cover .note-cover {
  min-height: 0;
  aspect-ratio: 4 / 3;
  padding: 14px;
  gap: 10px;
}

.note-cover-title-only {
  justify-content: flex-end;
}

.note-cover-title-shell {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: flex-end;
  min-height: 100%;
}

.paper-figure-card-detail {
  min-height: 100%;
}

.paper-figure-image {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  background: linear-gradient(180deg, rgba(255,255,255,0.6), rgba(241, 226, 211, 0.9));
}

.paper-figure-card-detail .paper-figure-image {
  max-height: 520px;
  object-fit: contain;
  background: #fffdf8;
}

.paper-figure-badge {
  position: absolute;
  top: 14px;
  left: 14px;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 6px 12px;
  border-radius: 999px;
  background: rgba(36, 23, 15, 0.76);
  color: #fffaf4;
  font-size: 12px;
  font-weight: 700;
  backdrop-filter: blur(10px);
}

.paper-figure-caption {
  padding: 14px 16px 16px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-secondary);
  background: rgba(255, 253, 248, 0.94);
  border-top: 1px solid rgba(93, 60, 33, 0.08);
}

.feed-card-body {
  padding: 0 20px 20px;
}

.feed-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 14px;
}

.feed-chip,
.meta-pill,
.reading-badge,
.reading-step,
.reading-step-note,
.note-chip {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 6px 12px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}

.feed-chip,
.meta-pill,
.reading-step-note {
  background: rgba(215, 92, 47, 0.08);
  color: var(--accent);
}

.feed-chip.subtle,
.reading-step,
.note-chip-muted {
  background: rgba(93, 60, 33, 0.07);
  color: var(--text-secondary);
}

.feed-card-title {
  font-size: 1.15rem;
  line-height: 1.4;
  font-weight: 800;
  margin-bottom: 10px;
}

.feed-card-preview {
  font-size: 14px;
  line-height: 1.75;
  margin-bottom: 16px;
}

.feed-card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding-top: 14px;
  border-top: 1px solid rgba(93, 60, 33, 0.08);
}

.feed-card-action {
  font-size: 14px;
  font-weight: 800;
  color: var(--accent);
  position: relative;
  transition: color 0.3s ease;
}

.feed-card:hover .feed-card-action {
  color: var(--accent-hover);
}

.feed-card-action::after {
  content: "→";
  margin-left: 6px;
  display: inline-block;
  transition: transform 0.3s ease;
}

.feed-card:hover .feed-card-action::after {
  transform: translateX(4px);
}

.feed-card-stats {
  font-size: 12px;
  color: var(--text-secondary);
}

.note-cover {
  position: relative;
  min-height: 420px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 18px;
  padding: 20px;
  border-radius: 28px;
  overflow: hidden;
  color: var(--cover-ink, #fff8ef);
  background: linear-gradient(160deg, var(--cover-from, #ef6c3f) 0%, var(--cover-to, #f6b13d) 100%);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.24), var(--shadow);
  transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);
}

.note-cover:hover {
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.32), var(--shadow-hover);
}

.note-cover::before,
.note-cover::after {
  content: "";
  position: absolute;
  border-radius: 999px;
  pointer-events: none;
}

.note-cover::before {
  width: 15rem;
  height: 15rem;
  right: -5rem;
  top: -4rem;
  background: radial-gradient(circle, rgba(255, 255, 255, 0.38) 0%, transparent 68%);
}

.note-cover::after {
  width: 14rem;
  height: 14rem;
  left: -5rem;
  bottom: -6rem;
  background: radial-gradient(circle, rgba(255, 255, 255, 0.22) 0%, transparent 70%);
}

.note-cover-mesh {
  position: absolute;
  inset: 0;
  background:
    linear-gradient(120deg, rgba(255, 255, 255, 0.14), transparent 42%),
    radial-gradient(circle at 70% 24%, var(--cover-spot, rgba(255, 255, 255, 0.3)) 0%, transparent 32%),
    radial-gradient(circle at 22% 78%, rgba(255, 255, 255, 0.16) 0%, transparent 34%);
  mix-blend-mode: screen;
  opacity: 0.88;
}

.note-cover-top,
.note-cover-body,
.note-cover-points,
.note-cover-bottom {
  position: relative;
  z-index: 1;
}

.note-cover-top,
.note-cover-bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.note-chip {
  background: var(--cover-chip, rgba(255, 255, 255, 0.16));
  color: var(--cover-ink, #fff8ef);
  border: 1px solid var(--cover-stroke, rgba(255, 255, 255, 0.24));
  backdrop-filter: blur(10px);
}

.note-cover-kicker {
  font-size: 13px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--cover-muted, rgba(255, 248, 239, 0.82));
  margin-bottom: 14px;
  font-weight: 700;
}

.note-cover-title {
  font-size: clamp(1.9rem, 4vw, 2.55rem);
  line-height: 1.05;
  letter-spacing: -0.05em;
  margin: 0;
  max-width: 14ch;
  text-wrap: balance;
}

.note-cover-title-only .note-cover-title {
  font-size: clamp(2.05rem, 4.5vw, 2.9rem);
  line-height: 0.98;
  max-width: none;
}

.feed-card-cover .note-cover-title {
  font-size: 1.36rem;
  line-height: 1.16;
  letter-spacing: -0.04em;
  display: -webkit-box;
  -webkit-line-clamp: 5;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.feed-card-cover .note-cover-title-only .note-cover-title {
  font-size: 1.5rem;
  line-height: 1.08;
  max-width: none;
}

.note-cover-hook {
  margin-top: 14px;
  font-size: 15px;
  line-height: 1.75;
  color: var(--cover-muted, rgba(255, 248, 239, 0.82));
  max-width: 28rem;
}

.feed-card-cover .note-cover-hook {
  margin-top: 10px;
  font-size: 14px;
  line-height: 1.55;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.note-cover-points {
  display: grid;
  gap: 10px;
  list-style: none;
}

.feed-card-cover .note-cover-points {
  gap: 8px;
}

.note-cover-points li {
  position: relative;
  padding: 12px 14px 12px 42px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.12);
  border: 1px solid rgba(255, 255, 255, 0.12);
  backdrop-filter: blur(12px);
  font-size: 14px;
  line-height: 1.65;
}

.feed-card-cover .note-cover-points li {
  padding: 10px 12px 10px 34px;
  font-size: 13px;
  line-height: 1.45;
}

.note-cover-points li::before {
  content: "•";
  position: absolute;
  left: 16px;
  top: 10px;
  font-size: 24px;
  line-height: 1;
}

.feed-card-cover .note-cover-points li::before {
  left: 12px;
  top: 8px;
}

.note-cover-meta {
  font-size: 13px;
  color: var(--cover-muted, rgba(255, 248, 239, 0.82));
}

.feed-card-cover .note-cover-bottom {
  margin-top: auto;
}

.detail-page-header {
  padding-bottom: 12px;
}

.detail-page-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 24px;
}

.back-link::before {
  content: "←";
  margin-right: 8px;
}

.detail-site-name {
  font-size: 14px;
  font-weight: 700;
}

.detail-hero-grid {
  display: grid;
  grid-template-columns: minmax(300px, 420px) minmax(0, 1fr);
  gap: 24px;
  align-items: stretch;
}

.detail-hero-copy {
  border-radius: var(--radius-xl);
  padding: 28px;
}

.detail-page-title {
  font-size: clamp(2rem, 4vw, 3.4rem);
  line-height: 1.05;
  letter-spacing: -0.04em;
  margin-bottom: 16px;
}

.detail-meta {
  font-size: 15px;
  margin-bottom: 16px;
}

.detail-meta a,
.footer a {
  color: var(--accent);
  text-decoration: none;
}

.detail-meta a:hover,
.footer a:hover {
  color: var(--accent-strong);
}

.detail-summary {
  font-size: 15px;
  line-height: 1.85;
  margin-bottom: 16px;
}

.detail-micro-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.detail-shell {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 240px;
  gap: 28px;
  align-items: start;
}

.reading-flow {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.reading-card {
  border-radius: 28px;
  padding: 28px;
  background: linear-gradient(135deg, rgba(255, 250, 243, 0.92) 0%, rgba(255, 245, 235, 0.88) 100%);
  transition: all 0.3s ease;
}

.reading-card:hover {
  box-shadow: var(--shadow-hover);
  transform: translateY(-2px);
}

.reading-card-topline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

.reading-badge,
.reading-step {
  background: rgba(215, 92, 47, 0.12);
  color: var(--accent);
}

.reading-intro-hook {
  font-size: 20px;
  line-height: 1.55;
  font-weight: 800;
  margin-bottom: 16px;
}

.reading-intro-points {
  list-style: none;
  display: grid;
  gap: 10px;
}

.reading-intro-points li {
  padding: 14px 16px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(93, 60, 33, 0.08);
}

.reading-card h2 {
  font-family: "Outfit", "Noto Sans SC", sans-serif;
  font-size: 1.65rem;
  line-height: 1.15;
  letter-spacing: -0.03em;
  margin-bottom: 16px;
}

.reading-card-content h3,
.reading-card-content h4 {
  margin: 24px 0 12px;
  font-size: 1rem;
  color: var(--text);
}

.reading-card-content p,
.reading-card-content ul,
.reading-card-content ol {
  margin: 14px 0;
}

.reading-card-content ul,
.reading-card-content ol {
  padding-left: 24px;
}

.reading-card-content li {
  margin: 10px 0;
  color: var(--text-secondary);
}

.reading-card-content p,
.reading-card-content li {
  line-height: 1.85;
}

.reading-card-content strong {
  color: var(--text);
}

.reading-card-content code {
  background: rgba(215, 92, 47, 0.08);
  color: var(--accent);
  border-radius: 8px;
  padding: 2px 8px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.reading-card-content a {
  color: var(--accent);
  text-decoration: none;
}

.reading-card-content a:hover {
  text-decoration: underline;
}

.detail-toc {
  position: sticky;
  top: 24px;
  border-radius: 24px;
  padding: 18px;
}

.detail-toc-title {
  font-size: 12px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  font-weight: 700;
  margin-bottom: 12px;
}

.detail-toc-nav {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.detail-toc-link {
  padding: 10px 12px;
  border-radius: 14px;
  font-size: 14px;
  text-decoration: none;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
}

.detail-toc-link::before {
  content: "";
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 0;
  background: var(--accent);
  border-radius: 2px;
  transition: height 0.25s ease;
}

.detail-toc-link:hover,
.detail-toc-link.is-active {
  background: rgba(215, 92, 47, 0.1);
  color: var(--accent);
  padding-left: 16px;
}

.detail-toc-link:hover::before,
.detail-toc-link.is-active::before {
  height: 60%;
}

.paper-nav {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-top: 32px;
}

.paper-nav-link {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 22px;
  border-radius: var(--radius-lg);
  background: var(--surface);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid var(--border);
  box-shadow: var(--shadow);
  text-decoration: none;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
  overflow: hidden;
}

.paper-nav-link::before {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, rgba(215, 92, 47, 0.05) 0%, transparent 50%);
  opacity: 0;
  transition: opacity 0.3s ease;
}

.paper-nav-link:hover {
  transform: translateY(-3px);
  border-color: rgba(215, 92, 47, 0.35);
  box-shadow: var(--shadow-hover);
}

.paper-nav-link:hover::before {
  opacity: 1;
}

.paper-nav-prev {
  grid-column: 1;
}

.paper-nav-next {
  grid-column: 2;
  text-align: right;
}

.paper-nav-label {
  font-size: 13px;
  font-weight: 700;
  color: var(--accent);
}

.paper-nav-title {
  font-size: 14px;
  line-height: 1.5;
  color: var(--text);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.cover-page {
  min-height: 100vh;
}

.cover-preview-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px 20px;
}

.cover-preview-shell {
  width: min(100%, 640px);
  display: grid;
  gap: 16px;
}

.note-cover-standalone {
  min-height: 820px;
}

.cover-preview-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  padding: 0 6px;
}

.lazy-sentinel {
  height: 1px;
}

.footer {
  padding: 28px 0 36px;
  text-align: center;
  font-size: 14px;
}

.feed-card-link:focus-visible,
.back-link:focus-visible,
.cover-preview-link:focus-visible,
.detail-toc-link:focus-visible,
.paper-nav-link:focus-visible,
input[type=search]:focus-visible,
.status-action:focus-visible {
  outline: none;
  box-shadow: 0 0 0 4px rgba(215, 92, 47, 0.12);
}

@media (max-width: 960px) {
  .detail-hero-grid,
  .detail-shell {
    grid-template-columns: 1fr;
  }

  .detail-toc {
    position: static;
  }
}

@media (max-width: 768px) {
  .container {
    width: min(100%, calc(100% - 24px));
  }

  .header {
    padding-top: 24px;
  }

  .header-copy,
  .search-panel,
  .detail-hero-copy,
  .reading-card {
    padding: 20px;
  }

  .grid {
    grid-template-columns: 1fr;
  }

  .note-cover {
    min-height: 390px;
    padding: 18px;
  }

  .note-cover-title {
    font-size: 1.95rem;
  }

  .detail-page-topbar,
  .group-heading,
  .cover-preview-toolbar {
    flex-direction: column;
    align-items: flex-start;
  }

  .detail-page-title {
    font-size: 2.1rem;
  }

  .paper-nav {
    grid-template-columns: 1fr;
  }

  .paper-nav-next {
    grid-column: 1;
  }

  .note-cover-standalone {
    min-height: 700px;
  }
}
""".strip()

    modern_stylesheet_path = PROJECT_ROOT / "scripts" / "modern_ui.css"
    return f"{base_stylesheet}\n\n{read_text(modern_stylesheet_path)}"


def generate_theme_js() -> str:
    return """
/**
 * @file theme.js
 * @description 在日间、夜间和跟随设备三种主题偏好间循环切换。
 */
(function(){
  const themeStorageKey = 'color-theme';
  const themePreferences = ['system', 'light', 'dark'];
  const themeLabels = {
    system: '设备',
    light: '日间',
    dark: '夜间'
  };
  const systemThemeQuery = window.matchMedia('(prefers-color-scheme: dark)');

  function normalizeThemePreference(themePreference){
    return themePreferences.includes(themePreference) ? themePreference : 'system';
  }

  function readThemePreference(){
    try {
      return normalizeThemePreference(window.localStorage.getItem(themeStorageKey));
    } catch (error) {
      return 'system';
    }
  }

  function resolveTheme(themePreference){
    if(themePreference === 'system'){
      return systemThemeQuery.matches ? 'dark' : 'light';
    }
    return themePreference;
  }

  function updateThemeToggle(themePreference){
    const themeLabel = themeLabels[themePreference];
    document.querySelectorAll('[data-theme-toggle]').forEach((themeToggleEl) => {
      themeToggleEl.dataset.themePreference = themePreference;
      themeToggleEl.setAttribute('aria-label', `当前主题：${themeLabel}，点击切换主题`);
      themeToggleEl.setAttribute('title', `当前主题：${themeLabel}`);
      const themeToggleLabelEl = themeToggleEl.querySelector('[data-theme-toggle-label]');
      if(themeToggleLabelEl){
        themeToggleLabelEl.textContent = themeLabel;
      }
    });
  }

  function applyThemePreference(themePreference, shouldPersist){
    const normalizedThemePreference = normalizeThemePreference(themePreference);
    const resolvedTheme = resolveTheme(normalizedThemePreference);
    document.documentElement.dataset.theme = resolvedTheme;
    document.documentElement.dataset.themePreference = normalizedThemePreference;
    document.documentElement.style.colorScheme = resolvedTheme;
    updateThemeToggle(normalizedThemePreference);

    if(shouldPersist){
      try {
        window.localStorage.setItem(themeStorageKey, normalizedThemePreference);
      } catch (error) {
        console.warn('无法保存主题偏好', error);
      }
    }
  }

  function cycleThemePreference(){
    const currentThemePreference = normalizeThemePreference(
      document.documentElement.dataset.themePreference || readThemePreference()
    );
    const currentThemeIndex = themePreferences.indexOf(currentThemePreference);
    const nextThemePreference = themePreferences[(currentThemeIndex + 1) % themePreferences.length];
    applyThemePreference(nextThemePreference, true);
  }

  document.addEventListener('click', (event) => {
    const themeToggleEl = event.target.closest('[data-theme-toggle]');
    if(themeToggleEl){
      cycleThemePreference();
    }
  });

  systemThemeQuery.addEventListener('change', () => {
    if(readThemePreference() === 'system'){
      applyThemePreference('system', false);
    }
  });

  window.addEventListener('storage', (event) => {
    if(event.key === themeStorageKey){
      applyThemePreference(event.newValue || 'system', false);
    }
  });

  applyThemePreference(readThemePreference(), false);
})();
""".strip()


def generate_media_js() -> str:
    return """
/**
 * @file media.js
 * @description 通用论文图片灯箱：支持点击放大、滚轮缩放、拖拽查看和键盘关闭。
 */
(function(){
  let lightboxEl = null;
  let imageEl = null;
  let captionEl = null;
  let scaleLabelEl = null;
  let closeButtonEl = null;
  let imageScale = 1;
  let imageOffsetX = 0;
  let imageOffsetY = 0;
  let dragStartX = 0;
  let dragStartY = 0;
  let dragOriginX = 0;
  let dragOriginY = 0;
  let activePointerId = null;
  let returnFocusEl = null;

  function clampScale(value){
    return Math.min(4, Math.max(1, value));
  }

  function renderTransform(){
    if(!imageEl || !scaleLabelEl){
      return;
    }

    imageEl.style.transform = `translate3d(${imageOffsetX}px, ${imageOffsetY}px, 0) scale(${imageScale})`;
    imageEl.classList.toggle('is-zoomed', imageScale > 1);
    scaleLabelEl.textContent = `${Math.round(imageScale * 100)}%`;
  }

  function setScale(nextScale){
    const normalizedScale = clampScale(nextScale);
    if(normalizedScale === 1){
      imageOffsetX = 0;
      imageOffsetY = 0;
    }
    imageScale = normalizedScale;
    renderTransform();
  }

  function resetImagePosition(){
    imageScale = 1;
    imageOffsetX = 0;
    imageOffsetY = 0;
    renderTransform();
  }

  function ensureLightbox(){
    if(lightboxEl){
      return;
    }

    lightboxEl = document.createElement('div');
    lightboxEl.className = 'image-lightbox';
    lightboxEl.setAttribute('aria-hidden', 'true');
    lightboxEl.innerHTML = `
      <div class="image-lightbox-stage" data-image-lightbox-close>
        <img class="image-lightbox-image" alt="" draggable="false" />
      </div>
      <div class="image-lightbox-topbar">
        <p class="image-lightbox-caption"></p>
        <button class="image-lightbox-close" type="button" aria-label="关闭图片预览">×</button>
      </div>
      <div class="image-lightbox-controls" aria-label="图片缩放控制">
        <button type="button" data-image-zoom-out aria-label="缩小图片">−</button>
        <button class="image-lightbox-scale" type="button" data-image-zoom-reset aria-label="恢复原始缩放">100%</button>
        <button type="button" data-image-zoom-in aria-label="放大图片">+</button>
      </div>
    `;

    document.body.appendChild(lightboxEl);
    imageEl = lightboxEl.querySelector('.image-lightbox-image');
    captionEl = lightboxEl.querySelector('.image-lightbox-caption');
    scaleLabelEl = lightboxEl.querySelector('.image-lightbox-scale');
    closeButtonEl = lightboxEl.querySelector('.image-lightbox-close');
    const stageEl = lightboxEl.querySelector('.image-lightbox-stage');

    lightboxEl.addEventListener('click', (event) => {
      if(event.target.closest('[data-image-lightbox-close]') && event.target !== imageEl){
        close();
      }
    });

    closeButtonEl.addEventListener('click', close);
    lightboxEl.querySelector('[data-image-zoom-out]').addEventListener('click', () => setScale(imageScale - 0.5));
    lightboxEl.querySelector('[data-image-zoom-in]').addEventListener('click', () => setScale(imageScale + 0.5));
    lightboxEl.querySelector('[data-image-zoom-reset]').addEventListener('click', resetImagePosition);

    stageEl.addEventListener('wheel', (event) => {
      if(!lightboxEl.classList.contains('is-open')){
        return;
      }
      event.preventDefault();
      setScale(imageScale + (event.deltaY < 0 ? 0.25 : -0.25));
    }, { passive: false });

    imageEl.addEventListener('dblclick', () => {
      setScale(imageScale > 1 ? 1 : 2);
    });

    imageEl.addEventListener('pointerdown', (event) => {
      if(imageScale <= 1){
        return;
      }
      activePointerId = event.pointerId;
      dragStartX = event.clientX;
      dragStartY = event.clientY;
      dragOriginX = imageOffsetX;
      dragOriginY = imageOffsetY;
      imageEl.setPointerCapture(event.pointerId);
      imageEl.classList.add('is-dragging');
    });

    imageEl.addEventListener('pointermove', (event) => {
      if(activePointerId !== event.pointerId){
        return;
      }
      imageOffsetX = dragOriginX + event.clientX - dragStartX;
      imageOffsetY = dragOriginY + event.clientY - dragStartY;
      renderTransform();
    });

    function stopDragging(event){
      if(activePointerId !== event.pointerId){
        return;
      }
      activePointerId = null;
      imageEl.classList.remove('is-dragging');
    }

    imageEl.addEventListener('pointerup', stopDragging);
    imageEl.addEventListener('pointercancel', stopDragging);

    window.addEventListener('keydown', (event) => {
      if(!lightboxEl.classList.contains('is-open')){
        return;
      }
      if(event.key === 'Escape'){
        event.preventDefault();
        close();
      }
      if(event.key === '+' || event.key === '='){
        setScale(imageScale + 0.5);
      }
      if(event.key === '-'){
        setScale(imageScale - 0.5);
      }
    });
  }

  function open(options){
    if(!options || !options.src){
      return;
    }

    ensureLightbox();
    returnFocusEl = options.returnFocus || document.activeElement;
    imageEl.src = options.src;
    imageEl.alt = options.alt || '论文图片放大预览';
    captionEl.textContent = options.caption || options.alt || '';
    captionEl.classList.toggle('hidden', !captionEl.textContent);
    resetImagePosition();
    lightboxEl.classList.add('is-open');
    lightboxEl.setAttribute('aria-hidden', 'false');
    document.body.classList.add('has-image-lightbox');
    window.requestAnimationFrame(() => closeButtonEl.focus());
  }

  function close(){
    if(!lightboxEl || !lightboxEl.classList.contains('is-open')){
      return;
    }

    lightboxEl.classList.remove('is-open');
    lightboxEl.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('has-image-lightbox');
    imageEl.removeAttribute('src');
    if(returnFocusEl && typeof returnFocusEl.focus === 'function'){
      returnFocusEl.focus({ preventScroll: true });
    }
    returnFocusEl = null;
  }

  function isOpen(){
    return Boolean(lightboxEl && lightboxEl.classList.contains('is-open'));
  }

  window.PaperImageViewer = { open, close, isOpen };
})();
""".strip()


def generate_app_js() -> str:
    return """
/**
 * @file app.js
 * @description 首页逻辑：加载 data.json，渲染信息流卡片与搜索。
 */
(function(){
  /** @type {Array<{date:string,title:string,link:string,arxiv_id:string,detail_path:string,cover_path:string,paper_image_path:string,paper_image_full_path:string,preview_text:string,research_unit:string,hook_text:string,key_points:string[],reading_minutes:number,section_count:number,cover_theme:Record<string,string>}>} */
  let DATA = [];

  const $ = (selector) => document.querySelector(selector);
  const statusEl = $('#status');
  const groupsEl = $('#groups');
  const searchEl = $('#search');
  const paperCountEl = $('#paper-count');
  const homeScrollKey = 'home-scroll:index';
  const paperModalQueryKey = 'paper';
  let restoredScroll = false;
  let paperModalEl = null;
  let paperModalFrameEl = null;
  let paperModalTitleEl = null;
  let paperModalOpenLinkEl = null;
  let paperModalLoaderEl = null;
  let modalReturnFocusEl = null;
  let modalCleanupTimerId = null;
  let modalSessionId = 0;

  function getPaperIdentifier(item){
    return item.arxiv_id || item.detail_path;
  }

  function getStandalonePaperURL(detailPath){
    return new URL(detailPath, window.location.href).href;
  }

  function getEmbeddedPaperURL(detailPath){
    const embeddedURL = new URL(detailPath, window.location.href);
    embeddedURL.searchParams.set('embed', '1');
    return embeddedURL.href;
  }

  function replacePaperModalFrameLocation(frameURL){
    if(!paperModalFrameEl){
      return;
    }

    try {
      if(paperModalFrameEl.contentWindow){
        paperModalFrameEl.contentWindow.location.replace(frameURL);
        return;
      }
    } catch (error) {
      console.warn('无法替换论文浮窗地址，改用 iframe src 导航', error);
    }

    paperModalFrameEl.src = frameURL;
  }

  function ensurePaperModal(){
    if(paperModalEl){
      return;
    }

    paperModalEl = document.createElement('div');
    paperModalEl.className = 'paper-modal';
    paperModalEl.setAttribute('aria-hidden', 'true');
    paperModalEl.innerHTML = `
      <div class="paper-modal-backdrop" data-paper-modal-close></div>
      <section class="paper-modal-panel" role="dialog" aria-modal="true" aria-labelledby="paper-modal-title">
        <header class="paper-modal-toolbar">
          <div class="paper-modal-heading">
            <span class="paper-modal-kicker">论文阅读</span>
            <span id="paper-modal-title" class="paper-modal-title"></span>
          </div>
          <div class="paper-modal-actions">
            <a class="paper-modal-open-link" href="#" target="_blank" rel="noopener noreferrer">新页面打开 ↗</a>
            <button class="paper-modal-close" type="button" aria-label="关闭论文浮窗">×</button>
          </div>
        </header>
        <div class="paper-modal-content">
          <div class="paper-modal-loader" aria-hidden="true">
            <span class="paper-modal-spinner"></span>
            <span>正在打开论文阅读卡</span>
          </div>
          <iframe class="paper-modal-frame" title="论文详情" loading="eager"></iframe>
        </div>
      </section>
    `;

    document.body.appendChild(paperModalEl);
    paperModalFrameEl = paperModalEl.querySelector('.paper-modal-frame');
    paperModalTitleEl = paperModalEl.querySelector('.paper-modal-title');
    paperModalOpenLinkEl = paperModalEl.querySelector('.paper-modal-open-link');
    paperModalLoaderEl = paperModalEl.querySelector('.paper-modal-loader');

    paperModalEl.querySelector('[data-paper-modal-close]').addEventListener('click', requestClosePaperModal);
    paperModalEl.querySelector('.paper-modal-close').addEventListener('click', requestClosePaperModal);
    paperModalFrameEl.addEventListener('load', () => {
      connectPaperModalImageZoom();
      paperModalLoaderEl.classList.add('hidden');
      paperModalFrameEl.classList.add('is-ready');
    });
  }

  function connectPaperModalImageZoom(){
    if(!paperModalFrameEl || !window.PaperImageViewer){
      return;
    }

    let frameDocument = null;
    try {
      frameDocument = paperModalFrameEl.contentDocument;
    } catch (error) {
      console.warn('无法访问论文浮窗内容，保留嵌入页自身的图片预览逻辑', error);
      return;
    }

    if(!frameDocument){
      return;
    }

    frameDocument.querySelectorAll('.paper-figure-image').forEach((imageEl) => {
      if(imageEl.dataset.parentZoomBound === 'true'){
        return;
      }
      imageEl.dataset.parentZoomBound = 'true';

      const openImage = (event) => {
        event.preventDefault();
        event.stopPropagation();
        const figureEl = imageEl.closest('.paper-figure-card');
        const captionEl = figureEl ? figureEl.querySelector('.paper-figure-caption') : null;
        window.PaperImageViewer.open({
          src: imageEl.currentSrc || imageEl.src,
          alt: imageEl.alt || '论文图片',
          caption: captionEl ? captionEl.textContent.trim() : imageEl.alt || ''
        });
      };

      imageEl.addEventListener('click', openImage, true);
      imageEl.addEventListener('keydown', (event) => {
        if(event.key === 'Enter' || event.key === ' '){
          openImage(event);
        }
      }, true);
    });
  }

  function openPaperModal(item, options){
    if(!item){
      return;
    }

    const settings = options || {};
    ensurePaperModal();
    modalSessionId += 1;
    if(modalCleanupTimerId !== null){
      window.clearTimeout(modalCleanupTimerId);
      modalCleanupTimerId = null;
    }
    modalReturnFocusEl = settings.returnFocus || modalReturnFocusEl || document.activeElement;
    paperModalTitleEl.textContent = item.title || '论文详情';
    paperModalOpenLinkEl.href = getStandalonePaperURL(item.detail_path);
    paperModalFrameEl.title = `论文详情：${item.title || ''}`;
    paperModalFrameEl.classList.remove('is-ready');
    paperModalLoaderEl.classList.remove('hidden');
    replacePaperModalFrameLocation(getEmbeddedPaperURL(item.detail_path));
    paperModalEl.classList.add('is-open');
    paperModalEl.setAttribute('aria-hidden', 'false');
    document.body.classList.add('has-paper-modal');

    if(settings.updateHistory){
      const modalURL = new URL(window.location.href);
      const paperIdentifier = getPaperIdentifier(item);
      const currentHistoryState = window.history.state && typeof window.history.state === 'object'
        ? window.history.state
        : {};
      modalURL.searchParams.set(paperModalQueryKey, paperIdentifier);
      window.history.pushState(
        { ...currentHistoryState, paperModal: paperIdentifier },
        '',
        modalURL
      );
    }

    window.requestAnimationFrame(() => {
      paperModalEl.querySelector('.paper-modal-close').focus();
    });
  }

  function hidePaperModal(){
    if(!paperModalEl || !paperModalEl.classList.contains('is-open')){
      return;
    }

    const closingSessionId = modalSessionId;
    paperModalEl.classList.remove('is-open');
    paperModalEl.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('has-paper-modal');
    if(modalCleanupTimerId !== null){
      window.clearTimeout(modalCleanupTimerId);
    }
    modalCleanupTimerId = window.setTimeout(() => {
      modalCleanupTimerId = null;
      const modalWasNotReopened = modalSessionId === closingSessionId;
      if(modalWasNotReopened && !paperModalEl.classList.contains('is-open')){
        replacePaperModalFrameLocation('about:blank');
      }
    }, 220);

    if(modalReturnFocusEl && typeof modalReturnFocusEl.focus === 'function'){
      modalReturnFocusEl.focus({ preventScroll: true });
    }
    modalReturnFocusEl = null;
  }

  function requestClosePaperModal(){
    if(window.PaperImageViewer && window.PaperImageViewer.isOpen()){
      window.PaperImageViewer.close();
      return;
    }

    const modalURL = new URL(window.location.href);
    const paperIdentifier = modalURL.searchParams.get(paperModalQueryKey);
    const historyPaperIdentifier = window.history.state && typeof window.history.state === 'object'
      ? window.history.state.paperModal
      : null;
    const canReturnToPreviousHistoryEntry = Boolean(
      paperIdentifier && historyPaperIdentifier === paperIdentifier
    );

    hidePaperModal();

    if(canReturnToPreviousHistoryEntry){
      window.history.back();
      return;
    }

    modalURL.searchParams.delete(paperModalQueryKey);
    const replacementHistoryState = window.history.state && typeof window.history.state === 'object'
      ? { ...window.history.state }
      : null;
    if(replacementHistoryState){
      delete replacementHistoryState.paperModal;
    }
    window.history.replaceState(replacementHistoryState, '', modalURL);
  }

  function openPaperModalFromURL(){
    const paperIdentifier = new URL(window.location.href).searchParams.get(paperModalQueryKey);
    if(!paperIdentifier){
      hidePaperModal();
      return;
    }

    const item = DATA.find((candidate) => getPaperIdentifier(candidate) === paperIdentifier);
    if(item){
      openPaperModal(item, { updateHistory: false });
    }
  }

  function openPaperImage(item, imageEl){
    if(!window.PaperImageViewer){
      return;
    }

    window.PaperImageViewer.open({
      src: item.paper_image_full_path || item.paper_image_path,
      alt: item.title || imageEl.alt,
      caption: item.title || '',
      returnFocus: imageEl
    });
  }

  function updatePaperCount(visibleCount){
    if(!paperCountEl){
      return;
    }

    const hasQuery = Boolean((searchEl.value || '').trim());
    paperCountEl.textContent = hasQuery
      ? `${visibleCount} / ${DATA.length} 篇`
      : `${DATA.length} 篇已收录`;
  }

  function applyCoverTheme(el, theme){
    if(!el || !theme){
      return;
    }

    const vars = {
      from: '--cover-from',
      to: '--cover-to',
      spot: '--cover-spot',
      ink: '--cover-ink',
      muted: '--cover-muted',
      chip: '--cover-chip',
      stroke: '--cover-stroke'
    };

    Object.entries(vars).forEach(([key, cssVar]) => {
      if(theme[key]){
        el.style.setProperty(cssVar, theme[key]);
      }
    });
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

  function buildSearchText(item){
    return [
      item.title || '',
      item.preview_text || '',
      item.research_unit || '',
      item.arxiv_id || '',
      item.hook_text || '',
      ...(item.key_points || [])
    ].join(' ').toLowerCase();
  }

  function filterItems(items, query){
    const raw = (query || '').trim().toLowerCase();
    if(!raw){
      return items;
    }
    const tokens = raw.split(/\\s+/).filter(Boolean);
    if(!tokens.length){
      return items;
    }
    return items.filter((item) => {
      const hay = buildSearchText(item).replace(/[-_]/g, '');
      return tokens.every((t) => hay.includes(t.replace(/[-_]/g, '')));
    });
  }

  function createFeedCard(item){
    const cardLink = document.createElement('a');
    cardLink.className = 'feed-card-link';
    cardLink.href = item.detail_path;
    cardLink.setAttribute('aria-label', `查看论文：${item.title}`);
    cardLink.setAttribute('aria-haspopup', 'dialog');
    cardLink.addEventListener('click', (event) => {
      const shouldUseNormalNavigation = event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey;
      if(shouldUseNormalNavigation){
        return;
      }
      event.preventDefault();
      openPaperModal(item, { updateHistory: true, returnFocus: cardLink });
    });

    const card = document.createElement('article');
    card.className = 'feed-card';

    const coverWrap = document.createElement('div');
    coverWrap.className = 'feed-card-cover';
    if(item.paper_image_path){
      const figure = document.createElement('figure');
      figure.className = 'feed-card-figure';

      const image = document.createElement('img');
      image.className = 'paper-figure-image';
      image.src = item.paper_image_path;
      image.alt = item.title || '论文首图';
      image.loading = 'lazy';
      image.dataset.zoomable = 'true';
      image.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();
        openPaperImage(item, image);
      });

      figure.appendChild(image);
      coverWrap.appendChild(figure);
    } else {
      const cover = document.createElement('div');
      cover.className = 'note-cover note-cover-feed note-cover-title-only';
      applyCoverTheme(cover, item.cover_theme);

      const mesh = document.createElement('div');
      mesh.className = 'note-cover-mesh';
      cover.appendChild(mesh);

      const titleShell = document.createElement('div');
      titleShell.className = 'note-cover-title-shell';

      const title = document.createElement('h3');
      title.className = 'note-cover-title';
      title.textContent = item.title;
      titleShell.appendChild(title);
      cover.appendChild(titleShell);
      coverWrap.appendChild(cover);
    }

    const cardBody = document.createElement('div');
    cardBody.className = 'feed-card-body';

    const meta = document.createElement('div');
    meta.className = 'feed-card-meta';

    if(item.research_unit){
      const org = document.createElement('span');
      org.className = 'feed-chip';
      org.textContent = item.research_unit;
      meta.appendChild(org);
    }

    if(item.arxiv_id){
      const id = document.createElement('span');
      id.className = 'feed-chip subtle';
      id.textContent = item.arxiv_id;
      meta.appendChild(id);
    }

    const bodyTitle = document.createElement('div');
    bodyTitle.className = 'feed-card-title';
    bodyTitle.textContent = item.title || '未命名论文';

    const preview = document.createElement('div');
    preview.className = 'feed-card-preview';
    preview.textContent = item.hook_text || item.preview_text || '摘要还在生成中';

    const footer = document.createElement('div');
    footer.className = 'feed-card-footer';

    const action = document.createElement('div');
    action.className = 'feed-card-action';
    action.textContent = '打开阅读卡';

    const stats = document.createElement('div');
    stats.className = 'feed-card-stats';
    stats.textContent = `${item.section_count || 0} 张卡 · ${item.reading_minutes || 1} 分钟`;

    footer.appendChild(action);
    footer.appendChild(stats);

    if(meta.childNodes.length){
      cardBody.appendChild(meta);
    }
    cardBody.appendChild(bodyTitle);
    cardBody.appendChild(preview);
    cardBody.appendChild(footer);

    card.appendChild(coverWrap);
    card.appendChild(cardBody);
    cardLink.appendChild(card);
    return cardLink;
  }

  const GROUPS_PER_BATCH = 3;
  let pendingDates = [];
  let pendingGrouped = new Map();
  let sentinelEl = null;
  let lazyObserver = null;

  function createGroupSection(date, items){
    const section = document.createElement('section');
    section.className = 'group';

    const heading = document.createElement('div');
    heading.className = 'group-heading';

    const h2 = document.createElement('h2');
    h2.textContent = date;

    const count = document.createElement('div');
    count.className = 'group-count';
    count.textContent = `${items.length} 篇`;

    const grid = document.createElement('div');
    grid.className = 'grid';

    items.forEach((item) => {
      grid.appendChild(createFeedCard(item));
    });

    heading.appendChild(h2);
    heading.appendChild(count);
    section.appendChild(heading);
    section.appendChild(grid);
    return section;
  }

  function removeSentinel(){
    if(sentinelEl && sentinelEl.parentNode){
      sentinelEl.parentNode.removeChild(sentinelEl);
    }
    sentinelEl = null;
  }

  function destroyLazyObserver(){
    if(lazyObserver){
      lazyObserver.disconnect();
      lazyObserver = null;
    }
    removeSentinel();
  }

  function loadNextBatch(){
    if(!pendingDates.length){
      removeSentinel();
      return;
    }

    const batch = pendingDates.splice(0, GROUPS_PER_BATCH);
    removeSentinel();

    batch.forEach((date) => {
      groupsEl.appendChild(createGroupSection(date, pendingGrouped.get(date)));
    });

    if(pendingDates.length){
      sentinelEl = document.createElement('div');
      sentinelEl.className = 'lazy-sentinel';
      sentinelEl.setAttribute('aria-hidden', 'true');
      groupsEl.appendChild(sentinelEl);
      if(lazyObserver){
        lazyObserver.observe(sentinelEl);
      }
    }
  }

  function renderGroups(items){
    destroyLazyObserver();
    groupsEl.innerHTML = '';

    if(!items.length){
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

    pendingGrouped = grouped;
    pendingDates = dates.slice(GROUPS_PER_BATCH);

    dates.slice(0, GROUPS_PER_BATCH).forEach((date) => {
      groupsEl.appendChild(createGroupSection(date, grouped.get(date)));
    });

    if(pendingDates.length){
      lazyObserver = new IntersectionObserver((entries) => {
        if(entries.some((e) => e.isIntersecting)){
          loadNextBatch();
        }
      }, { rootMargin: '400px' });

      sentinelEl = document.createElement('div');
      sentinelEl.className = 'lazy-sentinel';
      sentinelEl.setAttribute('aria-hidden', 'true');
      groupsEl.appendChild(sentinelEl);
      lazyObserver.observe(sentinelEl);
    }
  }

  function sync(){
    const items = filterItems(DATA, searchEl.value);
    updatePaperCount(items.length);

    if(!DATA.length){
      renderGroups([]);
      renderStatus('empty', '还没有论文卡片', '当前还没有可展示的数据，等抓取和摘要生成完成后，这里会自动出现。');
      return;
    }

    if(!items.length){
      renderGroups([]);
      renderStatus(
        'empty',
        '没有找到匹配卡片',
        `换个关键词试试，当前一共收录了 ${DATA.length} 篇论文。`,
        {
          label: '清空搜索',
          onClick: () => {
            searchEl.value = '';
            syncSearchURL();
            sync();
            searchEl.focus();
          }
        }
      );
      return;
    }

    clearStatus();
    renderGroups(items);
    restoreScroll();
  }

  function syncSearchURL(){
    const q = (searchEl.value || '').trim();
    const url = new URL(window.location);
    if(q){
      url.searchParams.set('q', q);
    } else {
      url.searchParams.delete('q');
    }
    window.history.replaceState(null, '', url);
  }

  searchEl.addEventListener('input', () => {
    syncSearchURL();
    sync();
  });

  function restoreScroll(){
    if(restoredScroll || window.location.hash){
      return;
    }

    try{
      const saved = window.localStorage.getItem(homeScrollKey);
      if(saved === null){
        restoredScroll = true;
        return;
      }

      const scrollY = Number(saved);
      restoredScroll = true;
      if(!Number.isFinite(scrollY) || scrollY <= 0){
        return;
      }

      while(pendingDates.length && document.documentElement.scrollHeight < scrollY + window.innerHeight){
        loadNextBatch();
      }

      window.requestAnimationFrame(() => {
        window.scrollTo(0, scrollY);
      });
    } catch (error) {
      restoredScroll = true;
      console.warn('恢复首页滚动进度失败', error);
    }
  }

  function saveScroll(){
    try{
      window.localStorage.setItem(homeScrollKey, String(window.scrollY || 0));
    } catch (error) {
      console.warn('保存首页滚动进度失败', error);
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

  window.addEventListener('popstate', openPaperModalFromURL);

  window.addEventListener('message', (event) => {
    if(event.origin !== window.location.origin || !paperModalFrameEl || event.source !== paperModalFrameEl.contentWindow){
      return;
    }

    const message = event.data || {};
    if(message.type === 'paper-modal-close'){
      requestClosePaperModal();
      return;
    }

    if(message.type === 'paper-modal-ready'){
      if(message.title){
        paperModalTitleEl.textContent = message.title;
      }
      if(message.url){
        const standaloneURL = new URL(message.url, window.location.href);
        standaloneURL.searchParams.delete('embed');
        paperModalOpenLinkEl.href = standaloneURL.href;
      }
      return;
    }

    if(message.type === 'paper-image-open' && window.PaperImageViewer){
      window.PaperImageViewer.open({
        src: message.src,
        alt: message.alt || '论文图片',
        caption: message.caption || message.alt || ''
      });
    }
  });

  window.addEventListener('keydown', (event) => {
    if(event.defaultPrevented || event.key !== 'Escape'){
      return;
    }
    if(paperModalEl && paperModalEl.classList.contains('is-open')){
      event.preventDefault();
      requestClosePaperModal();
    }
  });

  async function loadData(){
    renderStatus('loading', '正在加载论文卡片', '页面正在读取静态数据并搭建阅读流，你可以稍后直接开始搜索。');

    try{
      const response = await fetch('assets/data.json');
      if(!response.ok){
        throw new Error(`HTTP ${response.status}`);
      }

      DATA = await response.json();
      sync();
      openPaperModalFromURL();
    } catch (error) {
      console.error(error);
      renderGroups([]);
      renderStatus(
        'error',
        '论文卡片加载失败',
        '无法读取 data.json。你可以刷新页面重试，或者重新运行构建脚本。',
        { label: '重新加载', onClick: loadData }
      );
    }
  }

  const initialQuery = new URL(window.location).searchParams.get('q') || '';
  if(initialQuery){
    searchEl.value = initialQuery;
  }

  loadData();
})();
""".strip()


def generate_paper_js() -> str:
    return """
/**
 * @file paper.js
 * @description 论文详情页逻辑：构建目录、标记当前阅读卡，并按 arXiv id 记录滚动进度。
 */
(function(){
  const $ = (selector) => document.querySelector(selector);
  const detailBody = $('#detail-body');
  const detailToc = $('#detail-toc');
  const detailTocNav = $('#detail-toc-nav');
  const paperId = document.body.dataset.paperId || '';
  const isEmbedded = window.parent !== window && new URL(window.location.href).searchParams.get('embed') === '1';

  function getImagePayload(imageEl){
    const figureEl = imageEl.closest('.paper-figure-card');
    const captionEl = figureEl ? figureEl.querySelector('.paper-figure-caption') : null;
    return {
      src: imageEl.currentSrc || imageEl.src,
      alt: imageEl.alt || '论文图片',
      caption: captionEl ? captionEl.textContent.trim() : imageEl.alt || ''
    };
  }

  function openPaperImage(imageEl){
    const payload = getImagePayload(imageEl);
    if(isEmbedded){
      try {
        if(window.parent.PaperImageViewer){
          window.parent.PaperImageViewer.open(payload);
          return;
        }
      } catch (error) {
        console.warn('无法直接调用父页面图片预览，改用消息转发', error);
      }
      window.parent.postMessage({ type: 'paper-image-open', ...payload }, window.location.origin);
      return;
    }

    if(window.PaperImageViewer){
      window.PaperImageViewer.open({ ...payload, returnFocus: imageEl });
    }
  }

  window.openPaperFigureImage = openPaperImage;

  function initializeImageZoom(){
    document.querySelectorAll('.paper-figure-image').forEach((imageEl) => {
      imageEl.dataset.zoomable = 'true';
      imageEl.tabIndex = 0;
      imageEl.setAttribute('role', 'button');
      imageEl.setAttribute('aria-label', `放大查看：${imageEl.alt || '论文图片'}`);
      imageEl.addEventListener('keydown', (event) => {
        if(event.key === 'Enter' || event.key === ' '){
          event.preventDefault();
          openPaperImage(imageEl);
        }
      });
    });
  }

  function initializeEmbeddedMode(){
    if(!isEmbedded){
      return;
    }

    document.body.classList.add('embedded-detail');
    const backLinkEl = document.querySelector('.back-link');
    if(backLinkEl){
      backLinkEl.addEventListener('click', (event) => {
        event.preventDefault();
        window.parent.postMessage({ type: 'paper-modal-close' }, window.location.origin);
      });
    }

    document.querySelectorAll('.paper-nav-link').forEach((linkEl) => {
      linkEl.addEventListener('click', (event) => {
        event.preventDefault();
        const targetURL = new URL(linkEl.href, window.location.href);
        targetURL.searchParams.set('embed', '1');
        window.location.href = targetURL.href;
      });
    });

    const standaloneURL = new URL(window.location.href);
    standaloneURL.searchParams.delete('embed');
    window.parent.postMessage({
      type: 'paper-modal-ready',
      title: document.querySelector('.detail-page-title')?.textContent || document.title,
      url: standaloneURL.href
    }, window.location.origin);

    window.addEventListener('keydown', (event) => {
      if(event.defaultPrevented || event.key !== 'Escape'){
        return;
      }
      event.preventDefault();
      window.parent.postMessage({ type: 'paper-modal-close' }, window.location.origin);
    });
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
    if(!detailBody || !detailToc || !detailTocNav){
      return;
    }

    detailTocNav.innerHTML = '';
    const headings = Array.from(detailBody.querySelectorAll('.reading-card-section h2'));

    if(!headings.length){
      detailToc.classList.add('hidden');
      return;
    }

    const links = new Map();

    headings.forEach((heading, index) => {
      if(!heading.id){
        heading.id = slugifyHeading(heading.textContent, index + 1);
      }

      const link = document.createElement('a');
      link.className = 'detail-toc-link';
      link.href = `#${heading.id}`;
      link.textContent = heading.textContent || `章节 ${index + 1}`;
      detailTocNav.appendChild(link);
      links.set(heading.id, link);
    });

    if('IntersectionObserver' in window){
      const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          const link = links.get(entry.target.id);
          if(link && entry.isIntersecting){
            detailTocNav.querySelectorAll('.detail-toc-link').forEach((item) => item.classList.remove('is-active'));
            link.classList.add('is-active');
          }
        });
      }, {
        rootMargin: '-18% 0px -58% 0px',
        threshold: 0
      });

      headings.forEach((heading) => observer.observe(heading));
    }

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

  initializeEmbeddedMode();
  initializeImageZoom();
  buildDetailToc();
  restoreScroll();
})();
""".strip()


THUMB_DIR = IMAGE_DIR / "thumbs"
THUMB_MAX_WIDTH = 600
WEBP_QUALITY = 82
WEBP_MAX_DIMENSION = 8192
EXTREME_PORTRAIT_RATIO = 3
CARD_THUMB_ASPECT_RATIO = 16 / 10


def resize_image_for_webp(image: Image.Image) -> tuple[Image.Image, bool]:
    """将超出 WebP 安全尺寸的图片等比例缩小。"""
    largest_dimension = max(image.width, image.height)
    if largest_dimension <= WEBP_MAX_DIMENSION:
        return image, False

    resize_ratio = WEBP_MAX_DIMENSION / largest_dimension
    resized_dimensions = (
        max(1, round(image.width * resize_ratio)),
        max(1, round(image.height * resize_ratio)),
    )
    resized_image = image.resize(resized_dimensions, Image.LANCZOS)
    return resized_image, True


def create_paper_thumbnail(image: Image.Image) -> Image.Image:
    """生成列表缩略图，并避免极端纵向图片产生超长资源。"""
    thumbnail_source = image
    is_extreme_portrait = image.height > image.width * EXTREME_PORTRAIT_RATIO
    if is_extreme_portrait:
        crop_height = max(1, round(image.width / CARD_THUMB_ASPECT_RATIO))
        crop_top = max(0, (image.height - crop_height) // 2)
        thumbnail_source = image.crop(
            (0, crop_top, image.width, min(image.height, crop_top + crop_height))
        )

    if thumbnail_source.width <= THUMB_MAX_WIDTH:
        return thumbnail_source

    resize_ratio = THUMB_MAX_WIDTH / thumbnail_source.width
    thumbnail_dimensions = (
        THUMB_MAX_WIDTH,
        max(1, round(thumbnail_source.height * resize_ratio)),
    )
    return thumbnail_source.resize(thumbnail_dimensions, Image.LANCZOS)


def optimize_paper_images() -> Dict[str, str]:
    """将 paper-images/ 下的 PNG/JPG 转为 WebP，同时生成缩略图。

    返回 {原始相对路径: 缩略图相对路径} 的映射。
    跳过已经是 WebP 且缩略图已存在的文件。
    """
    if not HAS_PIL:
        print("警告: 未安装 Pillow，跳过图片优化")
        return {}

    if not IMAGE_DIR.exists():
        return {}

    THUMB_DIR.mkdir(parents=True, exist_ok=True)

    thumb_map: Dict[str, str] = {}
    converted = 0
    resized = 0
    skipped = 0

    for src_path in sorted(IMAGE_DIR.iterdir()):
        if src_path.is_dir():
            continue
        if src_path.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
            continue

        stem = src_path.stem
        webp_path = src_path.with_suffix(".webp")
        thumb_path = THUMB_DIR / f"{stem}.webp"

        # 原图的最终相对路径（相对于 site/）
        webp_rel = f"assets/paper-images/{stem}.webp"
        thumb_rel = f"assets/paper-images/thumbs/{stem}.webp"

        # 如果 WebP 全尺寸和缩略图都已存在，跳过
        if webp_path.exists() and thumb_path.exists() and src_path.suffix.lower() == ".webp":
            thumb_map[webp_rel] = thumb_rel
            skipped += 1
            continue

        try:
            img = Image.open(src_path)
            img = img.convert("RGB") if img.mode in ("RGBA", "P", "LA") else img
            img, was_resized = resize_image_for_webp(img)
            if was_resized:
                resized += 1
                print(
                    f"图片缩放: {src_path.name} -> "
                    f"{img.width}x{img.height}（最长边限制 {WEBP_MAX_DIMENSION}px）"
                )

            # 保存 WebP 全尺寸
            if src_path.suffix.lower() != ".webp":
                img.save(webp_path, "WEBP", quality=WEBP_QUALITY)
            elif not webp_path.exists():
                img.save(webp_path, "WEBP", quality=WEBP_QUALITY)

            # 极端纵向图片使用居中卡片预览，完整内容仍保留在全尺寸 WebP 中。
            thumb_img = create_paper_thumbnail(img)
            thumb_img.save(thumb_path, "WEBP", quality=WEBP_QUALITY)

            # 只有全尺寸和缩略图都成功后，才删除旧格式原图
            if src_path.suffix.lower() != ".webp" and src_path.exists():
                src_path.unlink()

            thumb_map[webp_rel] = thumb_rel
            converted += 1
        except Exception as exc:
            print(f"警告: 图片优化失败 {src_path.name}: {exc}")
            # 保留原文件，不生成映射
            continue

    print(f"图片优化: 转换 {converted} 张, 缩放 {resized} 张, 跳过 {skipped} 张")
    return thumb_map


def main() -> int:
    if not INPUT_MD.exists():
        print(f"未找到 {INPUT_MD}", file=sys.stderr)
        return 1

    # 优化图片：转 WebP + 生成缩略图
    thumb_map = optimize_paper_images()

    records = parse_markdown_table(read_text(INPUT_MD))
    paper_image_manifest = load_paper_image_manifest()

    # 更新 manifest 中的路径（PNG/JPG -> WebP）
    if thumb_map:
        for arxiv_id, entry in paper_image_manifest.items():
            if not isinstance(entry, dict):
                continue
            old_path = entry.get("path", "")
            if not isinstance(old_path, str):
                continue
            new_path = re.sub(r"\.(png|jpe?g)$", ".webp", old_path, flags=re.IGNORECASE)
            if new_path != old_path and (SITE_DIR / new_path).exists():
                entry["path"] = new_path

        write_text(PAPER_IMAGES_MANIFEST, json.dumps(paper_image_manifest, ensure_ascii=False, indent=2))

    site_records = build_site_records(records, paper_image_manifest)

    # 为首页列表数据使用缩略图路径
    list_data = build_list_data(site_records, thumb_map)

    shutil.rmtree(PAPERS_DIR, ignore_errors=True)
    shutil.rmtree(COVERS_DIR, ignore_errors=True)

    write_text(SITE_DIR / "index.html", generate_index_html())
    write_text(ASSETS_DIR / "style.css", generate_style_css())
    write_text(ASSETS_DIR / "theme.js", generate_theme_js())
    write_text(ASSETS_DIR / "media.js", generate_media_js())
    write_text(ASSETS_DIR / "app.js", generate_app_js())
    write_text(ASSETS_DIR / "paper.js", generate_paper_js())
    write_text(ASSETS_DIR / "data.json", json.dumps(list_data, ensure_ascii=False, indent=2))

    for idx, record in enumerate(site_records):
      prev_rec = site_records[idx - 1] if idx > 0 else None
      next_rec = site_records[idx + 1] if idx < len(site_records) - 1 else None
      write_text(PAPERS_DIR / str(record["page_dir"]) / "index.html", generate_paper_html(record, prev_rec, next_rec))
      write_text(COVERS_DIR / str(record["page_dir"]) / "index.html", generate_cover_html(record))

    print(f"生成完成：{SITE_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
