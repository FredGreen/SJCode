"""
SJCode 共享工具模块
仅包含真正通用的工具函数
"""
import re
import os
from pathlib import Path


def clean_filename(filename: str) -> str:
    """清理文件名中的非法字符和HTML标记"""
    if not filename:
        return "untitled"
    
    # 移除HTML标记
    filename = re.sub(r'<[^>]+>', '', filename)
    
    # 移除Windows文件名非法字符
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    
    # 移除控制字符
    filename = re.sub(r'[\x00-\x1f\x7f]', '', filename)
    
    # 限制长度
    if len(filename) > 200:
        filename = filename[:200]
    
    return filename.strip() or "untitled"


def format_duration(seconds: int) -> str:
    """格式化时长（秒 → mm:ss 或 hh:mm:ss）"""
    if not seconds:
        return "00:00"
    
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_number(num: int) -> str:
    """格式化数字（10000 → 1万）"""
    if not num:
        return "0"
    if num >= 10000:
        return f"{num / 10000:.1f}万"
    return str(num)


def get_project_root() -> Path:
    """获取项目根目录"""
    return Path(__file__).parent.parent


def get_config_dir() -> Path:
    """获取配置目录"""
    return get_project_root() / "config"


def get_output_dir() -> Path:
    """获取输出目录"""
    return get_project_root() / "output"


def ensure_dir(path: Path) -> Path:
    """确保目录存在"""
    path.mkdir(parents=True, exist_ok=True)
    return path
