"""报告生成 - 将 PipelineResult 输出为可读报告"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from src.models import PipelineResult
from src.utils.file_ops import ensure_dir, safe_write_text, safe_write_json
from src.utils.logger import get_logger

logger = get_logger(__name__)


def generate_report(result: PipelineResult, output_dir: Path) -> None:
    """生成完整的输出报告（Markdown 摘要 + JSON 数据）。

    输出文件:
        {output_dir}/{title}_summary.md   - 人类可读的分析报告
        {output_dir}/{title}_analysis.json - 结构化分析数据
    """
    output_dir = Path(output_dir)
    ensure_dir(output_dir)

    safe_name = _sanitize(result.metadata.title)

    # ── Markdown 摘要报告 ──
    md = _build_markdown_report(result)
    md_path = output_dir / "{}_summary.md".format(safe_name)
    safe_write_text(md_path, md)
    logger.info("摘要报告: %s", md_path)

    # ── JSON 数据 ──
    data = _build_json_data(result)
    json_path = output_dir / "{}_analysis.json".format(safe_name)
    safe_write_json(json_path, data)
    logger.info("分析数据: %s", json_path)


def _build_markdown_report(result: PipelineResult) -> str:
    meta = result.metadata
    analysis = result.analysis
    structure = result.assembly.structure

    lines = [
        "# {} - 分析报告".format(meta.title),
        "",
        "> 自动生成于 {}".format(datetime.now().strftime("%Y-%m-%d %H:%M")),
        "",
        "| 项目 | 值 |",
        "|------|-----|",
        "| 作者 | {} |".format(meta.author or "未知"),
        "| 总页数 | {} |".format(meta.total_pages),
        "| 分析模式 | {} |".format(analysis.analysis_type.value),
        "| 使用模型 | {} |".format(analysis.model_name),
        "| 处理耗时 | {:.1f} 秒 |".format(result.processing_time_seconds),
        "",
    ]

    # 摘要
    if structure.abstract:
        lines.extend([
            "## 论文摘要",
            "",
            structure.abstract,
            "",
        ])

    # 文档结构概览
    if structure.sections:
        lines.extend(["## 文档结构", ""])
        for s in structure.sections:
            indent = "  " * (s["level"] - 1)
            lines.append("{}- {}".format(indent, s["title"]))
        lines.append("")

    # LLM 分析结果
    lines.extend([
        "## 分析结果",
        "",
        analysis.analysis_text,
        "",
        "---",
        "*由本地文献解读 Pipeline 自动生成*",
    ])

    return "\n".join(lines)


def _build_json_data(result: PipelineResult) -> dict:
    meta = result.metadata
    analysis = result.analysis
    structure = result.assembly.structure

    return {
        "metadata": {
            "title": meta.title,
            "author": meta.author,
            "total_pages": meta.total_pages,
            "source_file": str(meta.file_path),
        },
        "structure": {
            "title": structure.title,
            "abstract": structure.abstract,
            "sections": structure.sections,
            "figures_count": len(structure.figures),
            "tables_count": len(structure.tables),
            "references_start_page": structure.references_start_page,
        },
        "analysis": {
            "type": analysis.analysis_type.value,
            "model": analysis.model_name,
            "token_count": analysis.token_count,
            "text": analysis.analysis_text,
        },
        "processing": {
            "time_seconds": result.processing_time_seconds,
            "generated_at": datetime.now().isoformat(),
            "structured_doc": str(result.assembly.output_path),
        },
    }


def _sanitize(name: str, max_len: int = 80) -> str:
    safe = name.replace("/", "_").replace("\\", "_").replace(":", "_")
    safe = safe.replace("?", "").replace("*", "").replace('"', "")
    safe = safe.replace("<", "").replace(">", "").replace("|", "")
    safe = safe.strip(". ")
    return (safe or "paper")[:max_len]
