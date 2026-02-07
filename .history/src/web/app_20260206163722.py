"""FastAPI 主应用 - API 路由 + 静态文件服务"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import List, Optional

import ollama
import uvicorn
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from src.models import AnalysisType
from src.analysis.prompts import list_prompt_library, PROMPTS_DIR
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

# 论文存储目录
_PAPERS_DIR = Path("papers")
_PAPERS_DIR.mkdir(parents=True, exist_ok=True)

# 输出目录（历史论文）
_OUTPUT_DIR = Path("output")


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
        
        # 保存到临时上传目录 (用于当前任务)
        dest = upload_path / f.filename
        content = await f.read()
        dest.write_bytes(content)
        
        # 同时保存到 papers/ 目录 (实现持久化)
        paper_dest = _PAPERS_DIR / f.filename
        if not paper_dest.exists():
            shutil.copy2(dest, paper_dest)
            
        saved.append({"name": f.filename, "path": str(dest)})

    if not saved:
        return JSONResponse(status_code=400, content={"error": "未找到有效的 PDF 文件"})

    return {"file_id": file_id, "files": saved}


@app.post("/api/analyze")
async def start_analysis(
    file_id: Optional[str] = Form(None),
    filenames: Optional[str] = Form(None),  # JSON array of filenames in papers/
    ocr_model: str = Form(...),
    llm_model: str = Form(...),
    analysis_type: str = Form("comprehensive"),
):
    """启动分析任务"""
    pdf_paths = []
    
    if file_id:
        upload_path = _UPLOAD_DIR / file_id
        if upload_path.exists():
            pdf_paths.extend(sorted(upload_path.glob("*.pdf")))
    
    if filenames:
        try:
            names = json.loads(filenames)
            for name in names:
                path = _PAPERS_DIR / name
                if path.exists():
                    pdf_paths.append(path)
        except json.JSONDecodeError:
            pass # 忽略错误格式
            
    if not pdf_paths:
        return JSONResponse(status_code=400, content={"error": "未指定有效的 PDF 文件"})

    # 直接使用 analysis_type 字符串，不再强制转换 Enum
    atype = analysis_type

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
        # 任务已结束时立即返回结果（防止刷新后挂起）
        if job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
            yield {
                "event": "done",
                "data": json.dumps({"status": job.status.value}),
            }
            return

        while True:
            try:
                event = await asyncio.wait_for(job.queue.get(), timeout=15)
            except asyncio.TimeoutError:
                # 超时时检查任务是否已结束（防止 None 哨兵被旧连接消费）
                if job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
                    yield {
                        "event": "done",
                        "data": json.dumps({"status": job.status.value}),
                    }
                    return
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
        content = {"status": "running"}
        if job.last_progress:
            content["progress"] = job.last_progress.to_dict()
        return JSONResponse(status_code=202, content=content)

    if job.status == JobStatus.FAILED:
        return JSONResponse(status_code=500, content={"error": job.error})

    return {
        "status": "completed",
        "markdown": job.result_markdown,
        "json_data": job.result_json,
    }


@app.get("/api/history")
async def list_history(
    search: Optional[str] = Query(None, description="搜索关键词（标题/作者）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页条数"),
):
    """扫描 output/ 目录，返回历史论文列表（按标题字母排序，分页）"""
    if not _OUTPUT_DIR.exists():
        return {"items": [], "total": 0, "page": page, "page_size": page_size}

    items = []
    for fp in _OUTPUT_DIR.glob("*_analysis.json"):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        meta = data.get("metadata", {})
        analysis = data.get("analysis", {})
        processing = data.get("processing", {})
        base_name = fp.name.removesuffix("_analysis.json")
        summary_file = base_name + "_summary.md"
        structured_file = base_name + "_structured.md"

        items.append({
            "title": meta.get("title", base_name),
            "author": meta.get("author", ""),
            "total_pages": meta.get("total_pages", 0),
            "analysis_type": analysis.get("type", ""),
            "model": analysis.get("model", ""),
            "time_seconds": processing.get("time_seconds", 0),
            "generated_at": processing.get("generated_at", ""),
            "submitted_at": processing.get("submitted_at", ""),
            "completed_at": processing.get("generated_at", ""),
            "base_name": base_name,
            "files": {
                "summary": summary_file,
                "analysis": fp.name,
                "structured": structured_file,
            },
        })

    # 搜索过滤
    if search:
        kw = search.lower()
        items = [
            it for it in items
            if kw in it["title"].lower() or kw in it["author"].lower()
        ]

    # 按标题字母排序
    items.sort(key=lambda x: x["title"].lower())

    total = len(items)
    start = (page - 1) * page_size
    paged_items = items[start : start + page_size]

    return {"items": paged_items, "total": total, "page": page, "page_size": page_size}


@app.get("/api/papers")
async def list_papers():
    """获取 papers/ 目录下的 PDF 文件列表"""
    if not _PAPERS_DIR.exists():
        return {"papers": []}
    
    papers = []
    for fp in sorted(_PAPERS_DIR.glob("*.pdf")):
        papers.append({
            "name": fp.name,
            "path": str(fp),
            "size": fp.stat().st_size,
            "modified_at": fp.stat().st_mtime
        })
    return {"papers": papers}


@app.get("/api/prompts")
async def get_prompts():
    """获取提示词库 (学科 -> 模式)"""
    return {"library": list_prompt_library()}


@app.post("/api/prompts/save")
async def save_prompt(
    category: str = Form(...),
    name: str = Form(...),
    content: str = Form(...),
):
    """保存自定义提示词"""
    safe_category = "".join(c for c in category if c.isalnum() or c in " _-") or "自定义"
    safe_name = "".join(c for c in name if c.isalnum() or c in " _-") or "新提示词"
    
    target_dir = PROMPTS_DIR / safe_category
    target_dir.mkdir(parents=True, exist_ok=True)
    
    target_file = target_dir / f"{safe_name}.txt"
    target_file.write_text(content, encoding="utf-8")
    
    return {"status": "success", "path": f"{safe_category}/{safe_name}"}


@app.get("/api/history/{filename:path}")
async def get_history_file(filename: str):
    """读取 output/ 目录下的单个文件（防止路径穿越）"""
    # 安全检查：防止路径穿越
    safe_path = (_OUTPUT_DIR / filename).resolve()
    if not str(safe_path).startswith(str(_OUTPUT_DIR.resolve())):
        raise HTTPException(status_code=403, detail="禁止访问")

    if not safe_path.exists() or not safe_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    content = safe_path.read_text(encoding="utf-8")

    if safe_path.suffix == ".json":
        return JSONResponse(content=json.loads(content))

    return PlainTextResponse(content=content)


@app.post("/api/shutdown")
async def shutdown():
    """关闭服务器，终止整个进程"""
    # 延迟 0.5s 让响应先返回给前端，然后强制终止整个进程（包括线程池）
    async def _exit():
        await asyncio.sleep(0.5)
        os._exit(0)

    asyncio.create_task(_exit())
    return {"message": "shutting down"}


if __name__ == "__main__":
    uvicorn.run(
        "src.web.app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )
