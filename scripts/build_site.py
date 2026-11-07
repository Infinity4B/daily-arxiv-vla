#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
生成静态站点：
1) 解析项目根目录下的 `papers.md` 表格（列：日期/标题/链接/简要总结）。
2) 从第四列提取 <details> ... </details> 中的实际内容。
3) 对内容进行“自动补换行”修复。
4) 生成首页信息流（data.json + 按需加载的 search-index.json）与每篇论文的详情页。
5) 把 scripts/web/ 下的前端源码复制到 site/assets/，并为资源地址附加内容哈希以便缓存失效。
"""

from __future__ import annotations

import hashlib
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
# 封面卡页面已下线，保留路径仅用于清理历史产物
LEGACY_COVERS_DIR = SITE_DIR / "covers"
WEB_SRC_DIR = PROJECT_ROOT / "scripts" / "web"
# site.js 由这些模块按顺序拼接（每个文件都是独立 IIFE），每页只需加载 site.js + 页面脚本
SITE_SCRIPT_MODULES = ["theme.js", "analytics.js", "read-state.js", "media.js"]
PAGE_SCRIPTS = ["app.js", "paper.js"]
# 合并进 site.js 之前单独输出的文件，构建时删除
OBSOLETE_ASSETS = ["theme.js", "analytics.js", "media.js"]
IMAGE_DIR = ASSETS_DIR / "paper-images"
PAPER_IMAGES_MANIFEST = ASSETS_DIR / "paper-images.json"
DEFAULT_ARXIV_QUERY = (
    'all:"VLA" OR all:"Vision-Language-Action" OR '
    'all:"World Action Model" OR all:"World-Action Model" OR '
    'all:"action world model"'
)
DEFAULT_ARXIV_KEYWORD_LABEL = "VLA / World Action Model"
# 全尺寸首图的外部地址前缀（指向仓库中的 site/ 目录，如 raw.githubusercontent.com）。
# 设置后页面从该地址加载全尺寸图，部署时可把全尺寸图排除在 Pages 产物之外，只保留缩略图。
PAPER_IMAGE_REMOTE_BASE = os.getenv("PAPER_IMAGE_REMOTE_BASE", "").strip().rstrip("/")

COVER_THEMES = [
    {
        "from": "#ef6c3f",
        "to": "#f6b13d",
        "spot": "#ffd59c",
        "ink": "#fff8ef",
    },
    {
        "from": "#d84f61",
        "to": "#f29c6b",
        "spot": "#ffd6c4",
        "ink": "#fff7f4",
    },
    {
        "from": "#177e89",
        "to": "#5ec2a8",
        "spot": "#c5f0de",
        "ink": "#f5fffb",
    },
    {
        "from": "#3f6ee8",
        "to": "#6fa7ff",
        "spot": "#d5e6ff",
        "ink": "#f7fbff",
    },
    {
        "from": "#6f4cc9",
        "to": "#c57be8",
        "spot": "#efd9ff",
        "ink": "#fdf7ff",
    },
    {
        "from": "#316b57",
        "to": "#8bb174",
        "spot": "#d9e7c7",
        "ink": "#fbfff6",
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


ALLOWED_INLINE_TAG_PATTERN = re.compile(
    r"&lt;(/?)(sup|sub|math|mi|mo|mn|msub|msup|mrow|mfrac)&gt;", re.IGNORECASE
)


def markdown_to_html(md: str) -> str:
    lines = md.splitlines()
    html_lines: List[str] = []

    def render_inline(text: str) -> str:
        # 先整体转义，避免摘要里的 `<think>`、`<ACT>` 之类的 token 被浏览器当成标签吞掉；
        # 再放行少量无属性的排版标签（上下标与简单 MathML）。
        text = escape(text, quote=False)
        text = ALLOWED_INLINE_TAG_PATTERN.sub(r"<\1\2>", text)
        text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
        text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(
            r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
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
    # 只去掉真实的 HTML 标签，保留 `<think>` 这类论文里的字面 token
    plain = re.sub(
        r"</?(?:br|p|div|span|details|summary|sup|sub|math|mi|mo|mn|msub|msup|mrow|mfrac)\b[^>]*>",
        " ",
        plain,
        flags=re.IGNORECASE,
    )
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


def resolve_full_image_src(relative_path: str, local_prefix: str = "") -> str:
    """返回全尺寸首图的引用地址：配置了外部前缀时用外部地址，否则用站内相对路径。"""
    if not relative_path:
        return ""
    if PAPER_IMAGE_REMOTE_BASE:
        return f"{PAPER_IMAGE_REMOTE_BASE}/{relative_path}"
    return f"{local_prefix}{relative_path}"


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
    return "; ".join(f"--cover-{key}: {value}" for key, value in theme.items())


def render_note_cover(record: Dict[str, object]) -> str:
    """没有论文首图时，用标题渐变块占位。"""
    return f"""
