"""章节解析 - 基于正则的 Markdown 结构解析"""

from __future__ import annotations

import re
from typing import Dict, List

from src.models import DocumentStructure, ElementType, PageContent
from src.utils.logger import get_logger

logger = get_logger(__name__)

# 匹配 Markdown 标题行: # Title, ## Section, ### Subsection
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

# 匹配 Figure/Fig. 引用
_FIGURE_RE = re.compile(
    r"(?:[Ff]igure|[Ff]ig\.)\s*(\d+)[.:：]?\s*(.*?)(?:\n|$)", re.MULTILINE
)

# 匹配 Table 引用
_TABLE_RE = re.compile(
    r"[Tt]able\s*(\d+)[.:：]?\s*(.*?)(?:\n|$)", re.MULTILINE
)

# 匹配摘要段落（Abstract 标题后到下一个标题前的内容）
_ABSTRACT_RE = re.compile(
    r"(?:^#{1,3}\s*[Aa]bstract\s*$|^\*{0,2}[Aa]bstract\*{0,2}\s*$)\n(.*?)(?=^#{1,3}\s|\Z)",
    re.MULTILINE | re.DOTALL,
)


class RegexSectionParser:
    """基于正则的章节解析器，纯 CPU 运行。"""

    def parse_sections(self, markdown: str) -> List[Dict]:
        """解析 Markdown 中的章节标题。"""
        sections = []
        for m in _HEADING_RE.finditer(markdown):
            sections.append({
                "level": len(m.group(1)),
                "title": m.group(2).strip(),
                "start_pos": m.start(),
            })
        return sections

    def extract_abstract(self, markdown: str) -> str:
        """提取摘要文本。"""
        m = _ABSTRACT_RE.search(markdown)
        if m:
            return m.group(1).strip()

        # 回退：在前 3000 字符内查找 "abstract" 关键词后的段落
        head = markdown[:3000].lower()
        idx = head.find("abstract")
        if idx == -1:
            return ""

        # 从关键词后取到下一个空行或标题
        rest = markdown[idx:]
        # 跳过 "Abstract" 标题行本身
        first_nl = rest.find("\n")
        if first_nl == -1:
            return ""
        rest = rest[first_nl + 1:]

        # 取到下一个标题或连续空行
        end = re.search(r"\n#{1,6}\s|\n\n\n", rest)
        if end:
            return rest[:end.start()].strip()
        return rest[:2000].strip()

    def _extract_figures(self, markdown: str) -> List[Dict]:
        """提取图表引用。"""
        figures = []
        for m in _FIGURE_RE.finditer(markdown):
            figures.append({
                "number": int(m.group(1)),
                "caption": m.group(2).strip(),
                "pos": m.start(),
            })
        return figures

    def _extract_tables(self, markdown: str) -> List[Dict]:
        """提取表格引用。"""
        tables = []
        for m in _TABLE_RE.finditer(markdown):
            tables.append({
                "number": int(m.group(1)),
                "caption": m.group(2).strip(),
                "pos": m.start(),
            })
        return tables

    def _detect_references_page(self, page_contents: List[PageContent]) -> int:
        """检测参考文献起始页码。"""
        for pc in page_contents:
            if ElementType.REFERENCES in pc.detected_elements:
                return pc.page_num
        return None

    def build_structure_index(
        self,
        page_contents: List[PageContent],
        full_markdown: str,
    ) -> DocumentStructure:
        """构建文档结构索引。"""
        sections = self.parse_sections(full_markdown)
        abstract = self.extract_abstract(full_markdown)
        figures = self._extract_figures(full_markdown)
        tables = self._extract_tables(full_markdown)
        refs_page = self._detect_references_page(page_contents) if page_contents else None

        # 提取文档标题：优先取第一个 level=1 的标题
        title = ""
        for s in sections:
            if s["level"] == 1:
                title = s["title"]
                break
        
        # 改进：如果正则没标出 # 标题，从第一页文本中深度检索候选标题
        if not title and page_contents:
            lines = page_contents[0].markdown.strip().split("\n")
            # 过滤掉 DOI, Elsevier ID, 网址, 和常见的期刊页码头
            noise_patterns = [
                r"^1-s2\.0-.*", r"^http.*", r"^doi:.*", r"^www\..*",
                r"^Downloaded from.*", r"^Journal of .*", r"^Research Article.*",
                r"^\d{4} Elsevier.*", r"^Available online.*"
            ]
            
            for line in lines[:15]: # 扫描前15行
                line = line.strip("#* \t")
                if not line or len(line) < 10: # 太短的通常不是标题
                    continue
                # 检查是否匹配任何噪音模式
                is_noise = any(re.match(p, line, re.IGNORECASE) for p in noise_patterns)
                if not is_noise:
                    title = line
                    break

        structure = DocumentStructure(
            title=title,
            abstract=abstract,
            sections=sections,
            figures=figures,
            tables=tables,
            references_start_page=refs_page,
        )

        logger.info(
            "结构索引: 最终判定标题=%s, %d 章节, %d 图, %d 表",
            title, len(sections), len(figures), len(tables)
        )
        return structure
