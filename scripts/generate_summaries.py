import os
import re
import time
from typing import List, Tuple

import requests
from dotenv import load_dotenv
from openai import OpenAI
from tqdm import tqdm


"""
/**
 * @file generate_summaries.py
 * @description 读取项目根目录 `papers.md`，为“简要总结”列仍为“待生成”的条目生成摘要，
 * 使用在 `test_api.py` 中相同的推理接口（ModelScope OpenAI 兼容 API），并将结果回写到 `papers.md`。
 */
"""


def get_client() -> OpenAI:
    """
    构造 OpenAI 客户端（ModelScope），从环境变量读取配置。
    """
    load_dotenv()
    api_key = os.getenv("MODELSCOPE_ACCESS_TOKEN")
    if not api_key:
        raise RuntimeError("缺少环境变量 MODELSCOPE_ACCESS_TOKEN")

    base_url = os.getenv("MODELSCOPE_BASE_URL", "https://api-inference.modelscope.cn/v1/")
    return OpenAI(api_key=api_key, base_url=base_url)


def get_papers_md_path() -> str:
    """
    /**
     * @function get_papers_md_path
     * @description 获取项目根目录下的 `papers.md` 绝对路径。
     */
    """
    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(scripts_dir)
    return os.path.join(root_dir, "papers.md")


def is_placeholder_summary(cell: str) -> bool:
    """
    /**
     * @function is_placeholder_summary
     * @description 判断“简要总结”单元格是否为默认占位（待生成）。
     */
    """
    return "待生成" in cell


def parse_table_line(line: str) -> List[str]:
    """
    /**
     * @function parse_table_line
     * @description 解析 markdown 表格行，返回去除空项后的单元格列表。
     * @param {str} line - 形如 `| a | b | c | d |\n`
     * @returns {List[str]} 单元格列表
     */
    """
    parts = [p.strip() for p in line.strip().split("|")]
    # 去除首尾空项（因为行首尾都有 `|`）
    cells = [p for p in parts if p and p != "---"]
    return cells


def rebuild_line(date_str: str, title: str, link: str, summary_html: str) -> str:
    """
    /**
     * @function rebuild_line
     * @description 将四列内容重建为表格行。
     */
    """
    safe_title = title.replace("|", "\\|")
    safe_summary = summary_html.replace("|", "\\|")
    return f"| {date_str} | {safe_title} | {link} | {safe_summary} |\n"


def generate_summary_for_link(client: OpenAI, link: str, model: str = None) -> str:
    """
    抓取 arXiv HTML 原文并让模型基于 HTML 生成简要总结。
    包含重试机制和错误处理。
    """
    # 从环境变量读取模型配置，如果未指定则使用默认值
    if model is None:
        model = os.getenv("MODELSCOPE_MODEL", "deepseek-ai/DeepSeek-V3.2")

    # 将 /abs/ 链接转换为 /html/ 页面
    html_url = re.sub(r"/abs/", "/html/", link)

    # 抓取 HTML 文本（带重试）
    max_retries = int(os.getenv("HTTP_MAX_RETRIES", "3"))
    timeout = int(os.getenv("HTTP_TIMEOUT", "30"))
    html_content = None

    for attempt in range(max_retries):
        try:
            resp = requests.get(html_url, timeout=timeout)
            resp.raise_for_status()
            html_content = resp.text
            break
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                print(f"警告: HTML页面不存在，尝试使用PDF: {link}")
                # 如果HTML不存在，尝试获取摘要（fallback）
                return ""
            elif attempt < max_retries - 1:
                print(f"HTTP错误 {e.response.status_code}，重试 {attempt + 1}/{max_retries}: {link}")
                time.sleep(2 ** attempt)
            else:
                print(f"HTTP请求失败，已达最大重试次数: {link}")
                return ""
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                print(f"网络错误，重试 {attempt + 1}/{max_retries}: {link}")
                time.sleep(2 ** attempt)
            else:
                print(f"网络请求失败: {link}: {repr(e)}")
                return ""

    if not html_content:
        return ""

    # 按需截断，避免上下文过长
    max_chars = int(os.getenv("HTML_MAX_CHARS", "180000"))
    if len(html_content) > max_chars:
        html_content = html_content[:max_chars]

    # API 调用（带重试）
    api_max_retries = int(os.getenv("API_MAX_RETRIES", "3"))
    for attempt in range(api_max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        'role': 'system',
                        'content': '你是一名论文阅读专家。根据提供的Arxiv论文HTML原文，总结论文的要点，只需提供Markdown格式文本，不要使用加粗，不需要输出其他内容。\n要求：\n论文总结分为以下部分：论文研究单位、论文概述、论文核心贡献点、论文方法描述、论文使用数据集和训练资源、论文使用的评估环境和评估指标。'
                    },
                    {
                        'role': 'user',
                        'content': f"以下为论文的HTML原文（可能已截断）：\n\n{html_content}"
                    },
                ],
                stream=False,
            )

            if not response.choices:
                print(f"警告: API返回无choices，链接: {link}")
                return ""

            text = getattr(response.choices[0].message, "content", "")
            if not text:
                print(f"警告: API返回content为空，链接: {link}")
                return ""

            text = text.strip()
            # 移除模型可能输出的 <think>...</think> 思考内容
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
            # 规范化换行：保留换行符，但规范化空白
            text = re.sub(r"[ \t]+", " ", text)
            text = re.sub(r"\n{3,}", "\n\n", text)
            text = re.sub(r" +\n", "\n", text)
            # 将换行符转换为 <br> 标签以便在 Markdown 表格中存储
            text = text.replace("\n", "<br>")

            if not text:
                print(f"警告: 处理后文本为空，链接: {link}")
                return ""

            return text

        except Exception as e:
            if attempt < api_max_retries - 1:
                print(f"API调用失败，重试 {attempt + 1}/{api_max_retries}: {link}")
                time.sleep(2 ** attempt)
            else:
                print(f"API调用失败，已达最大重试次数: {link}: {repr(e)}")
                return ""

    return ""


