#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
从 arXiv 论文 HTML 中提取首图并下载到站点静态资源目录。

特点：
1. 只用 Python 标准库，可直接在 GitHub Actions 的普通 `python` 环境运行。
2. 默认增量执行：已下载且文件仍存在的论文会自动跳过。
3. 输出 manifest 到 `site/assets/paper-images.json`，供站点构建阶段读取。

用法示例：
  python scripts/fetch_paper_images.py
  python scripts/fetch_paper_images.py --max-items 20
  python scripts/fetch_paper_images.py --force --max-items 2
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_MD = PROJECT_ROOT / "papers.md"
SITE_DIR = PROJECT_ROOT / "site"
ASSETS_DIR = SITE_DIR / "assets"
IMAGE_DIR = ASSETS_DIR / "paper-images"
MANIFEST_PATH = ASSETS_DIR / "paper-images.json"

BAD_HINTS = {
    "arxiv",
    "logo",
    "icon",
    "badge",
    "avatar",
    "sprite",
    "equation",
    "math",
    "footer",
    "header",
}
MIN_CANDIDATE_SCORE = 40


@dataclass
class PaperRecord:
    title: str
    link: str
    arxiv_id: str


@dataclass
class ImageCandidate:
    url: str
    source: str
    inside_figure: bool
    width: int | None = None
    height: int | None = None
    alt: str = ""
    classes: str = ""
    score: int = 0


def read_text(path: Path) -> str:
    with path.open("r", encoding="utf-8") as file:
        return file.read()


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        file.write(content)


def parse_markdown_table(md_text: str) -> List[PaperRecord]:
    lines = [line for line in md_text.splitlines() if line.strip()]
    if len(lines) < 3:
        return []

    records: List[PaperRecord] = []
    seen = set()

    for line in lines[2:]:
        if not line.strip().startswith("|"):
            continue

        parts = [part.strip() for part in line.strip().strip("|").split("|")]
        if len(parts) < 3:
            continue

        title = parts[1]
        link = parts[2]
        arxiv_id = normalize_arxiv_id(link)
        if not arxiv_id or arxiv_id in seen:
            continue

        seen.add(arxiv_id)
        records.append(PaperRecord(title=title, link=link, arxiv_id=arxiv_id))

    return records


def normalize_arxiv_id(value: str) -> str:
    match = re.search(r"arxiv\.org/(?:abs|pdf|html)/([^?#]+)", value, re.IGNORECASE)
    if not match:
        return ""

    arxiv_id = match.group(1).strip().rstrip("/")
    if arxiv_id.lower().endswith(".pdf"):
        arxiv_id = arxiv_id[:-4]
    arxiv_id = re.sub(r"v\d+$", "", arxiv_id, flags=re.IGNORECASE)
    return arxiv_id


def normalize_abs_url(link: str) -> str:
    url = link.strip()
    url = re.sub(r"^http://", "https://", url, flags=re.IGNORECASE)
    url = re.sub(r"/(?:pdf|html)/", "/abs/", url, flags=re.IGNORECASE)
    url = re.sub(r"\.pdf$", "", url, flags=re.IGNORECASE)
    return url


def parse_int(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"\d+", value)
    return int(match.group(0)) if match else None


def first_src_from_srcset(srcset: str | None) -> str:
    if not srcset:
        return ""
    return srcset.split(",")[0].strip().split(" ")[0].strip()


def as_directory_base(url: str) -> str:
    return url if url.endswith("/") else f"{url}/"


def to_ar5iv_url(html_url: str) -> str:
    return re.sub(
        r"^https://arxiv\.org/html/",
        "https://ar5iv.labs.arxiv.org/html/",
        html_url,
        flags=re.IGNORECASE,
    )


