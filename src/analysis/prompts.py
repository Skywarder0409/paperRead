"""Prompt 模板管理"""

from __future__ import annotations

from src.models import AnalysisType

# ── 综合分析 ──
COMPREHENSIVE_PROMPT = """\
作为运筹学领域的研究者，请深度分析这篇论文：

## 需要输出的内容：

### 1. 论文概述
- 研究问题是什么？
- 属于哪个细分领域？

### 2. 方法论分析
- 核心算法/模型是什么？
- 创新点在哪里？
- 与现有方法（如Tabu Search, ALNS）的关系？

### 3. 实验设计
- 使用了什么benchmark？
- 对比了哪些baseline？
- 关键实验结果？

### 4. 对我研究的启发
- 对PASP问题有什么可借鉴之处？
- 是否有可复用的技术组件？

### 5. 局限性与未来方向

论文内容如下：
{content}
"""

# ── 快速总结 ──
QUICK_PROMPT = """\
快速总结这篇论文的：
1. 一句话概括（200字内）
2. 核心贡献（3点）
3. 关键结果

论文内容：
{content}
"""

# ── 方法论聚焦 ──
METHODOLOGY_PROMPT = """\
专注分析这篇论文的方法论：
1. 问题建模（目标函数、约束条件）
2. 求解算法的详细步骤
3. 算法复杂度分析
4. 参数设置

论文内容：
{content}
"""

# ── 分块总结用的中间 prompt ──
CHUNK_SUMMARY_PROMPT = "总结以下章节的核心内容（200字内）：\n{content}"

# 模板映射
_PROMPT_MAP = {
    AnalysisType.COMPREHENSIVE: COMPREHENSIVE_PROMPT,
    AnalysisType.QUICK: QUICK_PROMPT,
    AnalysisType.METHODOLOGY_FOCUS: METHODOLOGY_PROMPT,
}


def get_prompt(analysis_type: AnalysisType) -> str:
    """获取指定分析类型的 prompt 模板。

    Args:
        analysis_type: 分析类型

    Returns:
        包含 {content} 占位符的 prompt 字符串
    """
    return _PROMPT_MAP[analysis_type]
