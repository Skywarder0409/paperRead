"""阶段4 接口定义：LLM 深度分析"""

from __future__ import annotations

from typing import List

from typing_extensions import Protocol, runtime_checkable

from src.models import AnalysisResult, AnalysisType, DocumentStructure


@runtime_checkable
class LLMEngineProtocol(Protocol):
    """LLM 引擎接口。

    负责加载 LLM 模型，对文档进行深度分析。
    模型使用完毕后应卸载以释放显存。
    """

    def load_model(self, model_name: str) -> None:
        """加载 LLM 模型到 GPU。

        Args:
            model_name: 模型名称，如 "qwen3-30b-a3b"

        Raises:
            RuntimeError: 模型加载失败或显存不足

        Example:
            >>> llm = TransformersLLMEngine()
            >>> llm.load_model("qwen3-30b-a3b")
        """
        ...

    def analyze(
        self,
        full_markdown: str,
        structure: DocumentStructure,
        analysis_type: AnalysisType = AnalysisType.COMPREHENSIVE,
        max_tokens: int = 4096,
    ) -> AnalysisResult:
        """对文档进行深度分析。

        Args:
            full_markdown: 完整的结构化 Markdown 文本
            structure: 文档结构索引
            analysis_type: 分析类型（综合/快速/方法论）
            max_tokens: 最大生成 token 数

        Returns:
            AnalysisResult，包含分析文本、分析类型、模型名、token 数

        Raises:
            RuntimeError: 模型未加载

        Example:
            >>> result = llm.analyze(md_text, struct, AnalysisType.QUICK)
            >>> print(result.analysis_text[:200])
        """
        ...

    def unload_model(self) -> None:
        """卸载模型，释放 GPU 显存。

        Example:
            >>> llm.unload_model()
        """
        ...


@runtime_checkable
class ChunkingStrategyProtocol(Protocol):
    """长文档分块策略接口。

    当文档过长无法一次送入 LLM 时，提供分块和分层总结能力。
    """

    def should_chunk(self, text: str, max_length: int = 50000) -> bool:
        """判断是否需要分块处理。

        Args:
            text: 待检查文本
            max_length: 字符数阈值

        Returns:
            True 表示需要分块

        Example:
            >>> strategy = SectionBasedChunking()
            >>> strategy.should_chunk("short text")
            False
        """
        ...

    def split_by_sections(
        self, text: str, structure: DocumentStructure
    ) -> List[str]:
        """按章节分割文档。

        Args:
            text: 完整 Markdown 文本
            structure: 文档结构索引

        Returns:
            文本块列表，每块对应一个或多个章节

        Example:
            >>> chunks = strategy.split_by_sections(md_text, struct)
            >>> len(chunks) > 0
            True
        """
        ...

    def hierarchical_summarize(
        self, llm: LLMEngineProtocol, chunks: List[str], final_prompt: str
    ) -> str:
        """分层总结：先各块独立总结，再整合。

        Args:
            llm: LLM 引擎实例
            chunks: 文本块列表
            final_prompt: 最终整合用的 prompt

        Returns:
            最终分析文本

        Example:
            >>> text = strategy.hierarchical_summarize(llm, chunks, prompt)
        """
        ...
