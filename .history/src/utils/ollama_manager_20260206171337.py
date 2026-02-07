"""Ollama 服务生命周期管理 - 自动配置并行参数"""

import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)

def get_ollama_pid() -> Optional[int]:
    """获取正在运行的 ollama serve 进程 PID"""
    try:
        # 查找 ollama serve 进程
        result = subprocess.run(
            ["pgrep", "-f", "ollama serve"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            return int(result.stdout.strip().split("\n")[0])
    except Exception:
        pass
    return None

def get_current_parallelism() -> int:
    """尝试获取当前运行中 Ollama 的并行数设置"""
    pid = get_ollama_pid()
    if not pid:
        return 0
    
    try:
        # 在 Linux 系统通过 /proc 检查环境变量
        environ_path = Path(f"/proc/{pid}/environ")
        if environ_path.exists():
            content = environ_path.read_text(encoding="utf-8", errors="ignore")
            # 环境变量以 \0 分隔
            envs = content.split("\0")
            for env in envs:
                if env.startswith("OLLAMA_NUM_PARALLEL="):
                    return int(env.split("=")[1])
    except Exception as e:
        logger.warning("检查 Ollama 环境变量失败: %s", e)
    
    # 默认 Ollama 为 1
    return 1

def restart_ollama(parallel_n: int):
    """重启 Ollama 服务并注入新的并行参数"""
    pid = get_ollama_pid()
    if pid:
        logger.info("发现运行中的 Ollama (PID: %d)，正在停止以重新配置...", pid)
        try:
            os.kill(pid, signal.SIGTERM)
            # 等待进程退出
            for _ in range(10):
                if get_ollama_pid() is None:
                    break
                time.sleep(0.5)
        except Exception as e:
            logger.error("停止 Ollama 失败: %s", e)

    # 构造用户指定的命令
    # OLLAMA_CONTEXT_LENGTH=100000 OLLAMA_HOST=0.0.0.0:11434 ollama serve > ollama.log 2>&1 &
    env = os.environ.copy()
    env["OLLAMA_CONTEXT_LENGTH"] = "100000"
    env["OLLAMA_HOST"] = "0.0.0.0:11434"
    env["OLLAMA_NUM_PARALLEL"] = str(parallel_n)
    env["OLLAMA_MAX_LOADED_MODELS"] = str(max(2, parallel_n // 2))
    
    log_file = open("ollama.log", "a")
    
    logger.info("🚀 重新启动 Ollama: 并行数=%d, 显存槽位=%s", parallel_n, env["OLLAMA_MAX_LOADED_MODELS"])
    
    subprocess.Popen(
        ["ollama", "serve"],
        env=env,
        stdout=log_file,
        stderr=log_file,
        start_new_session=True # 脱离当前进程树
    )
    
    # 等待服务启动响应
    time.sleep(2)
    logger.info("Ollama 已在后台启动")

def ensure_ollama_parallelism(required: int):
    """确保 Ollama 环境匹配要求的并行度"""
    if required <= 1:
        return
        
    current = get_current_parallelism()
    if current < required:
        logger.info("当前 Ollama 并行度 (%d) 低于要求 (%d)，正在自动重启...", current, required)
        restart_ollama(required)
    else:
        logger.info("当前 Ollama 并行度 (%d) 已满足要求 (%d)", current, required)