<div class="note-cover" style="{escape(theme_style(record["cover_theme"]), quote=True)}" aria-hidden="true">
  <p class="note-cover-title">{escape(str(record["title"]))}</p>
</div>
""".strip()


def render_article_figure(record: Dict[str, object], display_src: str, zoom_src: str, fallback_src: str) -> str:
    """文章首图：显示站内缩略图（快、可靠），点击放大时再加载全尺寸图（失败回退到缩略图）。"""
    if not display_src:
        return f'<figure class="article-figure">{render_note_cover(record)}</figure>'

    title = escape(str(record["title"]), quote=True)
    fallback_attr = f' data-zoom-fallback="{escape(fallback_src, quote=True)}"' if fallback_src else ""
    return f"""
<figure class="article-figure">
  <button class="article-figure-zoom" type="button" data-zoom-src="{escape(zoom_src, quote=True)}"{fallback_attr} aria-label="放大查看论文首图">
    <img src="{escape(display_src, quote=True)}" alt="{title} 论文首图" decoding="async" fetchpriority="high" />
    <span class="article-figure-hint" aria-hidden="true">点击放大</span>
  </button>
</figure>
""".strip()


def get_section_anchor(index: int) -> str:
    return f"section-{index}"


def render_article_sections(record: Dict[str, object]) -> str:
    """正文各节。首页阅读抽屉会抓取详情页并直接复用 .article-sections 内的这段 HTML。"""
    sections: List[Dict[str, str]] = record["sections"]  # type: ignore[assignment]
    return "\n".join(
        f"""
<section class="article-section" id="{get_section_anchor(index)}">
  <h2 class="article-section-title"><span class="article-section-index" aria-hidden="true">{index:02d}</span>{escape(section["title"])}</h2>
  <div class="prose">{section["html"]}</div>
</section>
""".strip()
        for index, section in enumerate(sections, start=1)
    )


def render_article_toc(record: Dict[str, object]) -> str:
    sections: List[Dict[str, str]] = record["sections"]  # type: ignore[assignment]
    if len(sections) < 2:
        return ""
    links = "\n".join(
        f'<a href="#{get_section_anchor(index)}"><span>{index:02d}</span>{escape(section["title"])}</a>'
        for index, section in enumerate(sections, start=1)
    )
    return f"""
<aside class="article-toc" aria-label="本文目录">
  <p class="article-toc-title">目录</p>
  <nav>{links}</nav>
