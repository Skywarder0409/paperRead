"""LLM 引擎 - 通过 Ollama 调用文本生成模型"""

from __future__ import annotations

import time

from src.analysis.prompts import get_prompt
from src.models import AnalysisResult, AnalysisType, DocumentStructure
from src.utils.logger import get_logger

logger = get_logger(__name__)


class TransformersLLMEngine:
    """通过 Ollama 调用 LLM 的引擎。

    支持 qwen3、deepseek-v2.5、qwq 等 Ollama 文本模型。
    Ollama 自行管理 GPU 显存，无需手动加载/卸载权重。
    """

    def __init__(self) -> None:
        self._model_name = ""

    @property
    def is_loaded(self) -> bool:
        return self._model_name != ""

    def load_model(self, model_name: str) -> None:
        """设置要使用的 Ollama LLM 模型，并验证可用性。"""
        if self._model_name == model_name:
            logger.info("模型已就绪，跳过: %s", model_name)
            return

        logger.info("验证 Ollama LLM 模型: %s", model_name)

        try:
            import ollama
            models = ollama.list()
            available = [m.model for m in models.models]
            if not any(model_name in name for name in available):
                logger.warning(
                    "模型 %s 未在本地找到 (可用: %s)，首次调用时 Ollama 会自动下载",
                    model_name, ", ".join(available) or "无",
                )
            self._model_name = model_name
            logger.info("LLM 模型已就绪: %s", model_name)

        except ImportError:
            raise RuntimeError("需要安装 ollama: pip install ollama")
        except Exception as e:
            raise RuntimeError("Ollama 连接失败 (确保 ollama serve 正在运行): {}".format(e))

    def _generate(self, prompt: str, max_new_tokens: int = 4096) -> str:
        """底层生成方法，供内部和 chunking 模块调用。"""
        if not self.is_loaded:
            raise RuntimeError("模型未设置，请先调用 load_model()")

        import ollama

        response = ollama.chat(
            model=self._model_name,
            messages=[
                {"role": "system", "content": "你是一个专业的学术论文分析助手。"},
                {"role": "user", "content": prompt},
            ],
            options={
                "num_predict": max_new_tokens,
                "temperature": 0.7,
                "top_p": 0.9,
            },
        )
        return response.message.content.strip()

    def analyze(
        self,
        full_markdown: str,
        structure: DocumentStructure,
        analysis_type: Union[AnalysisType, str] = AnalysisType.COMPREHENSIVE,
        max_tokens: int = 4096,
    ) -> AnalysisResult:
        """对文档进行深度分析。"""
        prompt_template = get_prompt(analysis_type if not isinstance(analysis_type, AnalysisType) else analysis_type.value)

        # 构造上下文摘要，帮助 LLM 理解文档结构
        context_hint = ""
        if structure.title:
            context_hint += "标题: {}\n".format(structure.title)
        if structure.abstract:
            context_hint += "摘要: {}\n".format(structure.abstract[:500])
        if structure.sections:
            toc = ", ".join(s["title"] for s in structure.sections if s["level"] <= 2)
            context_hint += "目录: {}\n".format(toc)

        content = context_hint + "\n" + full_markdown if context_hint else full_markdown
        prompt = prompt_template.format(content=content)

        display_mode = analysis_type.value if isinstance(analysis_type, AnalysisType) else analysis_type
        logger.info("开始 LLM 分析 (模式=%s, 输入长度=%d)", display_mode, len(prompt))
        t0 = time.time()
        analysis_text = self._generate(prompt, max_new_tokens=max_tokens)
        elapsed = time.time() - t0
        logger.info("LLM 分析完成，耗时 %.1f 秒，输出 %d 字符", elapsed, len(analysis_text))

        token_estimate = len(analysis_text) // 2

        return AnalysisResult(
            analysis_text=analysis_text,
            analysis_type=analysis_type,
            model_name=self._model_name,
            token_count=token_estimate,
        )

    def unload_model(self) -> None:
        """重置模型名称。Ollama 自行管理显存，无需手动释放。"""
        self._model_name = ""
        logger.info("LLM 模型已释放")
