"""FastAPI 主应用 - API 路由 + 静态文件服务"""

from __future__ import annotations

import asyncio
import json
import shutil
import uuid
from pathlib import Path
from typing import List

import ollama
import uvicorn
from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from src.models import AnalysisType
from src.web.pipeline_wrapper import (
    JobStatus,
    create_job,
    get_job,
    run_job,
)

app = FastAPI(title="paperRead", version="0.1.0")

# 静态文件
_STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

# 上传目录
_UPLOAD_DIR = Path("cache/uploads")
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/", response_class=HTMLResponse)
async def index():
    return (_STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/api/models")
async def list_models():
    """从 ollama 获取模型列表，按 OCR/LLM 分类"""
    try:
        result = ollama.list()
        ocr_name_keywords = {"vl", "vision", "ocr", "glm-ocr", "minicpm-v"}
        ocr_family_keywords = {"vl", "ocr", "vision"}
        ocr_models = []
        llm_models = []

        for m in result.models:
            name = m.model
            name_lower = name.lower()
            # 通过模型名或 family 判断是否为 OCR/视觉模型
            families = m.details.families if m.details and m.details.families else []
            families_str = " ".join(f.lower() for f in families)
            is_ocr = (
                any(kw in name_lower for kw in ocr_name_keywords)
                or any(kw in families_str for kw in ocr_family_keywords)
            )
            entry = {
                "name": name,
                "size": m.size or 0,
                "modified_at": str(m.modified_at) if m.modified_at else "",
            }
            if is_ocr:
                ocr_models.append(entry)
            else:
                llm_models.append(entry)

        return {"ocr_models": ocr_models, "llm_models": llm_models}
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"无法连接 Ollama: {e}"},
        )


@app.post("/api/upload")
async def upload_files(files: List[UploadFile] = File(...)):
    """上传 PDF 文件，返回 file_id 和文件列表"""
    file_id = uuid.uuid4().hex[:12]
    upload_path = _UPLOAD_DIR / file_id
    upload_path.mkdir(parents=True, exist_ok=True)

    saved = []
    for f in files:
        if not f.filename.lower().endswith(".pdf"):
            continue
        dest = upload_path / f.filename
        content = await f.read()
        dest.write_bytes(content)
        saved.append({"name": f.filename, "path": str(dest)})

    if not saved:
        return JSONResponse(status_code=400, content={"error": "未找到有效的 PDF 文件"})

    return {"file_id": file_id, "files": saved}


@app.post("/api/analyze")
async def start_analysis(
    file_id: str = Form(...),
    ocr_model: str = Form(...),
    llm_model: str = Form(...),
    analysis_type: str = Form("comprehensive"),
):
    """启动分析任务"""
    upload_path = _UPLOAD_DIR / file_id
    if not upload_path.exists():
        return JSONResponse(status_code=404, content={"error": "文件未找到"})

    pdf_paths = sorted(upload_path.glob("*.pdf"))
    if not pdf_paths:
        return JSONResponse(status_code=400, content={"error": "目录中无 PDF 文件"})

    try:
        atype = AnalysisType(analysis_type)
    except ValueError:
        atype = AnalysisType.COMPREHENSIVE

    job = create_job(pdf_paths, atype, ocr_model, llm_model)

    # 后台启动任务
    asyncio.create_task(run_job(job))

    return {"job_id": job.job_id, "file_count": len(pdf_paths)}


@app.get("/api/progress/{job_id}")
async def progress_stream(job_id: str):
    """SSE 实时进度流"""
    job = get_job(job_id)
    if not job:
        return JSONResponse(status_code=404, content={"error": "任务不存在"})

    async def event_generator():
        while True:
            try:
                event = await asyncio.wait_for(job.queue.get(), timeout=60)
            except asyncio.TimeoutError:
                # 心跳
                yield {"event": "heartbeat", "data": "{}"}
                continue

            if event is None:
                # 任务结束
                yield {
                    "event": "done",
                    "data": json.dumps({"status": job.status.value}),
                }
                break

            yield {
                "event": "progress",
                "data": json.dumps(event.to_dict(), ensure_ascii=False),
            }

    return EventSourceResponse(event_generator())


@app.get("/api/results/{job_id}")
async def get_results(job_id: str):
    """获取分析结果"""
    job = get_job(job_id)
    if not job:
        return JSONResponse(status_code=404, content={"error": "任务不存在"})

    if job.status == JobStatus.RUNNING:
        return JSONResponse(status_code=202, content={"status": "running"})

    if job.status == JobStatus.FAILED:
        return JSONResponse(status_code=500, content={"error": job.error})

    return {
        "status": "completed",
        "markdown": job.result_markdown,
        "json_data": job.result_json,
    }


if __name__ == "__main__":
    uvicorn.run(
        "src.web.app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )
