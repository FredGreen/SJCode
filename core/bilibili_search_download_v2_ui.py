# -*- coding: utf-8 -*-
"""
B站视频下载 - UI 集成版本

复用 core/bilibili_search_download-v2.py 的核心逻辑，
提供与 UI 集成的接口。
"""

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

# 添加项目路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import VIDEO

# 导入原版下载器的核心函数
sys.path.insert(0, str(Path(__file__).resolve().parent))
from bilibili_search_download_v2 import (
    HEADERS, COOKIE_FILE, load_cookies, cookie_dict_to_str,
    _parse_duration_minutes, ORDER_MAP,
    DEFAULT_PAGE_SIZE, MAX_DURATION_MIN, MAX_SIZE_MB
)


def download_keyword_videos(
    keyword: str,
    order: str = "totalrank",
    limit: int = 5,
    progress_callback: Optional[Callable] = None
) -> list[dict]:
    """
    下载指定关键词的视频

    Args:
        keyword: 搜索关键词
        order: 排序方式 (totalrank/click/pubdate/dm/stow)
        limit: 下载数量上限
        progress_callback: 进度回调函数

    Returns:
        下载成功的视频信息列表
    """
    import requests  # 延迟导入

    if progress_callback:
        progress_callback(f"开始搜索: {keyword}")

    # 加载 cookies
    cookies = load_cookies(COOKIE_FILE)
    if cookies:
        HEADERS["Cookie"] = cookie_dict_to_str(cookies)

    # 构建搜索 URL
    search_url = "https://api.bilibili.com/x/web-interface/search/type"
    params = {
        "search_type": "video",
        "keyword": keyword,
        "order": order,
        "page": 1,
        "page_size": min(limit * 2, 20)  # 多获取一些以便过滤
    }

    # 搜索视频
    try:
        response = requests.get(search_url, params=params, headers=HEADERS, timeout=30)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        if progress_callback:
            progress_callback(f"搜索失败: {str(e)}")
        return []

    if data.get("code") != 0 or "data" not in data:
        if progress_callback:
            progress_callback(f"搜索结果为空")
        return []

    videos = data["data"].get("result", [])
    if not videos:
        if progress_callback:
            progress_callback(f"未找到视频")
        return []

    downloaded = []

    # 使用 yt-dlp 下载视频
    ffmpeg_path = _find_ffmpeg()

    for video in videos[:limit]:
        try:
            bvid = video.get("bvid")
            title = video.get("title", "")
            # 清理标题中的非法字符
            title = re.sub(r'[\\/:*?"<>|]', '_', title)
            # 清理 HTML 实体
            title = re.sub(r'&[a-z]+;', '', title)

            duration_str = video.get("duration", "0:00")
            duration_min = _parse_duration_minutes(duration_str)

            # 过滤时长
            if MAX_DURATION_MIN > 0 and duration_min > MAX_DURATION_MIN:
                if progress_callback:
                    progress_callback(f"跳过 (时长过长): {title[:30]}")
                continue

            # 创建输出目录
            output_dir = VIDEO / keyword
            output_dir.mkdir(parents=True, exist_ok=True)
            output_template = str(output_dir / f"{title}.%(ext)s")

            # yt-dlp 下载命令
            cmd = [
                sys.executable, "-m", "yt_dlp",
                "--no-warnings",
                "-f", "bestvideo+bestaudio/best",
                "--merge-output-format", "mp4",
                "-o", output_template,
            ]

            # 添加 ffmpeg 路径
            if ffmpeg_path:
                cmd.extend(["--ffmpeg-location", os.path.dirname(ffmpeg_path)])

            # 添加 cookies
            if cookies:
                cookie_str = cookie_dict_to_str(cookies)
                cmd.extend(["--add-header", f"Cookie:{cookie_str}"])

            cmd.append(f"https://www.bilibili.com/video/{bvid}")

            if progress_callback:
                progress_callback(f"下载: {title[:40]}...")

            # 执行下载
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600
            )

            if result.returncode == 0:
                # 获取下载的文件
                output_files = list(output_dir.glob(f"{title}.mp4"))
                if output_files:
                    output_file = output_files[0]
                    file_size = output_file.stat().st_size / (1024 * 1024)

                    # 过滤大小
                    if MAX_SIZE_MB > 0 and file_size > MAX_SIZE_MB:
                        output_file.unlink()
                        if progress_callback:
                            progress_callback(f"删除 (过大): {title[:30]}")
                        continue

                    downloaded.append({
                        "bvid": bvid,
                        "title": title,
                        "path": str(output_file),
                        "duration": duration_str,
                        "size": file_size,
                        "favorite": video.get("favorites", "N/A"),
                        "keyword": keyword
                    })

                    if progress_callback:
                        progress_callback(f"完成: {title[:40]} ({file_size:.1f} MB)")
            else:
                if progress_callback:
                    progress_callback(f"下载失败: {title[:30]}")

        except subprocess.TimeoutExpired:
            if progress_callback:
                progress_callback(f"下载超时: {video.get('title', '')[:30]}")
        except Exception as e:
            if progress_callback:
                progress_callback(f"错误: {str(e)[:50]}")

    return downloaded


def _find_ffmpeg() -> str:
    """查找 ffmpeg 路径"""
    import shutil
    path = shutil.which("ffmpeg")
    if path:
        return path

    # 检查项目 bin 目录
    bin_dir = Path(__file__).resolve().parent.parent / "bin"
    if bin_dir.exists():
        ffmpeg_path = bin_dir / "ffmpeg.exe"
        if ffmpeg_path.exists():
            return str(ffmpeg_path)

    return ""
