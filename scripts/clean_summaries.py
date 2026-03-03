#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
清理和规范化 papers.md 中的总结内容：
1. 删除 ```markdown 和 ``` 标记
2. 如果最高级别标题是 ###，将所有标题降级（### -> #, #### -> ##）
3. 删除没有"论文概述"部分的总结
"""

import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_MD = PROJECT_ROOT / "papers.md"


def read_text(path: Path) -> str:
    with path.open("r", encoding="utf-8") as f:
        return f.read()


def write_text(path: Path, content: str) -> None:
    with path.open("w", encoding="utf-8") as f:
        f.write(content)


def normalize_summary_content(content: str) -> str:
    """规范化总结内容"""
    # 1. 删除 ```markdown 和 ```
    content = re.sub(r'```markdown\s*', '', content)
    content = re.sub(r'```\s*', '', content)

    # 2. 将 <br> 标签转换为换行符
    content = content.replace('<br>', '\n').replace('<br/>', '\n').replace('<br />', '\n')

    # 3. 将所有标题都改为 ##
    content = re.sub(r'^#{1,6}\s+', '## ', content, flags=re.MULTILINE)

    # 4. 将换行符转回 <br> 标签
    content = content.replace('\n', '<br>')

    return content.strip()


def has_paper_overview(content: str) -> bool:
    """检查总结中是否包含"论文概述"部分"""
    return '论文概述' in content


def process_papers_md(content: str) -> tuple:
    """
    处理 papers.md 内容
    返回: (处理后的内容, 删除的条目数, 规范化的条目数)
    """
    lines = content.splitlines()
    result_lines = []
    deleted_count = 0
    normalized_count = 0

    for i, line in enumerate(lines):
        # 保留表头
        if i < 2:
            result_lines.append(line)
            continue

        # 处理数据行
        if line.strip().startswith('|'):
            # 解析表格行
            parts = [p.strip() for p in line.strip().strip('|').split('|')]
            if len(parts) >= 4:
                date_str, title, link = parts[0], parts[1], parts[2]
                summary_cell = '|'.join(parts[3:])

                # 提取 <details> 内容
                details_match = re.search(r'<details><summary>.*?</summary>(.*?)</details>', summary_cell, re.DOTALL)
                if details_match:
                    details_content = details_match.group(1)

                    # 检查是否有"论文概述"
                    if not has_paper_overview(details_content):
                        deleted_count += 1
                        print(f"删除没有论文概述的条目: {title[:50]}...")
                        continue

                    # 规范化内容
                    normalized_content = normalize_summary_content(details_content)
                    if normalized_content != details_content:
                        normalized_count += 1

                    # 重新构建行
                    new_summary_cell = f'<details><summary>展开</summary>{normalized_content}</details>'
                    new_line = f'| {date_str} | {title} | {link} | {new_summary_cell} |'
                    result_lines.append(new_line)
                else:
                    # 没有 details 标签，保留原样
                    result_lines.append(line)
            else:
                result_lines.append(line)
        else:
            result_lines.append(line)

    return '\n'.join(result_lines), deleted_count, normalized_count


def main() -> int:
    if not INPUT_MD.exists():
        print(f"未找到 {INPUT_MD}", file=sys.stderr)
        return 1

    print(f"读取 {INPUT_MD}...")
    content = read_text(INPUT_MD)

    print("处理中...")
    new_content, deleted, normalized = process_papers_md(content)

    print(f"写入 {INPUT_MD}...")
    write_text(INPUT_MD, new_content)

    print(f"\n完成！")
    print(f"- 删除了 {deleted} 个没有论文概述的条目")
    print(f"- 规范化了 {normalized} 个条目")

    return 0


if __name__ == "__main__":
    sys.exit(main())
