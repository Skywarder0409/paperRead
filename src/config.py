"""全局配置管理"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PipelineConfig:
    """Pipeline 全局配置"""

    # 模型选择
    ocr_model: str = "deepseek-ocr2"
    llm_model: str = "qwen3-30b-a3b"

    # 路径配置
    input_dir: Path = field(default_factory=lambda: Path("papers"))
    output_dir: Path = field(default_factory=lambda: Path("output"))
    cache_dir: Path = field(default_factory=lambda: Path("cache"))

    # PDF 预处理
    dpi: int = 200
    image_format: str = "png"

    # 显存管理
    unload_after_stage: bool = True
    gpu_device: str = "cuda:0"

    # LLM 分析
    max_tokens: int = 4096
    max_text_length: int = 50000  # 超过此长度触发分块处理

    # 日志
    log_level: str = "INFO"
    log_file: str = "pipeline.log"

    def ensure_dirs(self) -> None:
        """确保所有必要目录存在"""
        for d in [self.input_dir, self.output_dir, self.cache_dir]:
            d.mkdir(parents=True, exist_ok=True)


DEFAULT_CONFIG = PipelineConfig()
