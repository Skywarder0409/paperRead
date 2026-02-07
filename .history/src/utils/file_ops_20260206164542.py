"""文件操作工具"""

import json
import shutil
import hashlib
from pathlib import Path

from src.utils.logger import get_logger

logger = get_logger(__name__)


def ensure_dir(path: Path) -> Path:
    """确保目录存在，返回路径"""
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    """安全写入文本文件（先写临时文件再重命名）"""
    ensure_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding=encoding)
    tmp.replace(path)
    logger.debug("写入文件: %s (%d 字符)", path, len(content))


def safe_write_json(path: Path, data: dict, indent: int = 2) -> None:
    """安全写入 JSON 文件"""
    safe_write_text(path, json.dumps(data, ensure_ascii=False, indent=indent))


def read_text(path: Path, encoding: str = "utf-8") -> str:
    """读取文本文件"""
    return path.read_text(encoding=encoding)


def read_json(path: Path) -> dict:
    """读取 JSON 文件"""
    return json.loads(read_text(path))


def clean_dir(path: Path) -> None:
    """清空目录内容（保留目录本身）"""
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    logger.debug("已清空目录: %s", path)


def get_pdf_output_dir(output_dir: Path, pdf_name: str) -> Path:
    """为单个 PDF 创建独立的输出目录"""
    stem = Path(pdf_name).stem
    out = ensure_dir(output_dir / stem)
    return out
