"""Prompt 模板管理"""

from __future__ import annotations

from src.models import AnalysisType

import os
from pathlib import Path

# 基础目录
PROMPTS_DIR = Path(__file__).parent / "prompts"

# 默认的分块总结 Prompt
CHUNK_SUMMARY_PROMPT = "总结以下章节的核心内容（200字内）：\n{content}"

def get_prompt(prompt_choice: str) -> str:
    """从文件系统中加载 Prompt 模板。
    
    Args:
        prompt_choice: 提示词路径，如 "运筹学/快速总结" 或 "custom_prompt_content"
        
    Returns:
        包含 {content} 占位符的 prompt 字符串
    """
    # 1. 尝试作为路径拼接待 .txt 加载
    prompt_path = PROMPTS_DIR / f"{prompt_choice}.txt"
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    
    # 2. 如果不存在，直接返回原始字符串（支持前端直接传自定义内容）
    # 如果字符串中不含 {content}，自动在末尾添加
    if "{content}" not in prompt_choice:
        return prompt_choice + "\n\n内容：\n{content}"
    
    return prompt_choice

def list_prompt_library() -> dict:
    """递归扫描 prompts 目录，返回树状结构"""
    library = {}
    if not PROMPTS_DIR.exists():
        return library
        
    for root, dirs, files in os.walk(PROMPTS_DIR):
        rel_path = os.path.relpath(root, PROMPTS_DIR)
        if rel_path == ".":
            current_level = library
        else:
            # 处理多层目录
            parts = rel_path.split(os.sep)
            temp = library
            for p in parts:
                if p not in temp:
                    temp[p] = {}
                temp = temp[p]
            current_level = temp
            
        for f in files:
            if f.endswith(".txt"):
                name = f.removesuffix(".txt")
                current_level[name] = os.path.join(rel_path if rel_path != "." else "", name)
    
    return library
