from abc import ABC, abstractmethod
from src.models import DocumentStructure, ReadStrategy
from src.analysis.prompts import CHUNK_SUMMARY_PROMPT
from src.utils.logger import get_logger

logger = get_logger(__name__)


class AnalysisStrategy(ABC):
    """分析策略基类"""

    @abstractmethod
    def run(self, llm, chunks: List[str], final_prompt: str) -> str:
        """执行分析逻辑"""
        pass


class HierarchicalMapReduceStrategy(AnalysisStrategy):
    """分层 Map-Reduce 策略 (现有的默认策略)
    
    逻辑：逐块总结 -> 汇总总结 -> 最终生成
    """

    def run(self, llm, chunks: List[str], final_prompt: str) -> str:
        logger.info("执行分层 Map-Reduce 策略: %d 块待处理", len(chunks))

        # ── 自动提取关注点 ──
        intent_hint = "核心内容"
        first_line = final_prompt.strip().split("\n")[0]
        if "# " in first_line:
            intent_hint = first_line.replace("#", "").strip()
        elif "提示词" in first_line:
            intent_hint = "文中关键信息"
        
        logger.info("感知到分析目标: %s", intent_hint)

        # 第一轮：目标导向的逐块总结 (Map)
        summaries = []
        for i, chunk in enumerate(chunks):
            logger.info("  总结块 %d/%d (%d 字符)", i + 1, len(chunks), len(chunk))
            
            dynamic_chunk_prompt = (
                f"你正在协助进行一项关于「{intent_hint}」的深度分析。\n"
                f"请总结以下章节内容，**特别留意与「{intent_hint}」相关的细节**（300字内）：\n\n"
                f"{chunk}"
            )
            
            summary = llm._generate(dynamic_chunk_prompt)
            summaries.append(summary)

        # 第二轮：整合 (Reduce)
        combined = "\n\n".join(
            "### 第{}部分回顾\n{}".format(i + 1, s) for i, s in enumerate(summaries)
        )
        logger.info("整合总结: %d 字符 -> 最终阶段", len(combined))
        
        # 最终阶段
        final_text = llm._generate(final_prompt.format(content=combined))
        return final_text


class StrategyFactory:
    """策略工厂"""
    
    @staticmethod
    def get_strategy(strategy_type: Union[ReadStrategy, str]) -> AnalysisStrategy:
        # 统一转换为字符串比较
        s_val = strategy_type.value if isinstance(strategy_type, ReadStrategy) else strategy_type
        
        if s_val == ReadStrategy.HIERARCHICAL.value:
            return HierarchicalMapReduceStrategy()
        
        # 默认返回现有的
        logger.warning(f"未知的策略类型: {s_val}，将使用默认分层策略")
        return HierarchicalMapReduceStrategy()


class SectionBasedChunking:
    """基于章节的分块协调器"""

    def should_chunk(self, text: str, max_length: int = 50000) -> bool:
        """判断是否需要分块。"""
        return len(text) > max_length

    def split_by_sections(
        self, text: str, structure: DocumentStructure
    ) -> List[str]:
        """按章节分割文档。"""
        sections = structure.sections
        if not sections:
            return self._split_by_size(text)

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

        if split_points[0] > 0:
            preamble = text[:split_points[0]].strip()
            if preamble:
                chunks.insert(0, preamble)

        logger.info("按章节分块: %d 块", len(chunks))
        return chunks

    def _split_by_size(self, text: str, chunk_size: int = 30000) -> List[str]:
        """按固定字符数切分。"""
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            if end >= len(text):
                chunks.append(text[start:])
                break

            boundary = text.rfind("\n\n", start + chunk_size // 2, end)
            if boundary != -1:
                end = boundary

            chunks.append(text[start:end].strip())
            start = end

        logger.info("按大小分块: %d 块 (每块 ~%d 字符)", len(chunks), chunk_size)
        return chunks

    def execute_strategy(
        self, llm, chunks: List[str], final_prompt: str, strategy_type: str = "hierarchical"
    ) -> str:
        """执行指定的分析策略。"""
        strategy = StrategyFactory.get_strategy(strategy_type)
        return strategy.run(llm, chunks, final_prompt)