</aside>
""".strip()


def build_site_records(
    records: List[Dict[str, str]],
    paper_image_manifest: Dict[str, Dict[str, object]],
    thumb_map: Dict[str, str],
) -> List[Dict[str, object]]:
    """thumb_map: {全尺寸图相对路径: 缩略图相对路径}，由 optimize_paper_images() 生成。"""
    built: List[Dict[str, object]] = []

    for record in records:
        summary_markdown = auto_add_linebreaks(record["details_raw"])
        sections = parse_markdown_sections(summary_markdown)
        preview_text = build_preview(sections)
        key_points = build_key_points(sections, preview_text)
        arxiv_id = normalize_arxiv_id(record["link"])
        page_dir = make_page_dir_name(arxiv_id, record["title"])
        paper_image_path = get_paper_image_path(paper_image_manifest, arxiv_id)

        built.append(
            {
                "date": record["date"],
                "title": record["title"],
                "link": record["link"],
                "arxiv_id": arxiv_id,
                "page_dir": page_dir,
                "detail_path": f"papers/{page_dir}/",
                "paper_image_path": paper_image_path,
                "thumb_path": thumb_map.get(paper_image_path, ""),
                "translation_link": get_translation_link(record["link"]),
                "sections": sections,
                "preview_text": preview_text,
                "research_unit": extract_research_unit(sections),
                "key_points": key_points,
                "hook_text": build_hook_text(key_points, preview_text),
                "reading_minutes": estimate_reading_minutes(summary_markdown),
                "section_count": len(sections),
                "cover_theme": pick_cover_theme(arxiv_id or record["title"]),
            }
        )

    return built


def get_paper_identifier(record: Dict[str, object]) -> str:
    """与前端 getPaperId 保持一致：优先 arXiv id，否则用详情页路径。"""
    return str(record["arxiv_id"] or record["detail_path"])


def build_list_data(records: List[Dict[str, object]]) -> List[Dict[str, object]]:
    """首页卡片数据：只保留渲染卡片所需字段，检索用的长文本拆到 search-index.json。"""
    list_data: List[Dict[str, object]] = []
    for record in records:
        image_path = str(record["paper_image_path"])
        item: Dict[str, object] = {
            "date": record["date"],
            "title": record["title"],
            "arxiv_id": record["arxiv_id"],
            "detail_path": record["detail_path"],
            "paper_image_path": record["thumb_path"] or resolve_full_image_src(image_path),
            "paper_image_full_path": resolve_full_image_src(image_path),
            "research_unit": record["research_unit"],
            "hook_text": record["hook_text"],
            "reading_minutes": record["reading_minutes"],
            "section_count": record["section_count"],
        }
        if not image_path:
            item["cover_theme"] = record["cover_theme"]
        list_data.append(item)
    return list_data


def build_search_index(records: List[Dict[str, object]]) -> Dict[str, str]:
    """首页全文检索的补充文本（论文概述 + 要点），仅在用户搜索时由前端加载。"""
    index: Dict[str, str] = {}
    for record in records:
        preview_text = str(record["preview_text"])
        extra_points = [point for point in record["key_points"] if point not in preview_text]  # type: ignore[union-attr]
        index[get_paper_identifier(record)] = " ".join([preview_text, *extra_points]).strip()
    return index


def dump_json_lines(data: object) -> str:
    """紧凑 JSON，但每条记录单独一行，兼顾体积与 git diff 可读性。"""
    def dump(value: object) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    if isinstance(data, list):
        return "[\n" + ",\n".join(dump(item) for item in data) + "\n]\n"
    if isinstance(data, dict):
        rows = (f"{dump(key)}:{dump(value)}" for key, value in data.items())
        return "{\n" + ",\n".join(rows) + "\n}\n"
    return dump(data) + "\n"


def render_article_links(record: Dict[str, object]) -> str:
    links = [
        f'<a class="pill-link" data-analytics-event="paper_source_click" href="{escape(str(record["link"]), quote=True)}" target="_blank" rel="noopener noreferrer">arXiv 原文 ↗</a>'
    ]
    if record["translation_link"]:
        links.append(
            f'<a class="pill-link" data-analytics-event="paper_translation_click" href="{escape(str(record["translation_link"]), quote=True)}" target="_blank" rel="noopener noreferrer">中文翻译 ↗</a>'
        )
    return "\n".join(links)


def get_ga_measurement_id() -> str:
    value = os.getenv("GA_MEASUREMENT_ID", "").strip()
    if not re.fullmatch(r"G-[A-Z0-9]+", value, flags=re.IGNORECASE):
        return ""
    return value


def generate_google_analytics() -> str:
    measurement_id = get_ga_measurement_id()
    if not measurement_id:
        return ""

    escaped_id = escape(measurement_id, quote=True)
    return f"""
<script async src="https://www.googletagmanager.com/gtag/js?id={escaped_id}"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag() {{ dataLayer.push(arguments); }}
  gtag('js', new Date());
  gtag('config', '{escaped_id}');
</script>
""".strip()


# ---------- 静态资源 ----------

# 资源文件名 -> 内容哈希，用于给 HTML 中的资源地址加 ?v=，部署后浏览器不会混用新旧版本
_asset_versions: Dict[str, str] = {}


def write_versioned_asset(name: str, content: str) -> None:
    write_text(ASSETS_DIR / name, content)
    _asset_versions[name] = hashlib.sha1(content.encode("utf-8")).hexdigest()[:10]


def asset_url(name: str, prefix: str = "") -> str:
    url = f"{prefix}assets/{name}"
    version = _asset_versions.get(name)
    return f"{url}?v={version}" if version else url


def write_static_assets() -> None:
    """把 scripts/web/ 下的前端源码输出到 site/assets/。"""
    write_versioned_asset("style.css", read_text(WEB_SRC_DIR / "style.css"))
    site_js = "\n\n".join(read_text(WEB_SRC_DIR / name).strip() for name in SITE_SCRIPT_MODULES)
    write_versioned_asset("site.js", site_js + "\n")
    for name in PAGE_SCRIPTS:
        write_versioned_asset(name, read_text(WEB_SRC_DIR / name))
    for name in OBSOLETE_ASSETS:
        (ASSETS_DIR / name).unlink(missing_ok=True)


# ---------- 页面模板 ----------

FAVICON = (
    "data:image/svg+xml,"
    "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E"
    "%3Crect width='64' height='64' rx='18' fill='%23111827'/%3E"
    "%3Ctext x='50%25' y='55%25' text-anchor='middle' dominant-baseline='middle' "
    "font-size='30' font-family='Arial, sans-serif' fill='white'%3EV%3C/text%3E"
    "%3C/svg%3E"
)

# 在样式表加载前确定主题，避免夜间模式下先闪一下白屏
THEME_BOOTSTRAP_SCRIPT = """
    <script>
      (function() {
        var root = document.documentElement;
        try {
          var preference = window.localStorage.getItem('color-theme');
          if (preference !== 'light' && preference !== 'dark') { preference = 'system'; }
          var prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
          var theme = preference === 'system' ? (prefersDark ? 'dark' : 'light') : preference;
          root.dataset.theme = theme;
          root.dataset.themePreference = preference;
          root.style.colorScheme = theme;
        } catch (error) {
          root.dataset.theme = 'light';
          root.dataset.themePreference = 'system';
        }
      })();
    </script>
""".strip()


def generate_head(title: str, description: str, prefix: str, page_script: str) -> str:
    return f"""
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
    <title>{escape(title)}</title>
    <meta name="description" content="{escape(description, quote=True)}" />
    <meta name="theme-color" content="#f4f6fa" media="(prefers-color-scheme: light)" />
    <meta name="theme-color" content="#0d1119" media="(prefers-color-scheme: dark)" />
    <link rel="icon" href="{FAVICON}" />
    {THEME_BOOTSTRAP_SCRIPT}
    <link rel="stylesheet" href="{escape(asset_url("style.css", prefix), quote=True)}" />
    <script defer src="{escape(asset_url("site.js", prefix), quote=True)}"></script>
    <script defer src="{escape(asset_url(page_script, prefix), quote=True)}"></script>
    {generate_google_analytics()}
""".strip()


def render_theme_toggle() -> str:
    return """
<button class="icon-button theme-toggle" type="button" data-theme-toggle aria-label="切换主题" title="切换主题">
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
</button>
""".strip()


def render_brand(home_href: str) -> str:
    return (
        f'<a class="brand" href="{home_href}" aria-label="返回首页">'
        '<span class="brand-mark">VLA<em>/</em>WAM</span>'
        '<span class="brand-name">每日论文精读</span></a>'
    )


def generate_footer() -> str:
    return """
    <footer class="footer">
      <div class="container">
        <p>论文来自 <a href="https://arxiv.org" target="_blank" rel="noopener noreferrer">arXiv.org</a> · 中文精读由大模型生成，可能存在错漏，请以原文为准</p>
      </div>
    </footer>
""".strip()


def generate_index_html() -> str:
    keyword = get_arxiv_keyword_label()
    site_title = f"{keyword} 每日论文卡"
    site_description = f"{keyword} 论文精选卡片"

    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    {generate_head(f"{site_title} - ArXiv Papers", site_description, "", "app.js")}
  </head>
  <body data-data-url="{escape(asset_url("data.json"), quote=True)}" data-search-index-url="{escape(asset_url("search-index.json"), quote=True)}">
    <header class="masthead">
      <div class="container masthead-inner">
        {render_brand("./")}
        <div class="masthead-actions">
          <search class="masthead-search" role="search">
            <label class="visually-hidden" for="search">搜索论文标题、机构、arXiv ID 或概述</label>
            <svg class="search-icon" viewBox="0 0 20 20" fill="none" aria-hidden="true">
              <path d="M9 17A8 8 0 1 0 9 1a8 8 0 0 0 0 16zM18 18l-4-4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            <input id="search" class="search-input" type="search" placeholder="搜索标题、机构、关键词" autocomplete="off" enterkeyhint="search" />
            <span class="search-trailing">
              <kbd class="search-kbd" title="按 / 快速搜索">/</kbd>
              <button class="search-clear" type="button" data-search-clear aria-label="清空搜索">×</button>
            </span>
          </search>
          {render_theme_toggle()}
        </div>
      </div>
    </header>

    <main class="container">
      <section class="intro" aria-labelledby="intro-title">
        <h1 class="intro-title" id="intro-title">{escape(keyword)} 每日论文精读</h1>
        <p class="intro-lede">每天从 arXiv 收集新论文，梳理研究单位、贡献、方法与实验，几分钟读懂一篇。</p>
        <p class="intro-stats" id="paper-count" aria-live="polite">正在加载…</p>
      </section>
      <noscript><div class="status-card"><div class="status-title">需要启用 JavaScript</div><div class="status-text">论文列表由脚本加载，请启用 JavaScript 后刷新页面。</div></div></noscript>
      <div id="status" class="hidden" aria-live="polite"></div>
      <div id="groups" class="feed"></div>
    </main>

    {generate_footer()}

    <button class="icon-button back-to-top" type="button" data-back-to-top aria-label="返回顶部" title="返回顶部">
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
    </button>
  </body>
</html>
"""


