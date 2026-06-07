
from pathlib import Path

##  获取当前脚本的所在的绝对路径
BASE_DIR = Path(__file__).resolve().parent.parent

##  定义 输出目录结构
OUTPUT_DIR = BASE_DIR / "output"

# 各功能模块的输出子目录
VIDEO = OUTPUT_DIR / "video"        # 视频下载
DOCS = OUTPUT_DIR / "docs"          # Parser 生成的 Markdown 文档
SUMMARY = OUTPUT_DIR / "summary"    # 商机提炼总结
TASKS = OUTPUT_DIR / "tasks"        # Excel 任务文件
ASR_CACHE = OUTPUT_DIR / "asr_cache"  # ASR 缓存
HISTORY = OUTPUT_DIR / "history"     # 历史记录


