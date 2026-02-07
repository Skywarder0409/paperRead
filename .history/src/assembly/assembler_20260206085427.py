"""文档整合 - 合并页面 OCR 结果为完整 Markdown"""

from __future__ import annotations

from pathlib import Path
from typing import List

from src.assembly.section_parser import RegexSectionParser
from src.models import AssemblyResult, PDFMetadata, PageContent
from src.utils.file_ops import ensure_dir, safe_write_text
from src.utils.logger import get_logger

logger = get_logger(__name__)

# 页面分隔符
_PAGE_SEP = "\n\n---\n<!-- page break -->\n\n"


class MarkdownAssembler:
    """将各页 OCR 结果合并为完整的 Markdown 文档并保存。"""

    def __init__(self) -> None:
        self._parser = RegexSectionParser()

    def assemble(
        self,
        page_contents: List[PageContent],
        metadata: PDFMetadata,
        output_dir: Path,
    ) -> AssemblyResult:
        """合并页面内容并保存。"""
        if not page_contents:
            raise ValueError("page_contents 不能为空")

        output_dir = Path(output_dir)
        ensure_dir(output_dir)

        # 按页码排序
        sorted_pages = sorted(page_contents, key=lambda p: p.page_num)

        # 构造文档头部
        header = "# {}\n\n".format(metadata.title)
        if metadata.author:
            header += "**作者**: {}\n\n".format(metadata.author)
        header += "**总页数**: {}\n\n---\n\n".format(metadata.total_pages)

        # 拼接各页内容
        body_parts = []
        for pc in sorted_pages:
            body_parts.append(pc.markdown)

        full_markdown = header + _PAGE_SEP.join(body_parts)

        # 构建结构索引
        structure = self._parser.build_structure_index(page_contents, full_markdown)
        # 如果索引没提取到标题，用 metadata 的
        if not structure.title:
            structure.title = metadata.title

        # 保存到磁盘
        safe_name = _sanitize_filename(metadata.title)
        output_path = output_dir / "{}_structured.md".format(safe_name)
        safe_write_text(output_path, full_markdown)
        logger.info("文档已保存: %s (%d 字符)", output_path, len(full_markdown))

        return AssemblyResult(
            full_markdown=full_markdown,
            structure=structure,
            output_path=output_path,
        )


def _sanitize_filename(name: str, max_len: int = 80) -> str:
    """将标题转为安全文件名。"""
    # 替换不安全字符
    safe = name.replace("/", "_").replace("\\", "_").replace(":", "_")
    safe = safe.replace("?", "").replace("*", "").replace('"', "")
    safe = safe.replace("<", "").replace(">", "").replace("|", "")
    safe = safe.strip(". ")
    if not safe:
        safe = "paper"
    return safe[:max_len]
