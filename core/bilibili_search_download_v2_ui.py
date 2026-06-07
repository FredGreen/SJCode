# -*- coding: utf-8 -*-
"""
B站视频下载 - UI 集成版本
复用 core/bilibili_search_download_v2.py 的核心逻辑，
提供与 UI 集成的接口。
"""
import os
import re
import subprocess
import sys
import time
import hashlib
import urllib.parse
from pathlib import Path
from typing import Callable, Optional, List, Dict

# 添加项目路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import VIDEO

# 导入原版下载器的核心函数
sys.path.insert(0, str(Path(__file__).resolve().parent))
from bilibili_search_download_v2 import (
    HEADERS, COOKIE_FILE, load_cookies, cookie_dict_to_str,
    _parse_duration_minutes, ORDER_MAP,
    DEFAULT_PAGE_SIZE, MAX_DURATION_MIN, MAX_SIZE_MB,
    _fetch_wbi_keys, sign_params, _safe_dirname
)

import requests


def download_keyword_videos(
    keyword: str,
    order: str = "totalrank",
    limit: int = 5,
    progress_callback: Optional[Callable] = None
) -> List[Dict]:
    """
    下载指定关键词的视频（使用 WBI 签名）
    Args:
        keyword: 搜索关键词
        order: 排序方式 (totalrank/click/pubdate/dm/stow)
        limit: 下载数量上限
        progress_callback: 进度回调函数
    Returns:
        下载成功的视频信息列表
    """
    print(f"[DownloadWorker] 开始搜索关键词: {keyword}, 排序: {order}, 数量: {limit}")

    # 加载 cookies
    cookies = load_cookies(COOKIE_FILE)
    if cookies:
        HEADERS["Cookie"] = cookie_dict_to_str(cookies)

    session = requests.Session()
    if cookies:
        session.cookies = requests.utils.cookiejar_from_dict(cookies)

    # 获取 WBI 签名密钥
    try:
        img_key, sub_key = _fetch_wbi_keys(session)
        print(f"[DownloadWorker] WBI 密钥获取成功")
    except Exception as e:
        print(f"[DownloadWorker] WBI 密钥获取失败: {e}")
        if progress_callback:
            progress_callback(f"WBI密钥获取失败: {str(e)}")
        return []

    # 构建带签名的搜索参数
    search_params = {
        "search_type": "video",
        "keyword": keyword,
        "page": 1,
        "page_size": min(limit * 2, 20),
        "order": order,
    }

    signed_params = sign_params(search_params, img_key, sub_key)

    print(f"[DownloadWorker] 调用 B站搜索 API...")

    # 搜索视频
    try:
        resp = session.get(
            "https://api.bilibili.com/x/web-interface/wbi/search/type",
            params=signed_params,
            headers=HEADERS,
            timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[DownloadWorker] API 请求失败: {e}")
        if progress_callback:
            progress_callback(f"搜索失败: {str(e)}")
        return []

    print(f"[DownloadWorker] API 返回: code={data.get('code')}, message={data.get('message')}")

    if data.get("code") != 0:
        print(f"[DownloadWorker] 搜索失败: {data.get('message')}")
        if progress_callback:
            progress_callback(f"搜索失败: {data.get('message')}")
        return []

    videos = data.get("data", {}).get("result", [])
    print(f"[DownloadWorker] 搜索到 {len(videos)} 个视频")

    if not videos:
        if progress_callback:
            progress_callback("未找到视频")
        return []

    downloaded = []

    # 查找 ffmpeg 路径
    ffmpeg_path = _find_ffmpeg()

    for i, video in enumerate(videos[:limit], 1):
        try:
            bvid = video.get("bvid", "")
            title = video.get("title", "")

            # 清理标题中的非法字符和 HTML 实体
            title = re.sub(r'[\\/:*?"<>|]', '_', title)  # Windows 非法字符
            title = re.sub(r'&[a-z]+;', '', title)       # HTML 实体
            title = re.sub(r'[<>\'\"]', '_', title)      # 额外清理
            title = re.sub(r'_{2,}', '_', title)         # 多个下划线合并
            title = title.strip().strip('._')            # 去除首尾空格和点下划线
            
            # 限制文件名长度（Windows 路径限制）
            if len(title) > 100:
                title = title[:100]
            
            if not title:
                title = f"video_{bvid}"

            duration_str = video.get("duration", "0:00")
            duration_min = _parse_duration_minutes(duration_str)

            # 过滤时长
            if MAX_DURATION_MIN > 0 and duration_min > MAX_DURATION_MIN:
                print(f"[DownloadWorker] 跳过 (时长过长): {title[:30]}")
                if progress_callback:
                    progress_callback(f"跳过 (时长过长): {title[:30]}")
                continue

            if progress_callback:
                progress_callback(f"下载 [{i}/{min(limit, len(videos))}]: {title[:40]}...")

            # 创建输出目录
            safe_keyword = _safe_dirname(keyword)
            output_dir = VIDEO / safe_keyword
            output_dir.mkdir(parents=True, exist_ok=True)

            # yt-dlp 下载命令
            cmd = [
                sys.executable, "-m", "yt_dlp",
                "--no-warnings",
                "-f", "bestvideo+bestaudio/best",
                "--merge-output-format", "mp4",
                "-o", str(output_dir / f"{title}.%(ext)s"),
            ]

            # 添加 ffmpeg 路径
            if ffmpeg_path:
                cmd.extend(["--ffmpeg-location", os.path.dirname(ffmpeg_path)])

            # 添加 cookies
            if cookies:
                cookie_str = cookie_dict_to_str(cookies)
                cmd.extend(["--add-header", f"Cookie:{cookie_str}"])

            cmd.append(f"https://www.bilibili.com/video/{bvid}")

            print(f"[DownloadWorker] 执行下载: {title}")

            # 执行下载（使用 utf-8 编码避免 Windows gbk 解码错误）
            result = subprocess.run(
                cmd,
                capture_output=True,
                encoding='utf-8',
                errors='ignore',
                timeout=600
            )

            if result.returncode == 0:
                # 查找下载的文件
                output_files = list(output_dir.glob(f"{title}.mp4"))
                if output_files:
                    output_file = output_files[0]
                    file_size = output_file.stat().st_size / (1024 * 1024)

                    # 过滤大小
                    if MAX_SIZE_MB > 0 and file_size > MAX_SIZE_MB:
                        output_file.unlink()
                        print(f"[DownloadWorker] 删除 (过大): {title[:30]}")
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
                    print(f"[DownloadWorker] 下载成功: {title} ({file_size:.1f} MB)")
                    if progress_callback:
                        progress_callback(f"完成: {title[:40]} ({file_size:.1f} MB)")
            else:
                print(f"[DownloadWorker] 下载失败: {title}, error={result.stderr[:200]}")
                if progress_callback:
                    progress_callback(f"下载失败: {title[:30]}")

        except subprocess.TimeoutExpired:
            print(f"[DownloadWorker] 下载超时: {video.get('title', '')[:30]}")
            if progress_callback:
                progress_callback(f"下载超时")
        except Exception as e:
            print(f"[DownloadWorker] 错误: {e}")
            if progress_callback:
                progress_callback(f"错误: {str(e)[:50]}")

    print(f"[DownloadWorker] 下载完成, 找到 {len(downloaded)} 个视频")
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