def default_summary_cell() -> str:
    """
    /**
     * @function default_summary_cell
     * @description 默认折叠占位单元格 HTML。
     */
    """
    return "<details><summary>展开</summary>待生成</details>"


def wrap_in_details(summary_text: str) -> str:
    """
    /**
     * @function wrap_in_details
     * @description 将纯文本包装为折叠 HTML。
     */
    """
    return f"<details><summary>展开</summary>{summary_text}</details>"


def update_papers_md() -> Tuple[int, int]:
    """
    /**
     * @function update_papers_md
     * @description 读取 `papers.md`，为缺失摘要的条目生成并写回。
     * @returns {Tuple[int,int]} (总需更新数, 实际更新成功数)
     */
    """
    papers_md = get_papers_md_path()
    if not os.path.exists(papers_md):
        raise FileNotFoundError(f"未找到 {papers_md}，请先运行爬取初始化")

    with open(papers_md, "r", encoding="utf-8") as f:
        lines = f.readlines()

    if len(lines) < 2:
        return 0, 0

    header = lines[:2]
    body = lines[2:]

    client = get_client()

    entries_to_update: List[Tuple[int, str, str, str]] = []
    for idx, line in enumerate(body):
        if not line.strip().startswith("|"):
            continue
        cells = parse_table_line(line)
        if len(cells) != 4:
            continue
        date_str, title, link, summary_cell = cells
        if not is_placeholder_summary(summary_cell):
            continue
        entries_to_update.append((idx, date_str, title, link))

    need_count = len(entries_to_update)
    success_count = 0
    batch_size = int(os.getenv("BATCH_WRITE_SIZE", "5"))
    updates_since_last_write = 0

    progress_bar = tqdm(entries_to_update, desc="生成简要总结", unit="篇")

    for idx, date_str, title, link in progress_bar:
        try:
            summary_text = generate_summary_for_link(client, link)
            if not summary_text:
                print(f"警告: 生成摘要为空，跳过: {link}")
                continue
            new_summary_cell = wrap_in_details(summary_text)
            new_line = rebuild_line(date_str, title, link, new_summary_cell)
            # 更新内存中的行
            body[idx] = new_line
            success_count += 1
            updates_since_last_write += 1
            progress_bar.set_postfix({"成功": success_count})

            # 批量写入：每处理 batch_size 篇就写一次文件
            if updates_since_last_write >= batch_size:
                try:
                    with open(papers_md, "w", encoding="utf-8") as f:
                        f.writelines(header + body)
                    updates_since_last_write = 0
                except Exception as e:
                    print(f"警告: 写入文件失败: {repr(e)}")

        except Exception as e:
            print(f"生成摘要失败: {link}: {repr(e)}")

    # 最后写入一次，确保所有更改都保存
    if updates_since_last_write > 0:
        try:
            with open(papers_md, "w", encoding="utf-8") as f:
                f.writelines(header + body)
        except Exception as e:
            print(f"错误: 最终写入文件失败: {repr(e)}")
            raise

    return need_count, success_count


if __name__ == "__main__":
    total, updated = update_papers_md()
    print(f"需要生成摘要的条目: {total}，已更新: {updated}")


