"""OCR 引擎 - 通过 Ollama 调用视觉大模型"""

from __future__ import annotations

import time
from typing import List, Optional

from src.models import PageContent, PageInfo, ElementType
from src.ocr.element_classifier import RuleBasedClassifier
from src.utils.file_ops import get_file_hash, safe_write_json, read_json, ensure_dir
from src.utils.logger import get_logger

from pathlib import Path

logger = get_logger(__name__)

# 默认 OCR 提示词
DEFAULT_PROMPT = (
    "请完整解析这一页学术论文内容：\n"
    "1. 识别所有文字，保持原有段落结构\n"
    "2. 如果有数学公式，转换为LaTeX格式（用$$包裹）\n"
    "3. 如果有表格，转换为Markdown表格\n"
    "4. 如果有图片/图表，描述其内容和关键信息\n"
    "5. 标注章节标题层级（用 # ## ### 等）\n"
    "\n输出格式：Markdown"
)


class VisionOCREngine:
    """通过 Ollama 调用视觉模型的 OCR 引擎。

    支持 qwen2.5vl、minicpm-v、llama3.2-vision 等 Ollama 多模态模型。
    Ollama 自行管理 GPU 显存，无需手动加载/卸载权重。
    """

    def __init__(self) -> None:
        self._model_name = ""
        self._classifier = RuleBasedClassifier()

    @property
    def is_loaded(self) -> bool:
        return self._model_name != ""

    def load_model(self, model_name: str) -> None:
        """设置要使用的 Ollama 视觉模型，并验证可用性。

        Args:
            model_name: Ollama 模型名称，如 "qwen2.5vl:7b"
        """
        if self._model_name == model_name:
            logger.info("模型已就绪，跳过: %s", model_name)
            return

        logger.info("验证 Ollama OCR 模型: %s", model_name)

        try:
            import ollama
            # 检查模型是否已下载
            models = ollama.list()
            available = [m.model for m in models.models]
            if not any(model_name in name for name in available):
                logger.warning(
                    "模型 %s 未在本地找到 (可用: %s)，首次调用时 Ollama 会自动下载",
                    model_name, ", ".join(available) or "无",
                )
            self._model_name = model_name
            logger.info("OCR 模型已就绪: %s", model_name)

        except ImportError:
            raise RuntimeError("需要安装 ollama: pip install ollama")
        except Exception as e:
            raise RuntimeError("Ollama 连接失败 (确保 ollama serve 正在运行): {}".format(e))

    def process_page(
        self, image_path: str, page_num: int, prompt: Optional[str] = None
    ) -> PageContent:
        """处理单页图像（带结果缓存）。"""
        if not self.is_loaded:
            raise RuntimeError("模型未设置，请先调用 load_model()")

        import ollama

        prompt = prompt or DEFAULT_PROMPT
        img_path = Path(image_path)
        
        # ── 缓存逻辑 ──
        # 缓存路径: cache/ocr_results/{model_name}/{img_hash}.json
        img_hash = get_file_hash(img_path)
        cache_dir = ensure_dir(Path("cache/ocr_results") / self._model_name.replace(":", "_"))
        cache_path = cache_dir / f"{img_hash}.json"
        
        if cache_path.exists():
            try:
                cached_data = read_json(cache_path)
                logger.debug("页面 %d 命中缓存: %s", page_num, cache_path.name)
                return PageContent(
                    page_num=page_num,
                    markdown=cached_data["markdown"],
                    detected_elements=[ElementType(e) for e in cached_data["elements"]],
                    confidence=cached_data.get("confidence", 1.0)
                )
            except Exception as e:
                logger.warning("读取缓存失败: %s", e)

        # ── 实际请求 ──
        try:
            response = ollama.chat(
                model=self._model_name,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                        "images": [str(img_path)],
                    }
                ],
            )
            markdown = response.message.content.strip()

        except Exception as e:
            logger.error("页面 %d OCR 失败: %s", page_num, e)
            markdown = "[OCR 失败: {}]".format(e)

        # 元素分类（纯 CPU）
        elements = self._classifier.classify(markdown)
        
        # 保存缓存
        result = PageContent(
            page_num=page_num,
            markdown=markdown,
            detected_elements=elements,
            confidence=1.0 if "[OCR 失败" not in markdown else 0.0,
        )
        
        if result.confidence > 0:
            try:
                safe_write_json(cache_path, {
                    "markdown": result.markdown,
                    "elements": [e.value for e in result.detected_elements],
                    "confidence": result.confidence,
                    "img_path": str(img_path)
                })
            except Exception as e:
                logger.warning("写入缓存失败: %s", e)

        return result

    def process_all_pages(
        self, pages: List[PageInfo], show_progress: bool = True, parallel_threads: int = 1
    ) -> List[PageContent]:
        """批量处理所有页面（支持并行）。"""
        if not self.is_loaded:
            raise RuntimeError("模型未设置，请先调用 load_model()")

        total = len(pages)
        if parallel_threads <= 1:
            # 串行处理 (原逻辑)
            results = []
            for i, page in enumerate(pages):
                t0 = time.time()
                content = self.process_page(str(page.image_path), page.page_num)
                elapsed = time.time() - t0
                results.append(content)
                if show_progress:
                    logger.info("[%d/%d] 页面 %d 完成 (%.1fs)", i + 1, total, page.page_num, elapsed)
            return results
        
        # 并行处理
        from concurrent.futures import ThreadPoolExecutor
        logger.info("启动并行 OCR: 线程数=%d", parallel_threads)
        
        with ThreadPoolExecutor(max_workers=parallel_threads) as executor:
            # 提交所有任务
            futures = [
                executor.submit(self.process_page, str(page.image_path), page.page_num)
                for page in pages
            ]
            
            # 等待结果并按页码排序
            results = []
            for i, future in enumerate(futures):
                content = future.result()
                results.append(content)
                if show_progress:
                    logger.info("[%d/%d] 页面 %d 处理完成 (异步)", i + 1, total, content.page_num)
            
            # 确保按页码排序（尽管提交顺序通常一致，但稳妥起见按 page_num 排序）
            results.sort(key=lambda x: x.page_num)
            return results

    def unload_model(self) -> None:
        """重置模型名称。Ollama 自行管理显存，无需手动释放。"""
        self._model_name = ""
        logger.info("OCR 模型已释放")