def render_paper_nav_link(record: Dict[str, object], direction: str) -> str:
    label = "<kbd>←</kbd> 上一篇" if direction == "prev" else "下一篇 <kbd>→</kbd>"
    return (
        f'<a class="paper-nav-link paper-nav-{direction}" rel="{direction}" '
        f'href="../../papers/{escape(str(record["page_dir"]), quote=True)}/">'
        f'<span class="paper-nav-label">{label}</span>'
        f'<span class="paper-nav-title">{escape(str(record["title"]))}</span></a>'
    )


def generate_paper_html(record: Dict[str, object], prev_record: Dict[str, object] | None = None, next_record: Dict[str, object] | None = None) -> str:
    keyword = get_arxiv_keyword_label()
    site_title = f"{keyword} 每日论文卡"
    page_title = str(record["title"])
    page_description = str(record["preview_text"] or f"{keyword} 论文详情")

    image_path = str(record["paper_image_path"])
    full_src = resolve_full_image_src(image_path, "../../")
    thumb_src = f'../../{record["thumb_path"]}' if record["thumb_path"] else ""
    figure_html = render_article_figure(record, thumb_src or full_src, full_src, thumb_src)

    unit_html = f'<p class="article-unit">{escape(str(record["research_unit"]))}</p>' if record["research_unit"] else ""
    facts = []
    if record["arxiv_id"]:
        facts.append(f'arXiv {record["arxiv_id"]}')
    facts.append(f'{record["section_count"]} 节精读')
    facts.append(f'约 {record["reading_minutes"]} 分钟')
    facts_html = "".join(f"<li>{escape(fact)}</li>" for fact in facts)

    nav_parts = []
    if prev_record:
        nav_parts.append(render_paper_nav_link(prev_record, "prev"))
    if next_record:
        nav_parts.append(render_paper_nav_link(next_record, "next"))

    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    {generate_head(f"{page_title} - {site_title}", page_description, "../../", "paper.js")}
  </head>
  <body class="detail-page" data-paper-id="{escape(get_paper_identifier(record), quote=True)}">
    <div class="reading-progress" aria-hidden="true"></div>
    <header class="masthead">
      <div class="container masthead-inner">
        {render_brand("../../")}
        <div class="masthead-actions">
          <a class="masthead-back" href="../../">← 全部论文</a>
          {render_theme_toggle()}
        </div>
      </div>
    </header>

    <main class="container article-layout">
      <article class="article">
        <p class="article-kicker"><strong>论文精读</strong><time datetime="{escape(str(record["date"]), quote=True)}">{escape(str(record["date"]))}</time></p>
        <h1 class="article-title">{escape(page_title)}</h1>
        <div class="article-links">
          {render_article_links(record)}
        </div>
        <p class="article-lead">{escape(str(record["hook_text"]))}</p>
        {figure_html}
        {unit_html}
        <ul class="article-facts">{facts_html}</ul>
        <div class="article-sections">
{render_article_sections(record)}
        </div>
        <nav class="paper-nav" aria-label="切换论文">{"".join(nav_parts)}</nav>
      </article>
      {render_article_toc(record)}
    </main>

    {generate_footer()}
  </body>
</html>
"""


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

    site_records = build_site_records(records, paper_image_manifest, thumb_map)

    # 先输出静态资源与数据文件，HTML 中的资源地址需要用到它们的内容哈希
    write_static_assets()
    write_versioned_asset("data.json", dump_json_lines(build_list_data(site_records)))
    write_versioned_asset("search-index.json", dump_json_lines(build_search_index(site_records)))

    shutil.rmtree(PAPERS_DIR, ignore_errors=True)
    shutil.rmtree(LEGACY_COVERS_DIR, ignore_errors=True)

    write_text(SITE_DIR / "index.html", generate_index_html())
    for idx, record in enumerate(site_records):
        prev_rec = site_records[idx - 1] if idx > 0 else None
        next_rec = site_records[idx + 1] if idx < len(site_records) - 1 else None
        write_text(PAPERS_DIR / str(record["page_dir"]) / "index.html", generate_paper_html(record, prev_rec, next_rec))

    print(f"生成完成：{SITE_DIR}（{len(site_records)} 篇论文）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
