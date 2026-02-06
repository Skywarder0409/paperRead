"""页面元素分类器 - 基于规则的纯 CPU 实现"""

from __future__ import annotations

import re
from typing import List

from src.models import ElementType


class RuleBasedClassifier:
    """基于关键词和正则的页面元素分类器。

    纯 CPU 运行，不占显存。通过匹配 OCR 输出的 Markdown 文本
    判断该页包含哪些元素类型。
    """

    # 标题关键词（通常出现在前几页）
    _TITLE_PATTERNS = [
        re.compile(r"^#\s+.{10,}", re.MULTILINE),  # Markdown 一级标题且足够长
    ]

    # 摘要关键词
    _ABSTRACT_PATTERNS = [
        re.compile(r"\babstract\b", re.IGNORECASE),
        re.compile(r"\b摘\s*要\b"),
    ]

    # 公式特征
    _EQUATION_PATTERNS = [
        re.compile(r"\$\$.+?\$\$", re.DOTALL),           # 块级公式 $$...$$
        re.compile(r"\\begin\{equation\}"),                # LaTeX equation 环境
        re.compile(r"\\begin\{align"),                     # LaTeX align 环境
        re.compile(r"\\\(.+?\\\)"),                        # 行内公式 \(...\)
    ]

    # 表格特征
    _TABLE_PATTERNS = [
        re.compile(r"\|.+\|.+\|"),                         # Markdown 表格行
        re.compile(r"[Tt]able\s+\d+"),                     # Table 1, Table 2...
        re.compile(r"表\s*\d+"),                            # 表1, 表2...
    ]

    # 图表特征
    _FIGURE_PATTERNS = [
        re.compile(r"[Ff]igure\s+\d+"),                    # Figure 1...
        re.compile(r"[Ff]ig\.\s*\d+"),                     # Fig. 1...
        re.compile(r"图\s*\d+"),                            # 图1...
        re.compile(r"!\[.*?\]\(.*?\)"),                     # Markdown 图片语法
    ]

    # 参考文献特征
    _REFERENCE_PATTERNS = [
        re.compile(r"\breferences\b", re.IGNORECASE),
        re.compile(r"\bbibliography\b", re.IGNORECASE),
        re.compile(r"\b参考文献\b"),
        re.compile(r"^\[\d+\]\s+\w", re.MULTILINE),       # [1] Author...
    ]

    def classify(self, markdown_text: str) -> List[ElementType]:
        """分类页面中包含的元素类型。"""
        if not markdown_text or not markdown_text.strip():
            return [ElementType.BODY_TEXT]

        elements = []

        # 取前 500 字符检测标题/摘要（通常出现在页面顶部）
        head = markdown_text[:500]

        if any(p.search(head) for p in self._TITLE_PATTERNS):
            elements.append(ElementType.TITLE)

        if any(p.search(head) for p in self._ABSTRACT_PATTERNS):
            elements.append(ElementType.ABSTRACT)

        # 全文检测其他元素
        if any(p.search(markdown_text) for p in self._EQUATION_PATTERNS):
            elements.append(ElementType.EQUATIONS)

        if any(p.search(markdown_text) for p in self._TABLE_PATTERNS):
            elements.append(ElementType.TABLES)

        if any(p.search(markdown_text) for p in self._FIGURE_PATTERNS):
            elements.append(ElementType.FIGURES)

        if any(p.search(markdown_text) for p in self._REFERENCE_PATTERNS):
            elements.append(ElementType.REFERENCES)

        # 如果没匹配到任何特殊元素，标记为正文
        if not elements:
            elements.append(ElementType.BODY_TEXT)

        return elements
