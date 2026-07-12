# -*- coding: utf-8 -*-
"""
V2 视频下载模块
功能：
  - 使用 yt-dlp 下载B站视频
  - 支持 cookies 认证
  - 自动跳过已下载视频
  - 支持自定义输出目录
"""

__version__ = "2.0.0"

import os
import sys
import subprocess
import shutil
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime


# ===================== 配置 =====================

def get_base_dir() -> Path:
    """获取基础目录（支持打包后的 exe）"""
    if getattr(sys, 'frozen', False):
        # 打包后的 exe，使用 exe 所在目录
        return Path(sys.executable).parent
    else:
        # 开发模式，使用项目根目录
        return Path(__file__).resolve().parent.parent.parent

# 项目根目录
PROJECT_ROOT = get_base_dir()
BASE_DIR = PROJECT_ROOT

# 默认输出目录
DEFAULT_VIDEO_DIR = PROJECT_ROOT / "output" / "v2_videos"

# yt-dlp 配置
YTDLP_TIMEOUT = 120  # 下载超时（秒）- 减少超时时间

# Cookies 文件路径（默认）
DEFAULT_COOKIE_FILE = PROJECT_ROOT / "config" / "cookies.txt"


# ===================== Cookies 处理 =====================

def load_cookies(cookie_file: Path = None) -> dict:
    """从 cookies.txt 加载 cookies（Netscape 格式）"""
    if cookie_file is None:
        cookie_file = DEFAULT_COOKIE_FILE
    
    if not cookie_file.exists():
        return {}
    
    cookies = {}
    try:
        with open(cookie_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) >= 7:
                    name = parts[5]
                    value = parts[6]
                    cookies[name] = value
    except Exception as e:
        print(f"[警告] 读取 cookies 失败: {e}")
    
    return cookies


