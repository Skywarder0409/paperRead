"""阶段1 接口定义：PDF 预处理"""

from __future__ import annotations

from pathlib import Path
from typing import List

from typing_extensions import Protocol, runtime_checkable

from src.models import PDFMetadata, PageInfo


@runtime_checkable
class PreprocessorProtocol(Protocol):
    """PDF 预处理器接口。

    负责将 PDF 文件拆分为页面图像并提取元信息。
    """

    def extract_pages(
        self, pdf_path: Path, output_dir: Path, dpi: int = 200
    ) -> List[PageInfo]:
        """将 PDF 拆分为页面图像。

        Args:
            pdf_path: PDF 文件路径
            output_dir: 页面图像输出目录
            dpi: 渲染 DPI，默认 200，影响 OCR 质量

        Returns:
            PageInfo 列表，包含每页的编号、图像路径、宽高

        Raises:
            FileNotFoundError: PDF 文件不存在
            RuntimeError: PDF 解析失败

        Example:
            >>> preprocessor = PyMuPDFPreprocessor()
            >>> pages = preprocessor.extract_pages(Path("paper.pdf"), Path("cache/pages"))
            >>> pages[0].image_path
            PosixPath('cache/pages/page_000.png')
        """
        ...

    def get_metadata(self, pdf_path: Path) -> PDFMetadata:
        """提取 PDF 元信息。

        Args:
            pdf_path: PDF 文件路径

        Returns:
            PDFMetadata，包含标题、作者、总页数、文件路径

        Raises:
            FileNotFoundError: PDF 文件不存在

        Example:
            >>> meta = preprocessor.get_metadata(Path("paper.pdf"))
            >>> print(meta.total_pages)
            20
        """
        ...
