"""阶段3 接口定义：文档整合"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from typing_extensions import Protocol, runtime_checkable

from src.models import (
    AssemblyResult,
    DocumentStructure,
    PDFMetadata,
    PageContent,
)


@runtime_checkable
class AssemblerProtocol(Protocol):
    """文档整合器接口。

    将各页 OCR 结果合并为完整文档并保存到磁盘。
    """

    def assemble(
        self,
        page_contents: List[PageContent],
        metadata: PDFMetadata,
        output_dir: Path,
    ) -> AssemblyResult:
        """合并页面内容并保存。

        Args:
            page_contents: 各页 OCR 结果列表
            metadata: PDF 元信息
            output_dir: 输出目录

        Returns:
            AssemblyResult，包含完整 Markdown、文档结构、输出路径

        Raises:
            ValueError: page_contents 为空

        Example:
            >>> assembler = MarkdownAssembler()
            >>> result = assembler.assemble(contents, meta, Path("output/paper1"))
            >>> result.output_path.exists()
            True
        """
        ...


@runtime_checkable
class SectionParserProtocol(Protocol):
    """章节解析器接口。

    解析 Markdown 文档的章节结构，构建索引。
    """

    def parse_sections(self, markdown: str) -> List[Dict]:
        """解析 Markdown 中的章节。

        Args:
            markdown: 完整 Markdown 文本

        Returns:
            章节列表，每个元素为 {"level": int, "title": str, "start_pos": int}

        Example:
            >>> parser = RegexSectionParser()
            >>> sections = parser.parse_sections("# Introduction\\n...")
            >>> sections[0]["title"]
            'Introduction'
        """
        ...

    def extract_abstract(self, markdown: str) -> str:
        """提取摘要文本。

        Args:
            markdown: 完整 Markdown 文本

        Returns:
            摘要文本，若未找到则返回空字符串

        Example:
            >>> abstract = parser.extract_abstract(md_text)
            >>> len(abstract) > 0
            True
        """
        ...

    def build_structure_index(
        self,
        page_contents: List[PageContent],
        full_markdown: str,
    ) -> DocumentStructure:
        """构建文档结构索引。

        Args:
            page_contents: 各页 OCR 结果
            full_markdown: 合并后的完整 Markdown

        Returns:
            DocumentStructure，包含标题、摘要、章节、图表、表格索引

        Example:
            >>> structure = parser.build_structure_index(contents, full_md)
            >>> print(structure.title)
        """
        ...
