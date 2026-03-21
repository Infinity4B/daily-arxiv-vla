#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
为无法直接下载首图的论文生成 Playwright 截图兜底队列。

输出文件默认写入：
  tmp/paper-image-fallback-queue.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fetch_paper_images import (
    IMAGE_DIR,
    INPUT_MD,
    load_manifest,
    parse_markdown_table,
    read_text,
    resolve_html_url,
    to_ar5iv_url,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
QUEUE_PATH = PROJECT_ROOT / "tmp" / "paper-image-fallback-queue.json"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build screenshot fallback queue for missing paper images.")
    parser.add_argument("--max-items", type=int, default=0, help="Only queue the first N missing papers. 0 means no limit.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()

    manifest = load_manifest()
    records = parse_markdown_table(read_text(INPUT_MD))
    missing_records = [record for record in records if record.arxiv_id not in manifest]
    if args.max_items > 0:
        missing_records = missing_records[: args.max_items]

    queue = []
    for record in missing_records:
        html_url, abs_url = resolve_html_url(record.link)
        queue.append(
            {
                "arxiv_id": record.arxiv_id,
                "title": record.title,
                "abs_url": abs_url,
                "html_url": html_url or "",
                "ar5iv_url": to_ar5iv_url(html_url) if html_url else "",
                "output_path": str((IMAGE_DIR / f"{record.arxiv_id}.png").resolve()),
                "relative_path": f"assets/paper-images/{record.arxiv_id}.png",
            }
        )

    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUEUE_PATH.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"队列: {QUEUE_PATH}")
    print(f"待截图论文: {len(queue)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
