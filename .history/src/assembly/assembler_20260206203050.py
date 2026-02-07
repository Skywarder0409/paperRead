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

        # 1. 首先拼接正文内容，用于解析真实标题
        body_content = _PAGE_SEP.join(pc.markdown for pc in sorted_pages)
        
        # 2. 尝试从正文解析结构（包含标题提取）
        structure = self._parser.build_structure_index(page_contents, body_content)
        
        # 3. 如果从正文找到了有效的标题，且旧标题看起来是“脏数据”（如 stem 名），则更新之
        if structure.title and (len(structure.title) > 5):
            # 如果原标题含有特征字符（如数字、连字符过多）或者是文件名 stem，则替换
            # 这里简单处理：只要找到新标题就尝试更新，提高准确度
            if structure.title.lower() != metadata.title.lower():
                logger.info("检测到真实标题: 「%s」 (替换原元数据: 「%s」)", structure.title, metadata.title)
                metadata.title = structure.title

        # 4. 构造文档最终头部（使用已更新的标题）
        header = "# {}\n\n".format(metadata.title)
        if metadata.author:
            header += "**作者**: {}\n\n".format(metadata.author)
        header += "**总页数**: {}\n\n---\n\n".format(metadata.total_pages)

        full_markdown = header + body_content

        # 5. 保存到磁盘
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
