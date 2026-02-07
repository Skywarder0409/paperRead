"""主编排器 - 串联4个阶段"""

from __future__ import annotations

import time
from pathlib import Path
from typing import List, Optional, Union

from src.config import PipelineConfig
from src.models import (
    AnalysisType,
    PipelineResult,
)
from src.utils.file_ops import get_file_hash, ensure_dir
from src.utils.gpu_manager import log_gpu_status, release_gpu_memory
from src.utils.logger import get_logger

logger = get_logger(__name__)


class Pipeline:
    """文献解读 Pipeline，按顺序调用4个阶段。

    显存使用时序：
        阶段1: ~0 GB (CPU only)
        阶段2: ~16-20 GB (OCR 模型) → 卸载
        阶段3: ~0 GB (CPU only)
        阶段4: ~20-24 GB (LLM 模型) → 卸载
    """

    def __init__(self, config: Optional[PipelineConfig] = None) -> None:
        self.config = config or PipelineConfig()
        self.config.ensure_dirs()

    def run(
        self,
        pdf_path: Path,
        analysis_type: Union[AnalysisType, str] = AnalysisType.COMPREHENSIVE,
        start_stage: int = 1,
    ) -> PipelineResult:
        """执行完整 Pipeline。

        Args:
            pdf_path: PDF 文件路径或已有的 structured.md 路径（配合 start_stage=4）
            analysis_type: 分析类型
            start_stage: 起始阶段 (1-4)，可跳过已完成的阶段
        """
        t0 = time.time()
        display_mode = analysis_type.value if isinstance(analysis_type, AnalysisType) else analysis_type
        logger.info("Pipeline 开始: %s (模式=%s, 起始阶段=%d)", pdf_path, display_mode, start_stage)
        
        pdf_path = Path(pdf_path)
        
        # ── 深度缓存检查 ──
        # 如果是 PDF 且从阶段 1 开始，检查是否有缓存的结构化文档
        use_cache = False
        cache_metadata = None
        cache_assembly = None
        
        if pdf_path.suffix.lower() == ".pdf" and start_stage <= 1:
            pdf_hash = get_file_hash(pdf_path)
            pipeline_cache_dir = ensure_dir(Path("cache/pipeline_cache") / pdf_hash)
            cached_md = pipeline_cache_dir / "structured.md"
            cached_meta = pipeline_cache_dir / "metadata.json"
            
            if cached_md.exists() and cached_meta.exists():
                logger.info("检测到结构化文档缓存，跳过阶段 1-3")
                from src.utils.file_ops import read_json
                from src.models import PDFMetadata, AssemblyResult, DocumentStructure
                from src.assembly.section_parser import RegexSectionParser
                
                meta_dict = read_json(cached_meta)
                cache_metadata = PDFMetadata(**meta_dict)
                full_md = cached_md.read_text(encoding="utf-8")
                
                parser = RegexSectionParser()
                structure = parser.build_structure_index([], full_md)
                cache_assembly = AssemblyResult(
                    full_markdown=full_md, 
                    structure=structure, 
                    output_path=cached_md
                )
                use_cache = True
                start_stage = 4 # 跳到阶段 4

        # ── 阶段1：PDF 预处理 ──
        if start_stage <= 1:
            logger.info("=== 阶段1: PDF 预处理 ===")
            from src.preprocess.preprocess import PyMuPDFPreprocessor

            preprocessor = PyMuPDFPreprocessor()
            pdf_path = Path(pdf_path)
            pages = preprocessor.extract_pages(pdf_path, self.config.cache_dir, self.config.dpi)
            metadata = preprocessor.get_metadata(pdf_path)
            logger.info("阶段1 完成: %d 页已提取", len(pages))
        elif use_cache:
            metadata = cache_metadata
            pages = None # 缓存模式下不需要图片
        else:
            pages = None
            metadata = None

        # ── 阶段2：OCR 与理解 ──
        if start_stage <= 2:
            logger.info("=== 阶段2: OCR 与理解 ===")
            log_gpu_status("阶段2-开始")
            from src.utils.ollama_manager import ensure_ollama_parallelism
            ensure_ollama_parallelism(self.config.ocr_parallel_threads)

            ocr_engine = VisionOCREngine()
            ocr_engine.load_model(self.config.ocr_model)
            page_contents = ocr_engine.process_all_pages(pages, parallel_threads=self.config.ocr_parallel_threads)
            ocr_engine.unload_model()
            if self.config.unload_after_stage:
                release_gpu_memory()
            log_gpu_status("阶段2-结束")
            logger.info("阶段2 完成: %d 页已处理", len(page_contents))
        else:
            page_contents = None

        # ── 阶段3：文档整合 ──
        if start_stage <= 3:
            logger.info("=== 阶段3: 文档整合 ===")
            from src.assembly.assembler import MarkdownAssembler

            assembler = MarkdownAssembler()
            assembly_result = assembler.assemble(page_contents, metadata, self.config.output_dir)
            logger.info("阶段3 完成: 输出 -> %s", assembly_result.output_path)
            
            # 保存到 Pipeline 级别缓存
            if not use_cache and pdf_path.suffix.lower() == ".pdf":
                try:
                    pdf_hash = get_file_hash(pdf_path)
                    pipeline_cache_dir = ensure_dir(Path("cache/pipeline_cache") / pdf_hash)
                    from src.utils.file_ops import safe_write_text, safe_write_json
                    import dataclasses
                    safe_write_text(pipeline_cache_dir / "structured.md", assembly_result.full_markdown)
                    safe_write_json(pipeline_cache_dir / "metadata.json", dataclasses.asdict(metadata))
                    logger.info("结构化文档已缓存: %s", pdf_hash)
                except Exception as e:
                    logger.warning("存档 Pipeline 缓存失败: %s", e)
        elif use_cache:
            assembly_result = cache_assembly
        else:
            # 从已有的 structured.md 开始
            from src.assembly.section_parser import RegexSectionParser
            from src.models import AssemblyResult, PDFMetadata

            md_path = Path(pdf_path)
            full_md = md_path.read_text(encoding="utf-8")
            parser = RegexSectionParser()
            structure = parser.build_structure_index([], full_md)
            assembly_result = AssemblyResult(
                full_markdown=full_md, structure=structure, output_path=md_path
            )
            metadata = PDFMetadata(
                title=structure.title or md_path.stem,
                author="",
                total_pages=0,
                file_path=md_path,
            )
            logger.info("阶段3 跳过: 使用已有文档 %s", md_path)

        # ── 阶段4：LLM 深度分析 ──
        logger.info("=== 阶段4: LLM 深度分析 ===")
        log_gpu_status("阶段4-开始")
        from src.analysis.llm_engine import TransformersLLMEngine
        from src.analysis.chunking import SectionBasedChunking

        llm = TransformersLLMEngine()
        llm.load_model(self.config.llm_model)

        chunking = SectionBasedChunking()
        if chunking.should_chunk(assembly_result.full_markdown, self.config.max_text_length):
            logger.info("文档过长，启用分块策略")
            from src.analysis.prompts import get_prompt
            chunks = chunking.split_by_sections(
                assembly_result.full_markdown, assembly_result.structure
            )
            final_prompt = get_prompt(analysis_type if not isinstance(analysis_type, AnalysisType) else analysis_type.value)
            analysis_text = chunking.hierarchical_summarize(llm, chunks, final_prompt)
            from src.models import AnalysisResult
            analysis_result = AnalysisResult(
                analysis_text=analysis_text,
                analysis_type=analysis_type,
                model_name=self.config.llm_model,
            )
        else:
            analysis_result = llm.analyze(
                assembly_result.full_markdown,
                assembly_result.structure,
                analysis_type,
                self.config.max_tokens,
            )

        llm.unload_model()
        if self.config.unload_after_stage:
            release_gpu_memory()
        log_gpu_status("阶段4-结束")
        logger.info("阶段4 完成")

        elapsed = time.time() - t0
        result = PipelineResult(
            metadata=metadata,
            assembly=assembly_result,
            analysis=analysis_result,
            processing_time_seconds=round(elapsed, 2),
        )

        # 生成报告
        from src.utils.report_generator import generate_report
        generate_report(result, self.config.output_dir)

        logger.info("Pipeline 完成，耗时 %.1f 秒", elapsed)
        return result

    def batch_run(
        self,
        pdf_dir: Path,
        analysis_type: Union[AnalysisType, str] = AnalysisType.QUICK,
    ) -> List[PipelineResult]:
        """批量处理目录下所有 PDF。"""
        pdfs = sorted(Path(pdf_dir).glob("*.pdf"))
        if not pdfs:
            logger.warning("目录 %s 中未找到 PDF 文件", pdf_dir)
            return []

        logger.info("批量处理: 找到 %d 个 PDF", len(pdfs))
        results = []
        for i, pdf in enumerate(pdfs, 1):
            logger.info("--- [%d/%d] %s ---", i, len(pdfs), pdf.name)
            try:
                r = self.run(pdf, analysis_type)
                results.append(r)
            except Exception:
                logger.exception("处理失败: %s", pdf.name)
        return results
