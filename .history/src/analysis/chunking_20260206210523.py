from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List, Union
from src.models import DocumentStructure, ReadStrategy
from src.analysis.prompts import CHUNK_SUMMARY_PROMPT
from src.utils.logger import get_logger

logger = get_logger(__name__)


class AnalysisStrategy(ABC):
    """分析策略基类"""

    @abstractmethod
    def run(self, llm, chunks: List[str], final_prompt: str, max_tokens: int = 4096) -> str:
        """执行分析逻辑"""
        pass


class HierarchicalMapReduceStrategy(AnalysisStrategy):
    """分层 Map-Reduce 策略 (现有的默认策略)
    
    逻辑：逐块总结 -> 汇总总结 -> 最终生成
    """

    def run(self, llm, chunks: List[str], final_prompt: str, max_tokens: int = 4096) -> str:
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
            
            # 块总结使用固定长度，聚合阶段使用配置长度
            summary = llm._generate(dynamic_chunk_prompt, max_new_tokens=1024)
            summaries.append(summary)

        # 第二轮：整合 (Reduce)
        combined = "\n\n".join(
            "### 第{}部分回顾\n{}".format(i + 1, s) for i, s in enumerate(summaries)
        )
        logger.info("整合总结: %d 字符 -> 最终阶段", len(combined))
        
        # 最终阶段
        final_text = llm._generate(final_prompt.format(content=combined), max_new_tokens=max_tokens)
        return final_text


class AnchoredMapReduceStrategy(AnalysisStrategy):
    """带全局锚点的分块并行解析 (精度锚型)
    
    逻辑：
    1. 识别并提取 G-Anchor (摘要+引言) 作为“全局背景”。
    2. 后续每一块的分析都会注入这一背景，确保 AI 不迷路。
    3. 最终进行自洽性校验。
    """

    def run(self, llm, chunks: List[str], final_prompt: str, max_tokens: int = 4096) -> str:
        if not chunks:
            return "无内容可分析。"

        logger.info("执行「全局锚点」精度策略: %d 块待处理", len(chunks))

        # ── 阶段 1：提取全局锚点 (Global Anchoring) ──
        # 搜索包含引言或摘要的前两个块作为潜在锚点源
        anchor_chunks = []
        other_chunks = []
        for i, chunk in enumerate(chunks):
            chunk_low = chunk[:500].lower()
            if i <= 1 or "abstract" in chunk_low or "introduction" in chunk_low:
                anchor_chunks.append(chunk)
            else:
                other_chunks.append(chunk)

        anchor_source = "\n\n".join(anchor_chunks)
        logger.info("  正在固化全局锚点 (源长度: %d)...", len(anchor_source))
        
        anchor_prompt = (
            "你是一个资深学术评审，请从以下论文开篇内容中提取「全局锚点 (Global Anchors)」。\n"
            "锚点必须包含：1.研究的核心矛盾；2.本文提出的核心创新点；3.最重要的数学定义/符号。\n"
            "输出必须精炼，作为后续解析的常驻内存（300字内）。\n\n"
            f"{anchor_source}"
        )
        global_anchor = llm._generate(anchor_prompt, max_new_tokens=1024)
        logger.info("  全局锚点已就绪: %s...", global_anchor[:100].replace("\n", " "))

        # ── 阶段 2：局部精读 (Anchored Map) ──
        insights = []
        # 将锚点也作为第一个片段放入结果
        insights.append(f"### 全局锚点 (核心目标)\n{global_anchor}")

        for i, chunk in enumerate(other_chunks):
            logger.info("  精读块 %d/%d (带锚点注入)...", i + 1, len(other_chunks))
            
            # 识别当前块的章节名（简单提取第一行）
            title_guess = chunk.split("\n")[0].strip("# ")
            
            anchored_map_prompt = (
                f"【全局锚点/研究目标】：\n{global_anchor}\n\n"
                f"--- 当前章节：{title_guess} ---\n"
                "请基于以上全局锚点，深度解析当前内容。如果是方法论，请精准提取逻辑与变量；"
                "如果是实验，请分析其是否支撑了锚点目标。输出高密度见解（400字内）：\n\n"
                f"{chunk}"
            )
            
            local_insight = llm._generate(anchored_map_prompt, max_new_tokens=1024)
            insights.append(f"### 章节解析: {title_guess}\n{local_insight}")

        # ── 阶段 3：全局合成 (Final Reduce) ──
        combined_insights = "\n\n".join(insights)
        logger.info("进入最后聚合阶段 (因果链校验)...")
        
        # 最终 Prompt 需要包含交叉验证的指令
        cross_check_prompt = (
            f"你正在整合一份高精度的论文解读报告。以下是基于「全局锚点」提取的各章节见解：\n\n"
            f"{combined_insights}\n\n"
            "请完成最终报告，除了各章节总结外，**特别注意逻辑自洽性校验**：\n"
            "1. B2 的模型假设是否在 B3 的实验中得到了验证？\n"
            "2. 最终结论是否完美回应了「全局锚点」中的核心矛盾？\n\n"
            f"最终要求：{final_prompt}"
        )
        
        # 剔除 final_prompt 中可能存在的占位符映射
        final_text = llm._generate(cross_check_prompt.replace("{content}", combined_insights), max_new_tokens=max_tokens)
        return final_text


class StrategyFactory:
    """策略工厂"""
    
    @staticmethod
    def get_strategy(strategy_type: Union[ReadStrategy, str]) -> AnalysisStrategy:
        # 统一转换为字符串比较
        s_val = strategy_type.value if isinstance(strategy_type, ReadStrategy) else strategy_type
        
        if s_val == ReadStrategy.HIERARCHICAL.value:
            return HierarchicalMapReduceStrategy()
        if s_val == ReadStrategy.ANCHORED.value:
            return AnchoredMapReduceStrategy()
        
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

        # 按 start_pos 排序，只取 level == 1 的主章节作为切分点
        # 这样通常一篇论文只会分成 4-6 个大块（Introduction, Methods, Results, Discussion, Conclusion 等）
        split_points = sorted(
            [s["start_pos"] for s in sections if s["level"] == 1]
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
        self, llm, chunks: List[str], final_prompt: str, strategy_type: str = "hierarchical", max_tokens: int = 4096
    ) -> str:
        """执行指定的分析策略。"""
        strategy = StrategyFactory.get_strategy(strategy_type)
        return strategy.run(llm, chunks, final_prompt, max_tokens=max_tokens)
