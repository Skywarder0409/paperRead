"""阶段2 接口定义：OCR 与理解"""

from __future__ import annotations

from typing import List, Optional

from typing_extensions import Protocol, runtime_checkable

from src.models import ElementType, PageContent, PageInfo


@runtime_checkable
class OCREngineProtocol(Protocol):
    """OCR 引擎接口。

    负责加载视觉模型、对页面图像进行 OCR 和语义理解，
    输出结构化 Markdown。模型使用完毕后应卸载以释放显存。
    """

    def load_model(self, model_name: str) -> None:
        """加载 OCR / 视觉模型到 GPU。

        Args:
            model_name: 模型名称，如 "deepseek-ocr2"

        Raises:
            RuntimeError: 模型加载失败或显存不足

        Example:
            >>> engine = VisionOCREngine()
            >>> engine.load_model("deepseek-ocr2")
        """
        ...

    def process_page(
        self, image_path: str, page_num: int, prompt: Optional[str] = None
    ) -> PageContent:
        """处理单页图像，返回 OCR 结果。

        Args:
            image_path: 页面图像文件路径
            page_num: 页码（从 0 开始）
            prompt: 自定义提示词，为 None 时使用默认提示

        Returns:
            PageContent，包含 Markdown 文本、检测到的元素类型、置信度

        Raises:
            RuntimeError: 模型未加载或推理失败

        Example:
            >>> result = engine.process_page("cache/page_001.png", 1)
            >>> print(result.markdown[:100])
        """
        ...

    def process_all_pages(
        self, pages: List[PageInfo], show_progress: bool = True
    ) -> List[PageContent]:
        """批量处理所有页面。

        Args:
            pages: PageInfo 列表
            show_progress: 是否显示进度信息

        Returns:
            PageContent 列表，与输入页面一一对应

        Example:
            >>> contents = engine.process_all_pages(pages)
            >>> len(contents) == len(pages)
            True
        """
        ...

    def unload_model(self) -> None:
        """卸载模型，释放 GPU 显存。

        Example:
            >>> engine.unload_model()
        """
        ...


@runtime_checkable
class ElementClassifierProtocol(Protocol):
    """页面元素分类器接口（纯 CPU）。

    基于 OCR 输出的 Markdown 文本，识别页面包含的元素类型。
    """

    def classify(self, markdown_text: str) -> List[ElementType]:
        """分类页面中包含的元素类型。

        Args:
            markdown_text: 单页 OCR 输出的 Markdown 文本

        Returns:
            ElementType 列表，如 [ElementType.EQUATIONS, ElementType.FIGURES]

        Example:
            >>> classifier = RuleBasedClassifier()
            >>> elements = classifier.classify("## Abstract\\nThis paper...")
            >>> ElementType.ABSTRACT in elements
            True
        """
        ...
