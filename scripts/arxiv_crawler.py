import os
import re
import time
from datetime import datetime
from typing import List, Set

import arxiv


class ArxivCollector:
	"""
	/**
	 * @class ArxivCollector
	 * @description 每日自动获取 arXiv 上包含指定关键词的论文，并维护项目根目录下的
	 * `papers.md` 表格（列：日期、标题、链接）。首次运行无数据时执行初始化，之后每日增量并去重。
	 * 关键词可通过环境变量 ARXIV_QUERY_KEYWORD 配置，默认为 "VLA"。
	 */
	"""

	# 允许的主类目（与现有脚本一致）
	_ALLOWED_PRIMARY_CATEGORIES = {
		"cs.CV",
		"cs.AI",
		"cs.CL",
		"cs.LG",
		"cs.MM",
		"cs.RO",
	}

	def __init__(self, papers_path: str, init_results: int = 500, daily_results: int = 20, query_keyword: str = None):
		"""
		/**
		 * @constructor
		 * @param {str} papers_path - `papers.md` 绝对路径
		 * @param {int} init_results - 初始化抓取的最大论文数
		 * @param {int} daily_results - 每日增量抓取的最大论文数
		 * @param {str} query_keyword - arXiv 搜索关键词，如果为 None 则从环境变量 ARXIV_QUERY_KEYWORD 读取，默认为 "VLA"
		 */
		"""
		self.papers_path = papers_path
		self.init_results = init_results
		self.daily_results = daily_results
		self.query_keyword = query_keyword or os.getenv("ARXIV_QUERY_KEYWORD", "VLA")
		self._client = arxiv.Client()

	def _search(self, max_results: int) -> List[arxiv.Result]:
		"""
		搜索 arXiv 论文，带重试机制
		"""
		max_retries = 3

		for attempt in range(max_retries):
			try:
				search = arxiv.Search(
					query=self.query_keyword,
					max_results=max_results,
					sort_by=arxiv.SortCriterion.SubmittedDate,
					sort_order=arxiv.SortOrder.Descending,
				)
				return list(self._client.results(search))
			except Exception as e:
				if attempt < max_retries - 1:
					print(f"arXiv搜索失败，重试 {attempt + 1}/{max_retries}: {repr(e)}")
					time.sleep(2 ** attempt)
				else:
					print(f"arXiv搜索失败，已达最大重试次数: {repr(e)}")
					return []

		return []

	def _filter_categories(self, results: List[arxiv.Result]) -> List[arxiv.Result]:
		"""
		/**
		 * @private 过滤到指定主类目
		 * @param {List[Result]} results - 原始结果
		 * @returns {List[Result]} 过滤后的结果
		 */
		"""
		filtered: List[arxiv.Result] = []
		for r in results:
			if r.primary_category in self._ALLOWED_PRIMARY_CATEGORIES:
				filtered.append(r)
		return filtered

	def _normalize_link(self, link: str) -> str:
		"""
		/**
		 * @private 规范化 arXiv 链接，去掉版本号（如 v1, v2, v3）。
		 * @param {str} link - 原始链接
		 * @returns {str} 规范化后的链接（无版本号）
		 */
		"""
		# 先去掉首尾空格
		link = link.strip()
		# 匹配 arxiv.org/abs/ 后面的 arXiv ID 格式，去掉版本号部分
		# 例如：http://arxiv.org/abs/2510.09607v2 -> http://arxiv.org/abs/2510.09607
		# 只处理包含 arxiv.org/abs/ 的链接，避免误匹配其他数字格式
		return re.sub(r"(arxiv\.org/abs/(\d+\.\d+))v\d+", r"\1", link, flags=re.IGNORECASE).strip()

	def _default_summary_cell(self) -> str:
		"""
		/**
		 * @private 返回简要总结列的默认折叠占位。
		 */
		"""
		return "<details><summary>展开</summary>待生成</details>"

	def _ensure_md_header(self) -> None:
		"""
		/**
		 * 确保 `papers.md` 存在且包含四列表头。
		 */
		"""
		four_header = "| 日期 | 标题 | 链接 | 简要总结 |\n"
		four_sep = "| --- | --- | --- | --- |\n"
		if not os.path.exists(self.papers_path):
			with open(self.papers_path, "w", encoding="utf-8") as f:
				f.write(four_header)
				f.write(four_sep)

	def _load_existing_links(self) -> Set[str]:
		"""
		解析 papers.md 已有的 arXiv 链接集合，用于去重。
		返回规范化后的链接（去掉版本号）。
		"""
		if not os.path.exists(self.papers_path):
			return set()

		links: Set[str] = set()
		link_pattern = re.compile(r"https?://arxiv\.org/abs/[\w\-\.\/]+", re.IGNORECASE)

		try:
			with open(self.papers_path, "r", encoding="utf-8") as f:
				for line in f:
					for m in link_pattern.findall(line):
						normalized = self._normalize_link(m)
						links.add(normalized)
		except Exception as e:
			print(f"警告: 读取 papers.md 失败: {repr(e)}")
			return set()

		return links

	def _format_row(self, r: arxiv.Result) -> str:
		"""
		/**
		 * 将单条结果格式化为 Markdown 表格行（四列）。
		 * @param {Result} r - 论文结果
		 * @returns {str} 形如 `| 2025-09-26 | 标题 | https://arxiv.org/abs/xxxx | <details>..</details> |`
		 */
		"""
		date_str = r.published.strftime("%Y-%m-%d") if isinstance(r.published, datetime) else ""
		title = (r.title or "").replace("|", "\\|").strip()
		# 规范化链接，去掉版本号
		link = self._normalize_link(r.entry_id)
		summary_cell = self._default_summary_cell()
		return f"| {date_str} | {title} | {link} | {summary_cell} |\n"

	def _append_rows(self, rows: List[str]) -> None:
		"""
		将若干行插入到表头之后（保持最新内容靠前）。
		"""
		self._ensure_md_header()

		try:
			with open(self.papers_path, "r", encoding="utf-8") as f:
				lines = f.readlines()
		except Exception as e:
			print(f"错误: 读取 papers.md 失败: {repr(e)}")
			raise

		insert_idx = 2 if len(lines) >= 2 else len(lines)
		new_lines = lines[:insert_idx] + rows + lines[insert_idx:]

		try:
			with open(self.papers_path, "w", encoding="utf-8") as f:
				f.writelines(new_lines)
		except Exception as e:
			print(f"错误: 写入 papers.md 失败: {repr(e)}")
			raise

	def initialize(self) -> int:
		"""
		/**
		 * 初始化 `papers.md`：抓取较多历史论文并写入（去重）。
		 * @returns {int} 写入的论文数量
		 */
		"""
		self._ensure_md_header()
		existing = self._load_existing_links()
		results = self._filter_categories(self._search(self.init_results))
		rows: List[str] = []
		for r in results:
			# 使用规范化链接进行去重比较
			normalized_link = self._normalize_link(r.entry_id)
			if normalized_link in existing:
				continue
			rows.append(self._format_row(r))
		if rows:
			self._append_rows(rows)
		return len(rows)

	def run_daily(self) -> int:
		"""
		/**
		 * 每日增量：抓取少量最新论文，与已存在内容去重后插入表头之后。
		 * @returns {int} 新增的论文数量
		 */
		"""
		self._ensure_md_header()
		existing = self._load_existing_links()
		results = self._filter_categories(self._search(self.daily_results))
		rows: List[str] = []
		for r in results:
			# 使用规范化链接进行去重比较
			normalized_link = self._normalize_link(r.entry_id)
			if normalized_link in existing:
				continue
			rows.append(self._format_row(r))
		if rows:
			self._append_rows(rows)
		return len(rows)


def _default_papers_path() -> str:
	"""
	/**
	 * 计算项目根目录下的 `papers.md` 绝对路径。
	 * 假设当前文件位于 `<root>/scripts/`。
	 */
	"""
	scripts_dir = os.path.dirname(os.path.abspath(__file__))
	root_dir = os.path.dirname(scripts_dir)
	return os.path.join(root_dir, "papers.md")


if __name__ == "__main__":
	import sys
	
	papers_md = _default_papers_path()
	collector = ArxivCollector(papers_md)
	
	# 检查是否已有 papers.md 文件，决定运行模式
	if os.path.exists(papers_md) and os.path.getsize(papers_md) > 0:
		# 文件存在且不为空，执行每日增量更新
		count = collector.run_daily()
		print(f"每日更新完成，新增 {count} 篇论文，写入 {papers_md}")
	else:
		# 文件不存在或为空，执行初始化
		count = collector.initialize()
		print(f"初始化完成，新增 {count} 篇论文，写入 {papers_md}")