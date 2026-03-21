#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试从 arXiv 论文 HTML 中提取首图候选。

默认会抓两篇论文：
1. 下载 /html/ 页面
2. 从 og:image、figure img、普通 img 中提取候选
3. 选择得分最高的候选图并下载到本地目录

运行示例：
  uv run python scripts/test_extract_paper_images.py
  uv run python scripts/test_extract_paper_images.py --output-dir tmp/paper-image-test
  uv run python scripts/test_extract_paper_images.py http://arxiv.org/abs/2603.19199 http://arxiv.org/abs/2603.19233
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import re
from dataclasses import dataclass, asdict
from html.parser import HTMLParser
from pathlib import Path
from typing import List
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "tmp" / "paper-image-test"
DEFAULT_LINKS = [
    "http://arxiv.org/abs/2603.19199",
    "http://arxiv.org/abs/2603.19233",
]

BAD_HINTS = {
    "logo",
    "icon",
    "badge",
    "avatar",
    "sprite",
    "equation",
    "math",
    "footer",
    "header",
    "arxiv",
}


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


@dataclass
class DownloadResult:
    arxiv_id: str
    html_url: str
    image_url: str
    source: str
    score: int
    content_type: str
    local_path: str


def normalize_html_url(link: str) -> str:
    return re.sub(r"/abs/", "/html/", link.strip())


def normalize_arxiv_id(link: str) -> str:
    match = re.search(r"arxiv\.org/(?:abs|html)/([^?#/]+(?:/[^?#/]+)?)", link, re.IGNORECASE)
    if not match:
        return "paper"
    value = match.group(1)
    return re.sub(r"v\d+$", "", value, flags=re.IGNORECASE).replace("/", "-")


def parse_int(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"\d+", value)
    return int(match.group(0)) if match else None


def first_src_from_srcset(srcset: str | None) -> str:
    if not srcset:
        return ""
    return srcset.split(",")[0].strip().split(" ")[0].strip()


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

        candidate = ImageCandidate(
            url=urljoin(self.base_url, raw_src),
            source=tag,
            inside_figure=self.figure_depth > 0,
            width=parse_int(attr_map.get("width")),
            height=parse_int(attr_map.get("height")),
            alt=(attr_map.get("alt") or "").strip(),
            classes=(attr_map.get("class") or "").strip(),
        )
        self.candidates.append(candidate)

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

    if not urlparse(candidate.url).scheme.startswith("http"):
        score -= 100

    return score


def unique_candidates(candidates: List[ImageCandidate]) -> List[ImageCandidate]:
    seen = set()
    unique: List[ImageCandidate] = []
    for candidate in candidates:
        key = candidate.url
        if key in seen:
            continue
        seen.add(key)
        candidate.score = score_candidate(candidate)
        unique.append(candidate)
    return sorted(unique, key=lambda item: item.score, reverse=True)


def choose_extension(image_url: str, content_type: str) -> str:
    guessed = mimetypes.guess_extension(content_type.split(";")[0].strip()) if content_type else None
    if guessed:
        return guessed

    suffix = Path(urlparse(image_url).path).suffix
    if suffix:
        return suffix
    return ".bin"


def http_get(url: str, timeout: int = 30) -> tuple[bytes, str]:
    request = Request(
        url,
        headers={
            "User-Agent": "daily-arxiv-vla/figure-test (+https://arxiv.org)",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        return response.read(), response.headers.get_content_type() or ""


def fetch_html(html_url: str) -> str:
    payload, _ = http_get(html_url, timeout=30)
    return payload.decode("utf-8", errors="replace")


def download_image(candidate: ImageCandidate, output_dir: Path, arxiv_id: str) -> DownloadResult:
    payload, content_type = http_get(candidate.url, timeout=60)
    extension = choose_extension(candidate.url, content_type)
    output_path = output_dir / arxiv_id / f"best{extension}"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(payload)

    return DownloadResult(
        arxiv_id=arxiv_id,
        html_url="",
        image_url=candidate.url,
        source=candidate.source,
        score=candidate.score,
        content_type=content_type,
        local_path=str(output_path),
    )


def process_link(link: str, output_dir: Path) -> dict:
    html_url = normalize_html_url(link)
    arxiv_id = normalize_arxiv_id(link)
    html_text = fetch_html(html_url)

    parser = ArxivImageParser(base_url=html_url)
    parser.feed(html_text)
    candidates = unique_candidates(parser.candidates)

    top_candidates = candidates[:5]
    if not top_candidates:
        return {
            "arxiv_id": arxiv_id,
            "html_url": html_url,
            "downloaded": None,
            "candidates": [],
            "error": "No image candidates found",
        }

    downloaded = download_image(top_candidates[0], output_dir=output_dir, arxiv_id=arxiv_id)
    downloaded.html_url = html_url

    return {
        "arxiv_id": arxiv_id,
        "html_url": html_url,
        "downloaded": asdict(downloaded),
        "candidates": [asdict(candidate) for candidate in top_candidates],
        "error": "",
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Test extracting first useful images from arXiv HTML pages.")
    parser.add_argument("links", nargs="*", default=DEFAULT_LINKS, help="arXiv abs links to inspect")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory to store downloaded test images and report",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for link in args.links:
        print(f"Processing: {link}")
        try:
            result = process_link(link, output_dir=output_dir)
        except (HTTPError, URLError) as exc:
            result = {
                "arxiv_id": normalize_arxiv_id(link),
                "html_url": normalize_html_url(link),
                "downloaded": None,
                "candidates": [],
                "error": repr(exc),
            }
        except Exception as exc:
            result = {
                "arxiv_id": normalize_arxiv_id(link),
                "html_url": normalize_html_url(link),
                "downloaded": None,
                "candidates": [],
                "error": repr(exc),
            }
        results.append(result)

    report_path = output_dir / "report.json"
    report_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print("")
    print(f"Report: {report_path}")
    for result in results:
        print(f"- {result['arxiv_id']}: {result['html_url']}")
        if result["downloaded"]:
            downloaded = result["downloaded"]
            print(f"  best: {downloaded['image_url']}")
            print(f"  saved: {downloaded['local_path']}")
            print(f"  type: {downloaded['content_type'] or 'unknown'}")
            print(f"  score: {downloaded['score']}")
        else:
            print(f"  error: {result['error']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