def save_cookies(content: str, cookie_file: Path = None) -> bool:
    """保存 cookies 内容到文件"""
    if cookie_file is None:
        cookie_file = DEFAULT_COOKIE_FILE
    
    try:
        cookie_file.parent.mkdir(parents=True, exist_ok=True)
        with open(cookie_file, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    except Exception as e:
        print(f"[错误] 保存 cookies 失败: {e}")
        return False


def _find_ffmpeg() -> str:
    """查找 ffmpeg 路径"""
    path = shutil.which("ffmpeg")
    if path:
        return path
    
    # 常见安装路径
    common_paths = [
        "/usr/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        "/opt/homebrew/bin/ffmpeg",
        "C:/ffmpeg/bin/ffmpeg.exe",
    ]
    
    for p in common_paths:
        if os.path.exists(p):
            return p
    
    return ""


# ===================== 视频下载 =====================

def safe_filename(name: str) -> str:
    """生成安全的文件名"""
    if not name:
        return "untitled"
    
    # 移除HTML标记
    import re
    name = re.sub(r'<[^>]+>', '', name)
    
    # 移除Windows文件名非法字符
    illegal = '<>:"/\\|?*'
    for c in illegal:
        name = name.replace(c, '_')
    
    # 限制长度
    if len(name) > 100:
        name = name[:100]
    
    return name.strip() or "untitled"


def check_video_exists(bvid: str, title: str, output_dir: Path) -> Optional[str]:
    """检查视频是否已存在"""
    safe_title = safe_filename(title) if title else bvid
    
    for ext in ["mp4", "mkv", "webm", "flv"]:
        check_path = output_dir / f"{bvid}_{safe_title}.{ext}"
        if check_path.exists():
            return str(check_path)
    
    return None


def download_video(
    url: str, 
    bvid: str, 
    title: str, 
    output_dir: Path = None,
    cookie_file: Path = None,
    progress_callback=None
) -> Optional[str]:
    """
    使用 yt-dlp 下载视频
    
    Args:
        url: 视频URL
        bvid: B站视频ID
        title: 视频标题
        output_dir: 输出目录
        cookie_file: cookies文件路径
        progress_callback: 进度回调函数
    
    Returns:
        视频文件路径，失败返回 None
    """
    if output_dir is None:
        output_dir = DEFAULT_VIDEO_DIR
    
    if cookie_file is None:
        cookie_file = DEFAULT_COOKIE_FILE
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 检查是否已存在
    existing = check_video_exists(bvid, title, output_dir)
    if existing:
        if progress_callback:
            progress_callback(f"视频已存在: {existing}")
        return existing
    
    safe_title = safe_filename(title) if title else bvid
    output_template = str(output_dir / f"{bvid}_{safe_title}.%(ext)s")
    
    if progress_callback:
        progress_callback(f"开始下载: {title[:50]}...")
        progress_callback(f"URL: {url}")
    
    # 使用 yt_dlp Python API 直接调用（打包后也能正常工作）
    # 格式选择：使用不需要 ffmpeg 合并的格式
    # b 表示最佳单一格式（已包含音视频），不需要合并
    ydl_opts = {
        'format': 'b',
        'outtmpl': output_template,
        'noplaylist': True,
        'socket_timeout': 15,
        'retries': 3,
        'no_check_certificates': True,
        'quiet': False,
        'no_warnings': False,
    }
    
    # 添加 ffmpeg 路径
    ffmpeg_path = _find_ffmpeg()
    if ffmpeg_path:
        ydl_opts['ffmpeg_location'] = os.path.dirname(ffmpeg_path)
    
    # 添加 cookies
    if cookie_file.exists():
        if progress_callback:
            progress_callback(f"使用cookies: {cookie_file}")
        ydl_opts['cookiefile'] = str(cookie_file)
    else:
        if progress_callback:
            progress_callback(f"警告: cookies文件不存在")
    
    # 进度回调
    if progress_callback:
        def progress_hook(d):
            if d['status'] == 'downloading':
                percent = d.get('_percent_str', '0%')
                speed = d.get('_speed_str', '')
                progress_callback(f"  下载中: {percent} {speed}")
            elif d['status'] == 'finished':
                progress_callback(f"  下载完成，正在处理...")
        ydl_opts['progress_hooks'] = [progress_hook]
    
    try:
        import yt_dlp
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        if progress_callback:
            progress_callback("下载完成，检查文件...")
        
        # 查找下载的文件
        for ext in ["mp4", "mkv", "webm", "flv"]:
            check_path = output_dir / f"{bvid}_{safe_title}.{ext}"
            if check_path.exists():
                if progress_callback:
                    progress_callback(f"找到文件: {check_path}")
                return str(check_path)
        
        # 尝试查找目录中的新文件
        for f in output_dir.iterdir():
            if f.suffix.lower() in [".mp4", ".mkv", ".webm", ".flv"]:
                if bvid in f.stem or safe_title in f.stem:
                    if progress_callback:
                        progress_callback(f"找到文件: {f}")
                    return str(f)
        
        if progress_callback:
            progress_callback("下载失败: 找不到下载的文件")
            progress_callback(f"目录内容: {list(output_dir.iterdir())[:5]}")
        return None
        
    except subprocess.TimeoutExpired:
        if progress_callback:
            progress_callback("下载超时")
        return None
    except Exception as e:
        if progress_callback:
            progress_callback(f"下载错误: {e}")
        return None


def download_videos_batch(
    videos: List[Dict], 
    output_dir: Path = None,
    cookie_file: Path = None,
    progress_callback=None
) -> List[Dict]:
    """
    批量下载视频
    
    Args:
        videos: 视频列表 [{"bvid": "...", "title": "...", "url": "..."}, ...]
        output_dir: 输出目录
        cookie_file: cookies文件路径
        progress_callback: 进度回调函数
    
    Returns:
        下载结果列表
    """
    results = []
    total = len(videos)
    
    for i, video in enumerate(videos, 1):
        bvid = video.get("bvid", "")
        title = video.get("title", "")
        url = video.get("url", f"https://www.bilibili.com/video/{bvid}")
        
        if progress_callback:
            progress_callback(f"\n[{i}/{total}] 处理: {title[:40]}...")
        
        # 检查是否已存在
        existing = check_video_exists(bvid, title, output_dir or DEFAULT_VIDEO_DIR)
        if existing:
            if progress_callback:
                progress_callback(f"  跳过: 视频已存在")
            results.append({
                "bvid": bvid,
                "title": title,
                "status": "skipped",
                "path": existing,
                "message": "视频已存在"
            })
            continue
        
        # 下载视频
        path = download_video(url, bvid, title, output_dir, cookie_file, progress_callback)
        
        if path:
            results.append({
                "bvid": bvid,
                "title": title,
                "status": "success",
                "path": path,
                "message": "下载成功"
            })
        else:
            results.append({
                "bvid": bvid,
                "title": title,
                "status": "failed",
                "path": None,
                "message": "下载失败"
            })
    
    return results


# ===================== 视频列表管理 =====================

def get_downloaded_videos(output_dir: Path = None) -> List[Dict]:
    """获取已下载的视频列表"""
    if output_dir is None:
        output_dir = DEFAULT_VIDEO_DIR
    
    if not output_dir.exists():
        return []
    
    videos = []
    for f in output_dir.iterdir():
        if f.suffix.lower() in [".mp4", ".mkv", ".webm", ".flv"]:
            # 从文件名提取 bvid
            name = f.stem
            parts = name.split("_", 1)
            bvid = parts[0] if len(parts) > 0 else ""
            title = parts[1] if len(parts) > 1 else name
            
            videos.append({
                "bvid": bvid,
                "title": title,
                "path": str(f),
                "size": f.stat().st_size,
                "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat()
            })
    
    return videos


def is_video_downloaded(bvid: str, output_dir: Path = None) -> bool:
    """检查视频是否已下载"""
    if output_dir is None:
        output_dir = DEFAULT_VIDEO_DIR
    
    if not output_dir.exists():
        return False
    
    for f in output_dir.iterdir():
        if f.stem.startswith(bvid + "_"):
            return True
    
    return False


# ===================== 命令行入口 =====================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="V2 视频下载模块")
    parser.add_argument("--url", help="视频URL")
    parser.add_argument("--bvid", help="B站视频ID")
    parser.add_argument("--title", default="", help="视频标题")
    parser.add_argument("--output", help="输出目录")
    parser.add_argument("--cookies", help="cookies文件路径")
    parser.add_argument("--list", action="store_true", help="列出已下载视频")
    
    args = parser.parse_args()
    
    if args.list:
        videos = get_downloaded_videos()
        print(f"已下载 {len(videos)} 个视频:")
        for v in videos:
            print(f"  {v['bvid']}: {v['title'][:50]}...")
    elif args.url or args.bvid:
        bvid = args.bvid or args.url.split("/video/")[-1].split("/")[0]
        output_dir = Path(args.output) if args.output else None
        cookie_file = Path(args.cookies) if args.cookies else None
        
        path = download_video(
            args.url or f"https://www.bilibili.com/video/{bvid}",
            bvid,
            args.title,
            output_dir,
            cookie_file,
            lambda msg: print(msg)
        )
        
        if path:
            print(f"\n下载成功: {path}")
        else:
            print("\n下载失败")
    else:
        parser.print_help()
