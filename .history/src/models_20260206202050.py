"""数据模型定义 - 所有阶段间共享的数据类型"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional


class ElementType(Enum):
    """页面元素类型"""
    TITLE = "title"
    ABSTRACT = "abstract"
    EQUATIONS = "equations"
    TABLES = "tables"
    FIGURES = "figures"
    REFERENCES = "references"
    BODY_TEXT = "body_text"


class AnalysisType(Enum):
    """分析类型"""
    COMPREHENSIVE = "comprehensive"
    QUICK = "quick"
    METHODOLOGY_FOCUS = "methodology_focus"


class ReadStrategy(Enum):
    """阅读策略"""
    HIERARCHICAL = "hierarchical"  # 现有的：分层总结 (Map-Reduce)


@dataclass
class PageInfo:
    """单页信息 (阶段1输出)"""
    page_num: int
    image_path: Path
    width: int
    height: int


@dataclass
class PDFMetadata:
    """PDF 元信息"""
    title: str
    author: str
    total_pages: int
    file_path: Path


@dataclass
class PageContent:
    """单页 OCR 结果 (阶段2输出)"""
    page_num: int
    markdown: str
    detected_elements: List[ElementType] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class DocumentStructure:
    """文档结构索引"""
    title: str = ""
    abstract: str = ""
    sections: List[Dict] = field(default_factory=list)
    figures: List[Dict] = field(default_factory=list)
    tables: List[Dict] = field(default_factory=list)
    references_start_page: Optional[int] = None


@dataclass
class AssemblyResult:
    """阶段3输出"""
    full_markdown: str
    structure: DocumentStructure
    output_path: Path


from typing import Dict, List, Optional, Union


@dataclass
class AnalysisResult:
    """阶段4输出"""
    analysis_text: str
    analysis_type: Union[AnalysisType, str]
    model_name: str
    token_count: int = 0


@dataclass
class PipelineResult:
    """完整 Pipeline 输出"""
    metadata: PDFMetadata
    assembly: AssemblyResult
    analysis: AnalysisResult
    processing_time_seconds: float = 0.0
