# -*- coding: utf-8 -*-
"""视频转 Markdown 工具 - 配置文件"""

import os
from pathlib import Path

# ==================== 路径配置 ====================
BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"

# 各功能模块输出目录
DOCS_DIR = OUTPUT_DIR / "docs"        # Parser 生成的 Markdown
ASR_CACHE_DIR = OUTPUT_DIR / "asr_cache"  # ASR 缓存
SUMMARY_DIR = OUTPUT_DIR / "summary"  # 商机提炼总结

# ==================== API 配置 ====================
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")

# ==================== ASR 配置 ====================
ASR_MODEL = "paraformer-v2"
ASR_LANGUAGE_HINTS = ["zh", "en"]

# ==================== LLM 配置 ====================
LLM_MODEL = "qwen-plus"