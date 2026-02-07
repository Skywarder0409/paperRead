"""Pipeline 异步包装器 - 拦截日志，推送 SSE 进度事件"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import PipelineConfig
from src.models import AnalysisType

_wrapper_logger = logging.getLogger("src.web.pipeline_wrapper")


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ProgressEvent:
    stage: int = 0
    stage_name: str = ""
    detail: str = ""
    page: int = 0
    total_pages: int = 0
    chunk: int = 0
    total_chunks: int = 0
    progress: float = 0.0
    file_index: int = 0      # 当前第几篇（从 1 开始）
    file_total: int = 0      # 总共几篇
    file_title: str = ""     # 当前论文文件名（去掉 .pdf 后缀）

    def to_dict(self) -> dict:
        return {
            "stage": self.stage,
            "stage_name": self.stage_name,
            "detail": self.detail,
            "page": self.page,
            "total_pages": self.total_pages,
            "chunk": self.chunk,
            "total_chunks": self.total_chunks,
            "progress": self.progress,
            "file_index": self.file_index,
            "file_total": self.file_total,
            "file_title": self.file_title,
        }


@dataclass
class Job:
    job_id: str
    status: JobStatus = JobStatus.PENDING
    pdf_paths: List[Path] = field(default_factory=list)
    analysis_type: AnalysisType = AnalysisType.COMPREHENSIVE
    ocr_model: str = ""
    llm_model: str = ""
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue())
    last_progress: Optional[ProgressEvent] = None  # 最新进度快照（供刷新恢复）
    result_markdown: str = ""
    result_json: dict = field(default_factory=dict)
    error: str = ""
    submitted_at: str = ""  # ISO 格式的提交时间


# 全局任务存储
_jobs: Dict[str, Job] = {}
_executor = ThreadPoolExecutor(max_workers=2)

# 阶段权重，用于计算总进度
_STAGE_WEIGHTS = {1: 0.05, 2: 0.45, 3: 0.05, 4: 0.45}
_STAGE_NAMES = {1: "PDF预处理", 2: "OCR识别", 3: "文档整合", 4: "LLM深度分析"}


class ProgressHandler(logging.Handler):
    """拦截 pipeline 日志，解析为进度事件写入 asyncio.Queue。

    挂载到 "src" 父 logger，通过 propagation 机制捕获所有子模块日志，
    不干扰子 logger 自身的 handler 初始化。
    """

    # 日志匹配模式
    _RE_STAGE = re.compile(r"=== 阶段(\d): (.+?) ===")
    _RE_STAGE_DONE = re.compile(r"阶段(\d) 完成")
    _RE_OCR_PAGE = re.compile(r"\[(\d+)/(\d+)\] 页面 \d+ 完成")
    _RE_CHUNK = re.compile(r"总结块 (\d+)/(\d+)")
    _RE_PIPELINE_DONE = re.compile(r"Pipeline 完成，耗时 ([\d.]+) 秒")
    _RE_LLM_ANALYZE = re.compile(r"开始 LLM 分析")
    _RE_LLM_DONE = re.compile(r"LLM 分析完成")
    _RE_MODEL_LOADING = re.compile(r"验证 Ollama (OCR|LLM) 模型: (.+)")
    _RE_MODEL_READY = re.compile(r"(OCR|LLM) 模型已就绪")

    def __init__(self, job: Job, loop: asyncio.AbstractEventLoop):
        super().__init__(level=logging.DEBUG)
        self._job = job
        self._queue = job.queue
        self._loop = loop
        self._current_stage = 0
        self._total_pages = 0
        self._file_index = 0
        self._file_total = 0
        self._file_title = ""

    def set_file_info(self, index: int, total: int, title: str) -> None:
        """设置当前处理的文件信息（从线程池中调用）"""
        self._file_index = index
        self._file_total = total
        self._file_title = title
        self._current_stage = 0

    def _apply_file_info(self, event: ProgressEvent) -> ProgressEvent:
        """为事件附加文件信息，并将进度映射到多文件整体进度"""
        event.file_index = self._file_index
        event.file_total = self._file_total
        event.file_title = self._file_title
        if self._file_total > 1 and event.progress >= 0:
            single = event.progress
            event.progress = round(
                (self._file_index - 1 + single) / self._file_total, 3
            )
        return event

    def emit(self, record: logging.LogRecord) -> None:
        msg = record.getMessage()
        event = self._parse(msg)
        if event:
            event = self._apply_file_info(event)
            self._job.last_progress = event
            try:
                self._loop.call_soon_threadsafe(self._queue.put_nowait, event)
            except RuntimeError:
                # loop 已关闭
                pass

    def _parse(self, msg: str) -> Optional[ProgressEvent]:
        # 阶段开始
        m = self._RE_STAGE.search(msg)
        if m:
            self._current_stage = int(m.group(1))
            stage_name = m.group(2)
            base = sum(_STAGE_WEIGHTS.get(i, 0) for i in range(1, self._current_stage))
            return ProgressEvent(
                stage=self._current_stage,
                stage_name=stage_name,
                detail=f"开始{stage_name}",
                progress=round(base, 3),
            )

        # 模型加载
        m = self._RE_MODEL_LOADING.search(msg)
        if m:
            model_type = m.group(1)
            model_name = m.group(2)
            stage = 2 if model_type == "OCR" else 4
            base = sum(_STAGE_WEIGHTS.get(i, 0) for i in range(1, stage))
            return ProgressEvent(
                stage=stage,
                stage_name=_STAGE_NAMES.get(stage, ""),
                detail=f"加载{model_type}模型: {model_name}",
                progress=round(base + 0.01, 3),
            )

        # 模型就绪
        m = self._RE_MODEL_READY.search(msg)
        if m:
            model_type = m.group(1)
            stage = 2 if model_type == "OCR" else 4
            base = sum(_STAGE_WEIGHTS.get(i, 0) for i in range(1, stage))
            return ProgressEvent(
                stage=stage,
                stage_name=_STAGE_NAMES.get(stage, ""),
                detail=f"{model_type}模型已就绪",
                progress=round(base + 0.02, 3),
            )

        # OCR 页面进度
        m = self._RE_OCR_PAGE.search(msg)
        if m:
            page, total = int(m.group(1)), int(m.group(2))
            self._total_pages = total
            base = sum(_STAGE_WEIGHTS.get(i, 0) for i in range(1, 2))
            stage_prog = page / total if total else 0
            progress = base + _STAGE_WEIGHTS[2] * stage_prog
            return ProgressEvent(
                stage=2,
                stage_name="OCR识别",
                detail=f"第 {page}/{total} 页",
                page=page,
                total_pages=total,
                progress=round(progress, 3),
            )

        # 分块总结进度
        m = self._RE_CHUNK.search(msg)
        if m:
            chunk, total = int(m.group(1)), int(m.group(2))
            base = sum(_STAGE_WEIGHTS.get(i, 0) for i in range(1, 4))
            stage_prog = chunk / total if total else 0
            progress = base + _STAGE_WEIGHTS[4] * stage_prog
            return ProgressEvent(
                stage=4,
                stage_name="LLM深度分析",
                detail=f"总结块 {chunk}/{total}",
                chunk=chunk,
                total_chunks=total,
                progress=round(progress, 3),
            )

        # LLM 分析开始
        m = self._RE_LLM_ANALYZE.search(msg)
        if m:
            base = sum(_STAGE_WEIGHTS.get(i, 0) for i in range(1, 4))
            return ProgressEvent(
                stage=4,
                stage_name="LLM深度分析",
                detail="LLM 分析中...",
                progress=round(base + 0.05, 3),
            )

        # 阶段完成
        m = self._RE_STAGE_DONE.search(msg)
        if m:
            stage = int(m.group(1))
            base = sum(_STAGE_WEIGHTS.get(i, 0) for i in range(1, stage + 1))
            return ProgressEvent(
                stage=stage,
                stage_name=_STAGE_NAMES.get(stage, ""),
                detail=f"阶段{stage}完成",
                progress=round(base, 3),
            )

        # Pipeline 完成
        m = self._RE_PIPELINE_DONE.search(msg)
        if m:
            return ProgressEvent(
                stage=4,
                stage_name="完成",
                detail=f"处理完成，耗时 {m.group(1)} 秒",
                progress=1.0,
            )

        return None


def create_job(
    pdf_paths: List[Path],
    analysis_type: AnalysisType,
    ocr_model: str,
    llm_model: str,
) -> Job:
    job_id = uuid.uuid4().hex[:12]
    job = Job(
        job_id=job_id,
        pdf_paths=pdf_paths,
        analysis_type=analysis_type,
        ocr_model=ocr_model,
        llm_model=llm_model,
        submitted_at=datetime.now().isoformat(),
    )
    _jobs[job_id] = job
    return job


def get_job(job_id: str) -> Optional[Job]:
    return _jobs.get(job_id)


async def run_job(job: Job) -> None:
    """在线程池中执行 Pipeline，通过日志拦截推送进度"""
    loop = asyncio.get_running_loop()
    handler = ProgressHandler(job, loop)

    # 挂载到 "src" 父 logger —— 所有 src.* 子 logger 的消息通过 propagation 上传到此
    # 这样不会干扰子 logger 自身的 handler 初始化（get_logger 中的 if logger.handlers 检查）
    src_logger = logging.getLogger("src")
    src_logger.setLevel(logging.DEBUG)
    src_logger.addHandler(handler)

    job.status = JobStatus.RUNNING

    # 推送一个初始事件，让前端立刻收到反馈
    try:
        job.queue.put_nowait(ProgressEvent(
            stage=0, stage_name="启动", detail="正在初始化 Pipeline...", progress=0.0
        ))
    except Exception:
        pass

    try:
        result = await loop.run_in_executor(
            _executor, _run_pipeline_sync, job, handler, loop
        )
        # 构建结果
        from src.utils.report_generator import _build_markdown_report, _build_json_data
        job.result_markdown = _build_markdown_report(result)
        job.result_json = _build_json_data(result)
        # 注入提交时间到 processing 字段
        job.result_json.setdefault("processing", {})["submitted_at"] = job.submitted_at
        job.status = JobStatus.COMPLETED
    except Exception as e:
        job.error = str(e)
        job.status = JobStatus.FAILED
        _wrapper_logger.exception("Pipeline 执行失败: %s", e)
        try:
            job.queue.put_nowait(
                ProgressEvent(stage=0, stage_name="错误", detail=str(e), progress=-1)
            )
        except Exception:
            pass
    finally:
        src_logger.removeHandler(handler)
        # 发送终止信号
        try:
            job.queue.put_nowait(None)
        except Exception:
            pass


def _run_pipeline_sync(
    job: Job,
    handler: ProgressHandler,
    loop: asyncio.AbstractEventLoop,
) -> Any:
    """同步执行 Pipeline（在线程池中调用）"""
    from src.pipeline import Pipeline

    config = PipelineConfig(
        ocr_model=job.ocr_model,
        llm_model=job.llm_model,
    )
    pipeline = Pipeline(config)
    total = len(job.pdf_paths)

    results = []
    for idx, pdf_path in enumerate(job.pdf_paths, 1):
        title = pdf_path.stem
        handler.set_file_info(idx, total, title)
        # 发送文件切换事件
        if total > 1:
            event = ProgressEvent(
                stage=0,
                stage_name="切换论文",
                detail=f"开始处理: {title}",
                file_index=idx,
                file_total=total,
                file_title=title,
                progress=round((idx - 1) / total, 3),
            )
            try:
                loop.call_soon_threadsafe(job.queue.put_nowait, event)
            except RuntimeError:
                pass
        r = pipeline.run(pdf_path, job.analysis_type)
        
        # ── 论文重命名 ──
        # 将 papers/ 目录下的 PDF 文件重命名为分析出的论文标题
        try:
            from src.utils.report_generator import _sanitize
            safe_title = _sanitize(r.metadata.title)
            new_filename = f"{safe_title}.pdf"
            papers_dir = Path("papers")
            
            # 找到 papers/ 下对应的文件 (可能是 pdf_path 本身，也可能是上传时的同步副本)
            pdf_in_papers = papers_dir / pdf_path.name
            if pdf_in_papers.exists() and pdf_in_papers.name != new_filename:
                target_path = papers_dir / new_filename
                
                # 如果目标文件名已存在且不是当前文件，尝试加序号避免冲突
                if target_path.exists():
                    for i in range(1, 100):
                        temp_name = f"{safe_title}_{i}.pdf"
                        target_path = papers_dir / temp_name
                        if not target_path.exists():
                            break
                
                if not target_path.exists(): # 最终确认
                    pdf_in_papers.rename(target_path)
                    _wrapper_logger.info("论文归档重命名: %s -> %s", pdf_in_papers.name, target_path.name)
        except Exception as e:
            _wrapper_logger.warning("自动重命名论文失败: %s", e)

        results.append(r)
    return results[-1] if results else None
