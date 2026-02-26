#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
清除 papers.md 中所有简要总结，替换为默认占位符
"""

import os
import re
from pathlib import Path


def get_papers_md_path() -> str:
    """获取 papers.md 的绝对路径"""
    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(scripts_dir)
    return os.path.join(root_dir, "papers.md")


def parse_table_line(line: str) -> list[str]:
    """解析 markdown 表格行，返回单元格列表"""
    parts = [p.strip() for p in line.strip().split("|")]
    # 去除首尾空项（因为行首尾都有 `|`）
    cells = [p for p in parts if p and p != "---"]
    return cells


def rebuild_line(date_str: str, title: str, link: str, summary_html: str) -> str:
    """将四列内容重建为表格行"""
    safe_title = title.replace("|", "\\|")
    safe_summary = summary_html.replace("|", "\\|")
    return f"| {date_str} | {safe_title} | {link} | {safe_summary} |\n"


def default_summary_cell() -> str:
    """默认占位单元格 HTML"""
    return "<details><summary>展开</summary>待生成</details>"


def is_valid_markdown_format(summary_cell: str) -> bool:
    """
    检查摘要是否遵循正确的 Markdown 格式
    要求：必须包含 ## 二级标题
    """
    # 提取 <details> 内容
    match = re.search(r"<details>([\s\S]*?)</details>", summary_cell, re.IGNORECASE)
    if not match:
        return False

    content = match.group(1)
    # 去掉 <summary>...</summary>
    content = re.sub(r"<summary>[\s\S]*?</summary>", "", content, flags=re.IGNORECASE)
    # 将 <br> 转换回换行
    content = content.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    content = content.strip()

    # 检查是否包含 ## 标题（至少要有一个）
    if not re.search(r"##\s+", content):
        return False

    return True


def clear_all_summaries() -> int:
    """清除所有不符合格式的简要总结，返回清除的数量"""
    papers_md = get_papers_md_path()
    if not os.path.exists(papers_md):
        raise FileNotFoundError(f"未找到 {papers_md}")

    with open(papers_md, "r", encoding="utf-8") as f:
        lines = f.readlines()

    if len(lines) < 2:
        return 0

    header = lines[:2]
    body = lines[2:]

    cleared_count = 0
    new_body = []

    for line in body:
        if not line.strip().startswith("|"):
            new_body.append(line)
            continue

        cells = parse_table_line(line)
        if len(cells) != 4:
            new_body.append(line)
            continue

        date_str, title, link, summary_cell = cells

        # 检查是否是"待生成"占位符
        if "待生成" in summary_cell:
            new_body.append(line)
            continue

        # 检查是否符合 Markdown 格式
        if not is_valid_markdown_format(summary_cell):
            # 不符合格式，替换为默认占位符
            new_summary_cell = default_summary_cell()
            new_line = rebuild_line(date_str, title, link, new_summary_cell)
            new_body.append(new_line)
            cleared_count += 1
            print(f"清除不符合格式的摘要: {title[:50]}...")
        else:
            # 符合格式，保持不变
            new_body.append(line)

    # 写回文件
    with open(papers_md, "w", encoding="utf-8") as f:
        f.writelines(header + new_body)

    return cleared_count


if __name__ == "__main__":
    try:
        count = clear_all_summaries()
        print(f"\n总计清除 {count} 条不符合 Markdown 格式的简要总结")
    except Exception as e:
        print(f"错误: {e}")
        exit(1)

