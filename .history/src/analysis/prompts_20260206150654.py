"""Prompt 模板管理"""

from __future__ import annotations

from src.models import AnalysisType

# ── 综合分析 ──
COMPREHENSIVE_PROMPT = """\
# Role
你是一位资深科研专家，具备极强的学术严谨性、数学建模直觉和算法工程化能力。请对以下论文进行全方位的“解剖级”分析：

## 核心任务

### 0. 摘要对齐 (Abstract)
- 输出论文英文摘要原文。
- 提供术语精准、符合中文学术惯例的翻译（重点关注核心算法名词的准确性）。

### 1. 研究问题与建模逻辑 (Problem & Modeling)
- **核心挑战**：论文试图解决什么本质问题？其计算复杂性（NP-hard 性质）体现在哪里？
- **数学架构**：提取其核心数学模型（如决策变量、目标函数、关键约束）。如果是分解算法，请说明主/子问题的逻辑耦合点。
- **创新维度**：该文是在建模方式上创新，还是在求解技术（如新的割平面、分支策略）上创新？
- **[引用要求]**：引用至少 2 处定义核心模型或逻辑跳转的原文。

### 2. 求解算法动力学 (Algorithm Dynamics)
- **技术路径**：算法的执行流程是什么？它如何平衡“解的质量”与“计算时间”？
- **加速机制**：文中采取了哪些手段来加速收敛（如对称性破除、启发式初值、强剪枝逻辑）？
- **收敛性分析**：分析实验中表现出的收敛曲线或 Gap 变化规律，识别算法在何种规模下会遭遇性能瓶颈。

### 3. 工程实现与计算特性 (Implementation & Efficiency)
- **算力分布**：识别算法中最耗费 CPU/GPU 资源的部分。
- **并行化潜力**：分析该算法是否具备天然的并行结构（如独立子问题、大规模矩阵运算）。基于高性能计算（HPC）视角，评估其在大规模算力下的扩展性。
- **[引用要求]**：引用至少 2 处描述实验环境、算法效率或瓶颈分析的原文。

### 4. 科研启发与迁移价值 (Research Insight)
- **方法论迁移**：文中的建模技巧或割平面逻辑，是否可以抽象出来应用到其他相似结构的组合优化问题中？
- **技术复用**：识别文中可复用的算法组件（如特定的 Pricing 逻辑、Benders Cut 类型）。
- **后续研究**：如果我要在此基础上进一步突破，最值得深挖的“痛点”或“盲点”是什么？

### 5. 批判性评价 (Critical Review)
- **局限性**：指出其实验设计是否存在过拟合、数据集是否具有代表性、或者模型假设是否过于理想化。
- **未来方向**：根据当前技术趋势（如 AI + OR、高性能并行计算），提出可能的改进建议。

## 格式要求
1. 每个分析要点须标注章节出处（例：Section 4.2）。
2. 关键论述引用原文格式：> "original text" — Section X.X
3. 重点加粗技术术语，保持段落 scannability。

## 待分析内容：
{content}
"""

# ── 快速总结 ──
QUICK_PROMPT = """\
快速总结这篇论文的：

### 0. 论文摘要
- 首先输出论文的英文原文摘要（Abstract 原文，保持原样）
- 然后输出对应的中文翻译摘要

### 1. 一句话概括（200字内）
### 2. 核心贡献（3点）
### 3. 关键结果

## 引用要求
- 关键论述请引用英文原文，格式：> "original text" — Section X.X

论文内容：
{content}
"""

# ── 方法论聚焦 ──
METHODOLOGY_PROMPT = """\
专注分析这篇论文的方法论：

### 0. 论文摘要
- 首先输出论文的英文原文摘要（Abstract 原文，保持原样）
- 然后输出对应的中文翻译摘要

### 1. 问题建模（目标函数、约束条件）
### 2. 求解算法的详细步骤
### 3. 算法复杂度分析
### 4. 参数设置

## 引用要求
- 每个分析要点请标注出处章节（如 Section 3.2）
- 关键论述请引用英文原文，格式：> "original text" — Section X.X
- 方法论部分至少提供 3-5 处原文引用

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