def http_get(url: str, timeout: int = 30) -> tuple[bytes, str, str]:
    request = Request(
        url,
        headers={
            "User-Agent": "daily-arxiv-vla/paper-image-fetcher (+https://arxiv.org)",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        return (
            response.read(),
            response.headers.get_content_type() or "",
            response.geturl(),
        )


class ArxivAbsParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.current_href = ""
        self.current_text: List[str] = []
        self.html_url = ""
        self.versioned_abs_url = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attr_map = dict(attrs)
        self.current_href = (attr_map.get("href") or "").strip()
        self.current_text = []

    def handle_data(self, data: str) -> None:
        if self.current_href:
            self.current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or not self.current_href:
            return

        text = " ".join(part.strip() for part in self.current_text if part.strip()).lower()
        href = urljoin(self.base_url, self.current_href)

        if not self.html_url and text.startswith("html"):
            self.html_url = href

        if not self.versioned_abs_url:
            version_match = re.search(r"/abs/([^?#]+v\d+)$", href, re.IGNORECASE)
            if version_match:
                self.versioned_abs_url = href

        self.current_href = ""
        self.current_text = []


def resolve_html_url(link: str) -> tuple[str | None, str]:
    abs_url = normalize_abs_url(link)
    html_bytes, _, final_abs_url = http_get(abs_url, timeout=30)
    parser = ArxivAbsParser(base_url=final_abs_url)
    parser.feed(html_bytes.decode("utf-8", errors="replace"))

    if parser.html_url:
        return parser.html_url, final_abs_url

    version_match = re.search(r"/abs/([^?#]+v\d+)$", parser.versioned_abs_url or final_abs_url, re.IGNORECASE)
    if version_match:
        return f"https://arxiv.org/html/{version_match.group(1)}", final_abs_url

    arxiv_id = normalize_arxiv_id(final_abs_url or abs_url)
    if arxiv_id:
        return f"https://arxiv.org/html/{arxiv_id}", final_abs_url
    return None, final_abs_url


def parse_candidates_from_html_url(html_url: str) -> tuple[List[ImageCandidate], str]:
    html_bytes, _, final_html_url = http_get(html_url, timeout=30)
    parser = ArxivImageParser(base_url=as_directory_base(final_html_url))
    parser.feed(html_bytes.decode("utf-8", errors="replace"))
    return unique_candidates(parser.candidates), final_html_url


class ArxivImageParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.figure_depth = 0
        self.candidates: List[ImageCandidate] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)

        if tag == "figure":
            self.figure_depth += 1
            return

        if tag == "meta":
            prop = (attr_map.get("property") or attr_map.get("name") or "").strip().lower()
            if prop == "og:image":
                content = (attr_map.get("content") or "").strip()
                if content:
                    self.candidates.append(
                        ImageCandidate(
                            url=urljoin(self.base_url, content),
                            source="og:image",
                            inside_figure=False,
                        )
                    )
            return

        if tag not in {"img", "source"}:
            return

        raw_src = (attr_map.get("src") or "").strip()
        if not raw_src:
            raw_src = first_src_from_srcset(attr_map.get("srcset"))
        if not raw_src:
            return

        self.candidates.append(
            ImageCandidate(
                url=urljoin(self.base_url, raw_src),
                source=tag,
                inside_figure=self.figure_depth > 0,
                width=parse_int(attr_map.get("width")),
                height=parse_int(attr_map.get("height")),
                alt=(attr_map.get("alt") or "").strip(),
                classes=(attr_map.get("class") or "").strip(),
            )
        )

    def handle_endtag(self, tag: str) -> None:
        if tag == "figure" and self.figure_depth > 0:
            self.figure_depth -= 1


def score_candidate(candidate: ImageCandidate) -> int:
    score = 0
    hint_text = " ".join([candidate.url, candidate.alt, candidate.classes]).lower()

    if candidate.source == "og:image":
        score += 80
    if candidate.inside_figure:
        score += 50
    if candidate.source == "img":
        score += 20
    if candidate.source == "source":
        score += 10

    if candidate.width and candidate.height:
        area = candidate.width * candidate.height
        if area >= 200_000:
            score += 30
        elif area >= 50_000:
            score += 15

        if candidate.width >= 300 and candidate.height >= 180:
            score += 20
        if candidate.width < 120 or candidate.height < 120:
            score -= 25

    if any(hint in hint_text for hint in BAD_HINTS):
        score -= 60

    if candidate.url.lower().endswith(".svg"):
        score -= 10

    if "/static/" in candidate.url.lower():
        score -= 80

    if not urlparse(candidate.url).scheme.startswith("http"):
        score -= 100

    return score


def unique_candidates(candidates: List[ImageCandidate]) -> List[ImageCandidate]:
    seen = set()
    unique: List[ImageCandidate] = []

    for candidate in candidates:
        if candidate.url in seen:
            continue
        seen.add(candidate.url)
        candidate.score = score_candidate(candidate)
        unique.append(candidate)

    return sorted(unique, key=lambda item: item.score, reverse=True)


def choose_extension(image_url: str, content_type: str) -> str:
    guessed = mimetypes.guess_extension(content_type.split(";")[0].strip()) if content_type else None
    if guessed:
        return guessed

    suffix = Path(urlparse(image_url).path).suffix
    return suffix or ".bin"


def load_manifest() -> Dict[str, Dict[str, object]]:
    if not MANIFEST_PATH.exists():
        return {}
    try:
        data = json.loads(read_text(MANIFEST_PATH))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def save_manifest(manifest: Dict[str, Dict[str, object]]) -> None:
    write_text(MANIFEST_PATH, json.dumps(manifest, ensure_ascii=False, indent=2))


def local_image_exists(entry: Dict[str, object]) -> bool:
    relative_path = entry.get("path") if isinstance(entry, dict) else ""
    if not relative_path:
        return False
    return (SITE_DIR / str(relative_path)).exists()


def manifest_entry_usable(entry: Dict[str, object]) -> bool:
    if not isinstance(entry, dict):
        return False
    if not local_image_exists(entry):
        return False

    score = entry.get("score")
    image_url = str(entry.get("image_url") or "").lower()
    if isinstance(score, int) and score < 50:
        return False
    if any(hint in image_url for hint in ("arxiv-logo", "/static/")):
        return False
    return True


def select_records(records: List[PaperRecord], manifest: Dict[str, Dict[str, object]], max_items: int, force: bool) -> List[PaperRecord]:
    selected: List[PaperRecord] = []
    for record in records:
        existing = manifest.get(record.arxiv_id)
        if not force and existing and manifest_entry_usable(existing):
            continue
        selected.append(record)

    if max_items > 0:
        return selected[:max_items]
    return selected


def fetch_best_candidate(html_url: str) -> tuple[ImageCandidate | None, List[ImageCandidate]]:
    attempted_urls: List[str] = []
    best_candidates: List[ImageCandidate] = []

    for candidate_url in dict.fromkeys([html_url, to_ar5iv_url(html_url)]):
        if not candidate_url or candidate_url in attempted_urls:
            continue
        attempted_urls.append(candidate_url)

        try:
            candidates, _ = parse_candidates_from_html_url(candidate_url)
        except Exception:
            continue

        if not candidates:
            continue

        if not best_candidates or candidates[0].score > best_candidates[0].score:
            best_candidates = candidates[:5]

        if candidates[0].score >= MIN_CANDIDATE_SCORE:
            return candidates[0], candidates[:5]

    if not best_candidates:
        return None, []
    return None, best_candidates


def download_candidate(arxiv_id: str, candidate: ImageCandidate) -> Dict[str, object]:
    payload, content_type, final_image_url = http_get(candidate.url, timeout=60)
    extension = choose_extension(candidate.url, content_type)
    relative_path = Path("assets") / "paper-images" / f"{arxiv_id.replace('/', '-')}{extension}"
    output_path = SITE_DIR / relative_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(payload)

    return {
        "path": relative_path.as_posix(),
        "image_url": final_image_url or candidate.url,
        "source": candidate.source,
        "score": candidate.score,
        "content_type": content_type,
        "inside_figure": candidate.inside_figure,
        "width": candidate.width,
        "height": candidate.height,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch best paper images from arXiv HTML pages.")
    parser.add_argument("--max-items", type=int, default=0, help="Only process the first N missing papers. 0 means no limit.")
    parser.add_argument("--force", action="store_true", help="Re-fetch papers even if an image already exists.")
    parser.add_argument("--workers", type=int, default=8, help="Number of concurrent download workers.")
    return parser


def process_record(record: PaperRecord) -> Dict[str, object]:
    html_url, abs_url = resolve_html_url(record.link)
    if not html_url:
        raise RuntimeError("No html page found")
    best_candidate, top_candidates = fetch_best_candidate(html_url)
    if not best_candidate:
        raise RuntimeError("No image candidates found")

    return {
        "title": record.title,
        "abs_url": abs_url,
        "html_url": html_url,
        "candidates": [asdict(candidate) for candidate in top_candidates],
        **download_candidate(record.arxiv_id, best_candidate),
    }


def main() -> int:
    args = build_arg_parser().parse_args()

    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    records = parse_markdown_table(read_text(INPUT_MD))
    manifest = load_manifest()
    targets = select_records(records, manifest, max_items=args.max_items, force=args.force)

    print(f"论文总数: {len(records)}")
    print(f"待处理首图: {len(targets)}")
    print(f"并发 workers: {max(1, args.workers)}")

    updated = 0
    failed = 0
    completed = 0

    worker_count = max(1, args.workers)
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_map = {executor.submit(process_record, record): record for record in targets}

        try:
            for future in as_completed(future_map):
                record = future_map[future]
                completed += 1
                print(f"[{completed}/{len(targets)}] {record.arxiv_id} -> {record.title}")

                try:
                    manifest[record.arxiv_id] = future.result()
                    updated += 1
                    save_manifest(manifest)
                    print(f"  saved: {manifest[record.arxiv_id]['path']}")
                    print(f"  image: {manifest[record.arxiv_id]['image_url']}")
                except (HTTPError, URLError, RuntimeError, TimeoutError, OSError) as exc:
                    failed += 1
                    print(f"  failed: {exc}")
                except Exception as exc:
                    failed += 1
                    print(f"  failed: {repr(exc)}")
        except KeyboardInterrupt:
            save_manifest(manifest)
            print("")
            print("中断：已保存当前 manifest，可稍后继续增量补齐。")
            raise

    save_manifest(manifest)

    print("")
    print(f"完成: 新增/更新 {updated} 张, 失败 {failed} 张")
    print(f"Manifest: {MANIFEST_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
