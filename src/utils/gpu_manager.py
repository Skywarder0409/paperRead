"""GPU 显存管理 - 通过 nvidia-smi 检测"""

import gc
import subprocess

from src.utils.logger import get_logger

logger = get_logger(__name__)


def get_gpu_memory_info() -> dict:
    """通过 nvidia-smi 获取 GPU 显存使用信息。

    Returns:
        dict: {"total_mb": float, "used_mb": float, "free_mb": float, "gpu_name": str}
        若 nvidia-smi 不可用则返回空字典
    """
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,memory.free",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return {}
        line = result.stdout.strip().split("\n")[0]
        parts = [p.strip() for p in line.split(",")]
        return {
            "gpu_name": parts[0],
            "total_mb": float(parts[1]),
            "used_mb": float(parts[2]),
            "free_mb": float(parts[3]),
        }
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        return {}


def release_gpu_memory() -> None:
    """释放 GPU 显存（Python 侧垃圾回收）"""
    gc.collect()
    info = get_gpu_memory_info()
    if info:
        logger.info(
            "当前显存: 已用 %.0f MB / 总共 %.0f MB",
            info["used_mb"], info["total_mb"],
        )


def log_gpu_status(stage_name: str = "") -> None:
    """记录当前 GPU 状态"""
    info = get_gpu_memory_info()
    if info:
        prefix = "[{}] ".format(stage_name) if stage_name else ""
        logger.info(
            "%sGPU %s: 已用 %.0f MB / 空闲 %.0f MB / 总共 %.0f MB",
            prefix, info["gpu_name"],
            info["used_mb"], info["free_mb"], info["total_mb"],
        )
    else:
        logger.info("nvidia-smi 不可用，无法检测 GPU 状态")
