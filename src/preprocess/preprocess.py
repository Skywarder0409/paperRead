"""PDF 预处理 - PyMuPDF 实现"""

from __future__ import annotations

from pathlib import Path
from typing import List

from src.models import PDFMetadata, PageInfo
from src.utils.file_ops import ensure_dir
from src.utils.logger import get_logger

logger = get_logger(__name__)


class PyMuPDFPreprocessor:
    """基于 PyMuPDF (fitz) 的 PDF 预处理器。

    纯 CPU 运行，不占用显存。将 PDF 每页渲染为 PNG 图像，
    同时提取 PDF 元信息。
    """

    def extract_pages(
        self, pdf_path: Path, output_dir: Path, dpi: int = 200
    ) -> List[PageInfo]:
        """将 PDF 拆分为页面图像。"""
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError("PDF 文件不存在: {}".format(pdf_path))

        import fitz  # PyMuPDF

        ensure_dir(output_dir)

        try:
            doc = fitz.open(str(pdf_path))
        except Exception as e:
            raise RuntimeError("PDF 解析失败: {}".format(e))

        pages = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(dpi=dpi)

            img_path = output_dir / "page_{:03d}.png".format(page_num)
            pix.save(str(img_path))

            pages.append(PageInfo(
                page_num=page_num,
                image_path=img_path,
                width=pix.width,
                height=pix.height,
            ))

        doc.close()
        logger.info("PDF 拆分完成: %d 页 -> %s", len(pages), output_dir)
        return pages

    def get_metadata(self, pdf_path: Path) -> PDFMetadata:
        """提取 PDF 元信息。"""
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError("PDF 文件不存在: {}".format(pdf_path))

        import fitz

        doc = fitz.open(str(pdf_path))
        meta = doc.metadata or {}
        total = len(doc)
        doc.close()

        title = meta.get("title", "") or pdf_path.stem
        author = meta.get("author", "")

        logger.info("PDF 元信息: title=%s, author=%s, pages=%d", title, author, total)
        return PDFMetadata(
            title=title,
            author=author,
            total_pages=total,
            file_path=pdf_path,
        )
