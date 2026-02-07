"""长文档分块策略"""

from __future__ import annotations

import re
from typing import List

from src.models import DocumentStructure
from src.analysis.prompts import CHUNK_SUMMARY_PROMPT
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SectionBasedChunking:
    """基于章节的分块策略。

    优先按章节标题切分；若文档缺少章节标题，则按固定字符数切分。
    """

    def should_chunk(self, text: str, max_length: int = 50000) -> bool:
        """判断是否需要分块。"""
        return len(text) > max_length

    def split_by_sections(
        self, text: str, structure: DocumentStructure
    ) -> List[str]:
        """按章节分割文档。"""
        sections = structure.sections
        if not sections:
            # 没有解析到章节，按固定大小切分
            return self._split_by_size(text)

        # 按 start_pos 排序，取 level <= 2 的主章节作为切分点
        split_points = sorted(
            [s["start_pos"] for s in sections if s["level"] <= 2]
        )

        if not split_points:
            return self._split_by_size(text)

        chunks = []
        for i, pos in enumerate(split_points):
            end = split_points[i + 1] if i + 1 < len(split_points) else len(text)
            chunk = text[pos:end].strip()
            if chunk:
                chunks.append(chunk)

        # 如果第一个切分点不在文档开头，把前面的内容也加上
        if split_points[0] > 0:
            preamble = text[:split_points[0]].strip()
            if preamble:
                chunks.insert(0, preamble)

        logger.info("按章节分块: %d 块", len(chunks))
        return chunks

    def _split_by_size(self, text: str, chunk_size: int = 30000) -> List[str]:
        """按固定字符数切分，尽量在段落边界断开。"""
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            if end >= len(text):
                chunks.append(text[start:])
                break

            # 尝试在段落边界（连续换行）断开
            boundary = text.rfind("\n\n", start + chunk_size // 2, end)
            if boundary != -1:
                end = boundary

            chunks.append(text[start:end].strip())
            start = end

        logger.info("按大小分块: %d 块 (每块 ~%d 字符)", len(chunks), chunk_size)
        return chunks

    def hierarchical_summarize(
        self, llm, chunks: List[str], final_prompt: str
    ) -> str:
        """分层总结：先逐块进行目标导向的总结，再整合为最终分析。

        Args:
            llm: LLM 引擎实例
            chunks: 文本块列表
            final_prompt: 最终整合 prompt
        """
        logger.info("分层总结 (目标导向): %d 块待处理", len(chunks))

        # ── 自动提取关注点 ──
        # 从最终 Prompt 的前几行提取目标（如标题或第一行）
        intent_hint = "核心内容"
        first_line = final_prompt.strip().split("\n")[0]
        if "# " in first_line:
            intent_hint = first_line.replace("#", "").strip()
        elif "提示词" in first_line:
             intent_hint = "文中关键信息"
        
        logger.info("感知到分析目标: %s", intent_hint)

        # 第一轮：目标导向的逐块总结
        summaries = []
        for i, chunk in enumerate(chunks):
            logger.info("  总结块 %d/%d (%d 字符)", i + 1, len(chunks), len(chunk))
            
            # 动态构造中间层 Prompt
            dynamic_chunk_prompt = (
                f"你正在协助进行一项关于「{intent_hint}」的深度分析。\n"
                f"请总结以下章节内容，**特别留意与「{intent_hint}」相关的细节**（300字内）：\n\n"
                f"{chunk}"
            )
            
            summary = llm._generate(dynamic_chunk_prompt)
            summaries.append(summary)

        # 第二轮：整合
        combined = "\n\n".join(
            "### 第{}部分回顾\n{}".format(i + 1, s) for i, s in enumerate(summaries)
        )
        logger.info("整合总结: %d 字符 -> 最终阶段", len(combined))
        
        # 最终阶段
        final_text = llm._generate(final_prompt.format(content=combined))

        return final_text
