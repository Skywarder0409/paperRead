"""CLI 入口点"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from src.config import PipelineConfig
from src.models import AnalysisType
from src.pipeline import Pipeline
from src.utils.logger import setup_logger


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="本地文献解读 Pipeline - 基于本地大模型的学术论文分析系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
示例:
  # 单篇深度分析
  python -m src.main --input papers/example.pdf --mode comprehensive

  # 快速总结
  python -m src.main --input papers/example.pdf --mode quick

  # 批量处理
  python -m src.main --batch papers/ --mode quick

  # 从阶段4开始（复用已有 structured.md）
  python -m src.main --input output/example_structured.md --stage 4 --mode comprehensive

  # 自定义参数
  python -m src.main --input papers/example.pdf --dpi 300 --llm-model deepseek-v2.5
""",
    )

    # 输入
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--input", type=Path, help="单个 PDF 文件或 structured.md 路径")
    input_group.add_argument("--batch", type=Path, help="批量处理：PDF 目录路径")

    # 分析模式
    parser.add_argument(
        "--mode",
        type=str,
        choices=["comprehensive", "quick", "methodology_focus"],
        default="comprehensive",
        help="分析模式 (默认: comprehensive)",
    )

    # 起始阶段
    parser.add_argument(
        "--stage",
        type=int,
        choices=[1, 2, 3, 4],
        default=1,
        help="起始阶段 1-4 (默认: 1)",
    )

    # 可选参数
    parser.add_argument("--dpi", type=int, default=200, help="PDF 渲染 DPI (默认: 200)")
    parser.add_argument("--ocr-model", type=str, default="deepseek-ocr2", help="OCR 模型名称")
    parser.add_argument("--llm-model", type=str, default="qwen3-30b-a3b", help="LLM 模型名称")
    parser.add_argument("--max-tokens", type=int, default=4096, help="LLM 最大生成 token 数")
    parser.add_argument("--output-dir", type=Path, default=Path("output"), help="输出目录")
    parser.add_argument("--cache-dir", type=Path, default=Path("cache"), help="缓存目录")
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="日志级别",
    )

    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)

    # 配置
    config = PipelineConfig(
        ocr_model=args.ocr_model,
        llm_model=args.llm_model,
        dpi=args.dpi,
        max_tokens=args.max_tokens,
        output_dir=args.output_dir,
        cache_dir=args.cache_dir,
        log_level=args.log_level,
    )

    setup_logger("pipeline", level=config.log_level, log_file=config.log_file)

    analysis_type = AnalysisType(args.mode)
    pipeline = Pipeline(config)

    if args.batch:
        results = pipeline.batch_run(args.batch, analysis_type)
        print("\n批量处理完成: {} 篇论文".format(len(results)))
    else:
        if not args.input.exists():
            print("错误: 文件不存在 - {}".format(args.input), file=sys.stderr)
            sys.exit(1)
        result = pipeline.run(args.input, analysis_type, start_stage=args.stage)
        print("\n处理完成: {}".format(result.metadata.title))
        print("耗时: {:.1f} 秒".format(result.processing_time_seconds))
        print("分析报告: {}".format(config.output_dir))


if __name__ == "__main__":
    main()
