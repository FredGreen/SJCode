"""
bilibili-search-download v2.1.0

Bilibili 关键词搜索 → 下载视频

功能:
  - 单关键词模式: python bilibili_search_download.py "Python教程"
  - Excel 批量模式: python bilibili_search_download.py --excel tasks.xlsx
    Excel 格式: 检索关键词 | 排序方式 | 提取前N个视频
    排序方式: totalrank=综合排序, click=播放量, pubdate=最新发布, dm=弹幕数, stow=收藏数
  - 每个关键词自动建立独立目录存放视频
  - 自动查询视频格式，选择最高画质 video + 最高码率 audio 合并下载
  - 支持 cookies.txt（Get cookies.txt 插件导出）登录态下载
  - 自动检测 ffmpeg 环境
  - 通过 config/settings.py 统一管理输出目录

依赖:
  pip install requests yt-dlp openpyxl
  ffmpeg: https://ffmpeg.org/download.html

用法:
  python bilibili_search_download.py "Python教程"              # 单关键词
  python bilibili_search_download.py --excel tasks.xlsx         # Excel 批量模式
  python bilibili_search_download.py                            # 默认关键词 Python教程

Cookie:
  将 "Get cookies.txt" 浏览器插件导出的 cookies.txt 放在以下任一位置:
    1. 脚本同目录
    2. 项目根目录/config/cookies.txt
    3. 项目根目录/cookies.txt

目录结构:
  SJCode/
    config/
      __init__.py
      cookies.txt
      settings.py          ← 统一配置输出目录
    core/
      bilibili_search_download.py
    output/                 ← 下载输出根目录(settings.py 中配置)
      video/
        Python教程/         ← 按关键词建子目录
        AI入门/

更新日志:
  v2.1.0 (2026-05-23) — 集成 settings.py 配置管理，下载路径统一为 output/video/{keyword}/；增加时长+大小过滤
  v2.0.1 (2026-05-23) — Cookie 路径智能搜索，适配多级项目结构
  v2.0.0 (2026-05-22) — Excel 批量模式，每个关键词独立目录
  v1.1.0 (2026-05-22) — 增加弹幕/收藏/点赞/发布日期展示，数字智能格式化(万/亿)，排序方式注释说明
  v1.0.0 (2026-05-22) — 首个正式版
"""

__version__ = "2.1.0"

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
from http.cookiejar import MozillaCookieJar

import requests


# ===================== 配置导入 =====================

def _load_settings():
    """从 config/settings.py 加载配置，失败则使用默认值"""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
        from config.settings import VIDEO
        return str(VIDEO)
    except ImportError:
        print("[配置] 未找到 config/settings.py，使用默认输出目录")
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "bilibili_videos")


DOWNLOAD_DIR = _load_settings()

DEFAULT_PAGE_SIZE = 10

# 下载过滤阈值（0 表示不限制）
MAX_DURATION_MIN = 30      # 超过此分钟数，跳过
MAX_SIZE_MB = 300           # 超过此 MB 数，跳过

# 排序方式映射
ORDER_MAP = {
    "totalrank": "综合排序",
    "click": "播放量",
    "pubdate": "最新发布",
    "dm": "弹幕数",
    "stow": "收藏数",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://search.bilibili.com",
}


# ===================== 路径查找 =====================

def _find_cookie_file() -> str:
    """按优先级搜索 cookies.txt：脚本同目录 → ../config/ → 项目根目录"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(script_dir, "cookies.txt"),                    # 脚本同目录
        os.path.join(script_dir, "..", "config", "cookies.txt"),    # config/ 子目录
        os.path.join(script_dir, "..", "cookies.txt"),              # 项目根目录
    ]
    for p in candidates:
        if os.path.isfile(p):
            return os.path.normpath(p)
    # 都没找到，返回默认路径（后续会提示不存在）
    return os.path.join(script_dir, "cookies.txt")


COOKIE_FILE = _find_cookie_file()


# ===================== 环境检查 =====================

def _find_ffmpeg_path() -> str:
    path = shutil.which("ffmpeg")
    if path:
        return path
    for d in [
        os.path.join(os.environ.get("ProgramFiles", ""), "ffmpeg", "bin"),
        os.path.join(os.environ.get("ProgramFiles", ""), "FFmpeg", "bin"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "ffmpeg", "bin"),
        "C:\\ffmpeg\\bin",
    ]:
        exe = os.path.join(d, "ffmpeg.exe")
        if os.path.isfile(exe):
            return exe
    return ""


def check_ffmpeg() -> tuple[bool, str]:
    path = _find_ffmpeg_path()
    if not path:
        return False, ""
    try:
        subprocess.run([path, "-version"], capture_output=True, check=True)
        return True, path
    except Exception:
        return False, ""


def check_ytdlp():
    try:
        subprocess.run(["yt-dlp", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("[错误] yt-dlp 未安装，请运行: pip install yt-dlp")
        sys.exit(1)


# ===================== Cookie 加载 =====================

def load_cookies(cookie_file: str) -> dict:
    if not os.path.isfile(cookie_file):
        return {}
    jar = MozillaCookieJar(cookie_file)
    try:
        jar.load(ignore_discard=True, ignore_expires=True)
    except Exception as e:
        print(f"[警告] cookies.txt 解析失败: {e}")
        return {}
    return {c.name: c.value for c in jar if "bilibili" in c.domain}


def cookie_dict_to_str(cookies: dict) -> str:
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


def _init_cookies():
    print(f"[Cookie] 文件: {COOKIE_FILE}")
    print(f"[Cookie] 存在: {os.path.isfile(COOKIE_FILE)}")
    cookies = load_cookies(COOKIE_FILE)
    if cookies:
        HEADERS["Cookie"] = cookie_dict_to_str(cookies)
        print(f"[Cookie] 加载 {len(cookies)} 条")
        critical = ["SESSDATA", "bili_jct", "buvid3", "buvid4"]
        found = [k for k in critical if k in cookies]
        missing = [k for k in critical if k not in cookies]
        if found:
            print(f"[Cookie] 关键项: {', '.join(found)} ✓")
        if missing:
            print(f"[Cookie] 缺失项: {', '.join(missing)} ✗")
    else:
        HEADERS["Cookie"] = ""
        print("[Cookie] 未加载到 Cookie")


# ===================== 通用工具 =====================

def _decode(result) -> tuple[str, str]:
    stdout = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
    stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
    return stdout, stderr


def _run(cmd, timeout=600):
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
        stdout, stderr = _decode(r)
        return r.returncode, stdout, stderr
    except subprocess.TimeoutExpired:
        return -1, "", "超时"
    except Exception as e:
        return -2, "", str(e)


def _parse_duration_minutes(duration_str: str) -> float:
    """解析时长字符串为分钟数，支持 '1:23:45' / '23:45' / '45' 等格式"""
    if not duration_str:
        return 0
    parts = str(duration_str).strip().split(":")
    try:
        if len(parts) == 3:       # H:MM:SS
            return int(parts[0]) * 60 + int(parts[1]) + int(parts[2]) / 60
        elif len(parts) == 2:     # MM:SS
            return int(parts[0]) + int(parts[1]) / 60
        else:                     # 纯秒数
            return float(parts[0]) / 60
    except (ValueError, IndexError):
        return 0


def _parse_size_mb(fmt_output: str) -> float:
    """从 yt-dlp -F 输出中解析 video+audio 合并预估大小(MB)"""
    video_size = audio_size = 0.0
    best_video_res = 0
    best_audio_br = 0

    for line in fmt_output.split("\n"):
        parts = line.strip().split()
        if len(parts) < 4:
            continue

        # 解析大小 ≈XX.XXMiB 或 ≈XX.XXGiB
        size_mb = 0.0
        for p in parts:
            if p.startswith("≈") or p.startswith("~"):
                p = p[1:]
            if p.endswith("GiB"):
                try:
                    size_mb = float(p[:-3]) * 1024
                except ValueError:
                    pass
                break
            elif p.endswith("MiB"):
                try:
                    size_mb = float(p[:-3])
                except ValueError:
                    pass
                break
            elif p.endswith("KiB"):
                try:
                    size_mb = float(p[:-3]) / 1024
                except ValueError:
                    pass
                break

        if "video only" in line:
            try:
                w, h = parts[2].split("x")
                res = int(w) * int(h)
                if res > best_video_res:
                    best_video_res = res
                    video_size = size_mb
            except (ValueError, IndexError):
                continue
        elif "audio only" in line:
            for p in parts:
                if p.endswith("k") and p[:-1].isdigit():
                    br = int(p[:-1])
                    if br > best_audio_br:
                        best_audio_br = br
                        audio_size = size_mb
                    break

    return video_size + audio_size


def _filter_videos(videos: list[dict]) -> list[dict]:
    """按时长过滤搜索结果，返回可下载列表"""
    if not MAX_DURATION_MIN:
        return videos

    filtered = []
    for v in videos:
        dur_min = _parse_duration_minutes(v.get("duration", ""))
        if dur_min > MAX_DURATION_MIN:
            print(f"[过滤] 「{v['title'][:40]}」 时长 {v['duration']} 超过 {MAX_DURATION_MIN}分钟，跳过")
            continue
        filtered.append(v)

    # 重新编号
    for i, v in enumerate(filtered, 1):
        v["index"] = i

    skipped = len(videos) - len(filtered)
    if skipped:
        print(f"[过滤] 共跳过 {skipped} 个超长视频，剩余 {len(filtered)} 个")
    return filtered


def _safe_dirname(name: str) -> str:
    """将关键词转为安全的目录名，处理特殊字符和保留名"""
    # Windows 不允许的字符: \ / : * ? " < > |
    for ch in ['\\', '/', ':', '*', '?', '"', '<', '>', '|']:
        name = name.replace(ch, '_')
    # 控制字符
    name = re.sub(r'[\x00-\x1f\x7f]', '_', name)
    # 去首尾空格、点和下划线
    name = name.strip('. _')
    # 连续下划线合并
    name = re.sub(r'_+', '_', name)
    # Windows 保留名: CON, PRN, AUX, NUL, COM1-9, LPT1-9
    reserved = {"CON", "PRN", "AUX", "NUL"}
    reserved.update(f"COM{i}" for i in range(1, 10))
    reserved.update(f"LPT{i}" for i in range(1, 10))
    if name.upper() in reserved:
        name = f"_{name}_"
    # 限制长度（NTFS 255 字符，留余量）
    return name[:80] if name else "unnamed"


# ===================== WBI 签名 =====================

_MIXIN_TABLE = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 16,
    20, 36, 34, 17, 6, 22, 48, 44, 13, 24, 52, 37, 4, 55, 25, 51,
    7, 56, 40, 30, 59, 21, 1, 26, 11, 54, 57, 0, 61, 63, 60, 62,
]
_ILLEGAL_CHARS = "!'()*"


def _extract_key(url: str) -> str:
    return url.split("/")[-1].split(".")[0]


def _mixin_key(raw: str) -> str:
    return "".join(raw[i] for i in _MIXIN_TABLE)[:32]


def _fetch_wbi_keys(session: requests.Session) -> tuple[str, str]:
    resp = session.get(
        "https://api.bilibili.com/x/web-interface/nav",
        headers=HEADERS, timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"WBI 密钥获取失败: {data.get('message')}")
    wbi = data["data"]["wbi_img"]
    return _extract_key(wbi["img_url"]), _extract_key(wbi["sub_url"])


def sign_params(params: dict, img_key: str, sub_key: str) -> dict:
    key = _mixin_key(img_key + sub_key)
    params = {**params, "wts": int(time.time())}
    cleaned = {}
    for k, v in sorted(params.items()):
        cleaned[k] = str(v).translate(str.maketrans("", "", _ILLEGAL_CHARS))
    query = urllib.parse.urlencode(cleaned)
    cleaned["w_rid"] = hashlib.md5((query + key).encode()).hexdigest()
    return cleaned


# ===================== Excel 读取 =====================

def read_excel_tasks(filepath: str) -> list[dict]:
    """
    读取 Excel 任务文件
    格式: 检索关键词 | 排序方式 | 提取前N个视频
    返回: [{"keyword": "xxx", "order": "totalrank", "count": 5}, ...]
    """
    try:
        import openpyxl
    except ImportError:
        print("[错误] 需要 openpyxl 库，请运行: pip install openpyxl")
        sys.exit(1)

    if not os.path.isfile(filepath):
        print(f"[错误] Excel 文件不存在: {filepath}")
        sys.exit(1)

    wb = openpyxl.load_workbook(filepath, read_only=True)
    ws = wb.active

    tasks = []
    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
        if not row or not row[0]:
            continue

        keyword = str(row[0]).strip()
        if not keyword:
            continue

        # 排序方式，默认综合排序
        order = str(row[1]).strip().lower() if len(row) > 1 and row[1] else "totalrank"
        if order not in ORDER_MAP:
            print(f"[警告] 第{row_idx}行 排序方式 '{order}' 不合法，使用默认 totalrank")
            order = "totalrank"

        # 提取数量，默认5
        count = 5
        if len(row) > 2 and row[2]:
            try:
                count = int(row[2])
            except (ValueError, TypeError):
                print(f"[警告] 第{row_idx}行 提取数量 '{row[2]}' 不合法，使用默认 5")

        tasks.append({
            "keyword": keyword,
            "order": order,
            "order_label": ORDER_MAP.get(order, order),
            "count": count,
        })

    wb.close()
    return tasks


def print_tasks(tasks: list[dict]):
    """打印任务清单"""
    header = f"{'序号':<4} {'检索关键词':<20} {'排序方式':<12} {'提取数量':<8}"
    print("\n" + "=" * 50)
    print("任务清单:")
    print(header)
    print("-" * 50)
    for i, t in enumerate(tasks, 1):
        print(f"{i:<4} {t['keyword']:<20} {t['order_label']:<12} {t['count']:<8}")
    print("=" * 50 + "\n")


# ===================== 搜索 =====================

def search_videos(keyword: str, page_size: int = DEFAULT_PAGE_SIZE,
                  order: str = "totalrank") -> list[dict]:
    check_ytdlp()
    videos = _search_api(keyword, page_size, order)
    if videos:
        return videos
    print("[回退] API 搜索失败，尝试 yt-dlp 搜索...")
    return _search_ytdlp(keyword, page_size)


def _search_api(keyword: str, page_size: int, order: str = "totalrank") -> list[dict]:
    session = requests.Session()
    cookies = load_cookies(COOKIE_FILE)
    if cookies:
        session.cookies = requests.utils.cookiejar_from_dict(cookies)

    try:
        img_key, sub_key = _fetch_wbi_keys(session)
    except Exception as e:
        print(f"[API] WBI 密钥获取失败({e})，跳过")
        return []

    params = sign_params({
        "search_type": "video",
        "keyword": keyword,
        "page": 1,
        "page_size": page_size,
        # 排序方式：totalrank=综合排序(默认), click=播放量, pubdate=最新发布, dm=弹幕数, stow=收藏数
        "order": order,
    }, img_key, sub_key)

    order_label = ORDER_MAP.get(order, order)
    print(f"[搜索-API] 关键词: {keyword}，排序: {order_label}，数量: {page_size}")

    try:
        resp = session.get(
            "https://api.bilibili.com/x/web-interface/wbi/search/type",
            params=params, headers=HEADERS, timeout=15,
        )
    except Exception as e:
        print(f"[API] 请求失败: {e}")
        return []

    content_type = resp.headers.get("content-type", "")
    if "json" not in content_type:
        print("[API] 返回非 JSON，跳过")
        return []

    try:
        data = resp.json()
    except Exception:
        print("[API] JSON 解析失败，跳过")
        return []

    if data.get("code") != 0:
        print(f"[API] 错误: code={data.get('code')}, message={data.get('message')}")
        return []

    results = data.get("data", {}).get("result", [])
    if not results:
        print("[API] 无结果")
        return []

    videos = []
    for i, item in enumerate(results, 1):
        title = item.get("title", "").replace('<em class="keyword">', "").replace("</em>", "")
        bvid = item.get("bvid", "")
        url = f"https://www.bilibili.com/video/{bvid}" if bvid else ""
        if not url:
            continue
        videos.append({
            "index": len(videos) + 1, "title": title, "bvid": bvid,
            "aid": item.get("aid", 0),
            "author": item.get("author", ""),
            "play": item.get("play", 0),
            "danmaku": item.get("video_review", 0),
            "favorites": item.get("favorites", 0),
            "like": item.get("like", 0),
            "duration": item.get("duration", ""),
            "pubdate": item.get("pubdate", 0),
            "tag": item.get("tag", ""),
            "url": url,
        })

    print(f"[搜索-API] 找到 {len(videos)} 条结果")
    return videos


def _search_ytdlp(keyword: str, page_size: int) -> list[dict]:
    search_url = f"https://search.bilibili.com/video?keyword={urllib.parse.quote(keyword)}"
    cmd = [
        "yt-dlp", "--flat-playlist", "--dump-json",
        "--playlist-end", str(page_size), "--no-warnings",
    ]
    if os.path.isfile(COOKIE_FILE):
        cmd.extend(["--cookies", COOKIE_FILE])
    cmd.append(search_url)

    print(f"[搜索-yt-dlp] 关键词: {keyword}")

    code, stdout, _ = _run(cmd, timeout=120)

    if code != 0 or not stdout.strip():
        print("       搜索页失败，尝试 bilisearch: ...")
        cmd2 = [
            "yt-dlp", "--flat-playlist", "--dump-json",
            "--playlist-end", str(page_size), "--no-warnings",
        ]
        if os.path.isfile(COOKIE_FILE):
            cmd2.extend(["--cookies", COOKIE_FILE])
        cmd2.append(f"bilisearch:{keyword}")
        code2, stdout2, _ = _run(cmd2, timeout=120)
        if code2 == 0 and stdout2.strip():
            stdout = stdout2
        else:
            print("[错误] 所有搜索方式均失败")
            return []

    videos = []
    for i, line in enumerate(stdout.strip().split("\n"), 1):
        if not line.strip():
            continue
        try:
            info = json.loads(line)
        except json.JSONDecodeError:
            continue

        title = info.get("title", "") or info.get("alt_title", "") or ""
        url = info.get("url") or info.get("webpage_url") or info.get("original_url", "")
        bvid = ""
        if "/video/" in url:
            bvid = url.split("/video/")[-1].split("/")[0].split("?")[0]
        elif url.startswith("BV"):
            bvid = url
        if bvid and not url.startswith("http"):
            url = f"https://www.bilibili.com/video/{bvid}"

        if not url.startswith("http"):
            continue

        duration = info.get("duration_string") or ""
        if not duration and info.get("duration"):
            m, s = divmod(int(info["duration"]), 60)
            duration = f"{m}:{s:02d}"

        if title or bvid:
            videos.append({
                "index": len(videos) + 1, "title": title, "bvid": bvid,
                "aid": info.get("id", ""),
                "author": info.get("uploader") or info.get("channel") or "",
                "play": info.get("view_count") or 0,
                "danmaku": info.get("comment_count") or 0,
                "favorites": info.get("like_count") or 0,
                "like": 0,
                "duration": duration, "pubdate": 0,
                "tag": "", "url": url,
            })

    print(f"[搜索-yt-dlp] 找到 {len(videos)} 条结果" if videos else "[搜索] 无结果")
    return videos[:page_size]


# ===================== 展示 =====================

def _fmt_num(n) -> str:
    if not n or n == 0:
        return "0"
    if n >= 100000000:
        return f"{n / 100000000:.1f}亿"
    if n >= 10000:
        return f"{n / 10000:.1f}万"
    return str(n)


def _fmt_date(ts) -> str:
    if not ts or ts == 0:
        return ""
    try:
        from datetime import datetime
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    except Exception:
        return ""


def print_video_list(videos: list[dict]):
    header = (
        f"{'序号':<4} {'标题':<32} {'UP主':<10} "
        f"{'播放':>7} {'弹幕':>6} {'收藏':>6} {'点赞':>6} "
        f"{'时长':<7} {'发布日期':<11}"
    )
    print("\n" + "=" * 100)
    print(header)
    print("-" * 100)
    for v in videos:
        title = v["title"][:30] + ".." if len(v["title"]) > 32 else v["title"]
        author = v["author"][:8] + ".." if len(v["author"]) > 10 else v["author"]
        play = _fmt_num(v.get("play", 0))
        danmaku = _fmt_num(v.get("danmaku", 0))
        favorites = _fmt_num(v.get("favorites", 0))
        like = _fmt_num(v.get("like", 0))
        duration = v.get("duration", "")
        pubdate = _fmt_date(v.get("pubdate", 0))
        print(
            f"{v['index']:<4} {title:<32} {author:<10} "
            f"{play:>7} {danmaku:>6} {favorites:>6} {like:>6} "
            f"{duration:<7} {pubdate:<11}"
        )
    print("=" * 100 + "\n")


# ===================== 格式查询与选择 =====================

def query_formats(url: str, has_cookie: bool) -> str:
    cmd = ["yt-dlp", "-F", "--no-warnings", "--no-playlist"]
    if has_cookie:
        cmd.extend(["--cookies", COOKIE_FILE])
    cmd.append(url)
    code, stdout, _ = _run(cmd, timeout=30)
    return stdout if code == 0 else ""


def pick_best_formats(fmt_output: str) -> tuple[str, str]:
    best_video_id = ""
    best_video_res = 0
    best_audio_id = ""
    best_audio_br = 0

    for line in fmt_output.split("\n"):
        parts = line.strip().split()
        if len(parts) < 4:
            continue
        fmt_id = parts[0]

        if "video only" in line:
            try:
                w, h = parts[2].split("x")
                res = int(w) * int(h)
                if res > best_video_res:
                    best_video_res = res
                    best_video_id = fmt_id
            except (ValueError, IndexError):
                continue

        elif "audio only" in line:
            for p in parts:
                if p.endswith("k") and p[:-1].isdigit():
                    br = int(p[:-1])
                    if br > best_audio_br:
                        best_audio_br = br
                        best_audio_id = fmt_id
                    break

    return best_video_id, best_audio_id


# ===================== 下载 =====================

def download_videos(videos: list[dict], save_dir: str = DOWNLOAD_DIR):
    os.makedirs(save_dir, exist_ok=True)
    check_ytdlp()

    has_ffmpeg, ffmpeg_path = check_ffmpeg()
    has_cookie = os.path.isfile(COOKIE_FILE)
    ffmpeg_dir = os.path.dirname(ffmpeg_path) if has_ffmpeg else ""

    if has_ffmpeg:
        print(f"[环境] ffmpeg ✓ {ffmpeg_path}")
    else:
        print("[环境] ⚠ ffmpeg 未检测到，视频可能只有声音")

    # 清理临时文件
    for f in os.listdir(save_dir):
        if f.endswith((".part", ".temp", ".ytdl")):
            os.remove(os.path.join(save_dir, f))

    # 扫描已有文件，避免重复下载
    existing_ids = set()
    if os.path.isdir(save_dir):
        for f in os.listdir(save_dir):
            # 文件名格式: 标题-BVID.mp4，提取 BVID 部分
            name = os.path.splitext(f)[0]
            for part in name.split("-"):
                if part.startswith("BV") and len(part) >= 10:
                    existing_ids.add(part)

    skipped_exist = 0
    success = fail = 0
    for v in videos:
        if not v["url"] or not v["url"].startswith("http"):
            print(f"\n[跳过] ({v['index']}/{len(videos)}) {v['title']} — 无有效链接")
            continue

        # 跳过已存在的视频
        bvid = v.get("bvid", "")
        if bvid and bvid in existing_ids:
            print(f"\n[跳过] ({v['index']}/{len(videos)}) {v['title'][:40]} — 已存在")
            skipped_exist += 1
            continue

        print(f"\n[下载] ({v['index']}/{len(videos)}) {v['title']}")
        print(f"       链接: {v['url']}")

        output_tpl = os.path.join(save_dir, "%(title).80s-%(id)s.%(ext)s")

        if has_ffmpeg:
            fmt_output = query_formats(v["url"], has_cookie)

            # 大小过滤：解析预估大小
            if MAX_SIZE_MB:
                est_size = _parse_size_mb(fmt_output)
                if est_size > MAX_SIZE_MB:
                    print(f"       ✗ 预估 {est_size:.0f}MB 超过 {MAX_SIZE_MB}MB，跳过")
                    fail += 1
                    continue
                else:
                    print(f"       预估大小: {est_size:.0f}MB ✓")

            video_id, audio_id = pick_best_formats(fmt_output)

            if video_id and audio_id:
                explicit_fmt = f"{video_id}+{audio_id}"
                print(f"       格式: {explicit_fmt}")
            else:
                explicit_fmt = "bestvideo+bestaudio/best"
                print(f"       回退格式: {explicit_fmt}")

            cmd = [
                "yt-dlp", "--no-warnings", "--no-playlist",
                "-f", explicit_fmt,
                "--merge-output-format", "mp4",
                "--ffmpeg-location", ffmpeg_dir,
                "-o", output_tpl,
            ]
        else:
            cmd = [
                "yt-dlp", "--no-warnings", "--no-playlist",
                "-f", "best",
                "-o", output_tpl,
            ]

        if has_cookie:
            cmd.extend(["--cookies", COOKIE_FILE])
        cmd.append(v["url"])

        print("       下载中...")
        code, stdout, stderr = _run(cmd)

        if code != 0:
            err = stderr.strip().split("\n")[-1] if stderr.strip() else "未知错误"
            print(f"       ✗ 失败: {err}")
            fail += 1
        else:
            size_mb = 0
            exts = (".mp4", ".mkv", ".webm")
            for f in os.listdir(save_dir):
                if f.endswith(exts):
                    p = os.path.join(save_dir, f)
                    s = os.path.getsize(p)
                    if s > size_mb:
                        size_mb = s

            if size_mb > 1024 * 1024:
                print(f"       ✓ 完成 ({size_mb / 1024 / 1024:.1f}MB)")
            elif size_mb > 0:
                print(f"       ✓ 完成 ({size_mb / 1024:.0f}KB)")
            else:
                print("       ✓ 完成")
            success += 1

        if v is not videos[-1]:
            time.sleep(3)

    skipped_info = f"，跳过已存在 {skipped_exist}" if skipped_exist else ""
    print(f"\n[完成] 成功 {success}, 失败 {fail}{skipped_info}，目录: {os.path.abspath(save_dir)}")
    return success, fail


# ===================== 单关键词模式 =====================

def run_single(keyword: str):
    """单关键词搜索下载模式"""
    videos = search_videos(keyword)
    if not videos:
        return

    # 时长过滤
    videos = _filter_videos(videos)
    if not videos:
        print("[提示] 过滤后无符合条件的视频")
        return

    print_video_list(videos)

    if input(f"下载以上 {len(videos)} 个视频？(y/n): ").strip().lower() != "y":
        print("已取消。")
        return

    # 目录: ./bilibili_videos/关键词/
    save_dir = os.path.join(DOWNLOAD_DIR, _safe_dirname(keyword))
    download_videos(videos, save_dir)

    # 保存搜索结果
    json_path = os.path.join(save_dir, f"search_result_{keyword}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(videos, f, ensure_ascii=False, indent=2)
    print(f"[保存] 搜索结果: {json_path}")


# ===================== Excel 批量模式 =====================

def run_excel(filepath: str):
    """Excel 批量搜索下载模式"""
    tasks = read_excel_tasks(filepath)
    if not tasks:
        print("[错误] Excel 中没有有效任务")
        return

    print_tasks(tasks)

    total_videos = sum(t["count"] for t in tasks)
    print(f"共 {len(tasks)} 个任务，预计下载 {total_videos} 个视频\n")

    if input("确认开始？(y/n): ").strip().lower() != "y":
        print("已取消。")
        return

    total_success = 0
    total_fail = 0
    task_results = []

    for i, task in enumerate(tasks, 1):
        keyword = task["keyword"]
        order = task["order"]
        count = task["count"]
        order_label = task["order_label"]

        print(f"\n{'#' * 60}")
        print(f"# 任务 {i}/{len(tasks)}: 「{keyword}」 排序:{order_label} 数量:{count}")
        print(f"{'#' * 60}")

        # 搜索
        videos = search_videos(keyword, page_size=count, order=order)
        if not videos:
            task_results.append({"keyword": keyword, "success": 0, "fail": 0, "status": "搜索无结果"})
            continue

        # 时长过滤
        videos = _filter_videos(videos)
        if not videos:
            task_results.append({"keyword": keyword, "success": 0, "fail": 0, "status": "过滤后无视频"})
            continue

        print_video_list(videos)

        # 目录: ./bilibili_videos/关键词/
        save_dir = os.path.join(DOWNLOAD_DIR, _safe_dirname(keyword))

        # 下载
        s, f = download_videos(videos, save_dir)
        total_success += s
        total_fail += f

        # 保存搜索结果 JSON
        json_path = os.path.join(save_dir, f"search_result_{keyword}.json")
        with open(json_path, "w", encoding="utf-8") as f_json:
            json.dump(videos, f_json, ensure_ascii=False, indent=2)

        task_results.append({
            "keyword": keyword,
            "order": order_label,
            "count": count,
            "found": len(videos),
            "success": s,
            "fail": f,
            "status": "完成",
        })

        # 任务间隔
        if i < len(tasks):
            print(f"\n[等待] 5秒后继续下一个任务...")
            time.sleep(5)

    # 汇总报告
    print("\n" + "=" * 70)
    print("汇总报告")
    print("=" * 70)
    header = f"{'关键词':<16} {'排序':<10} {'提取':<5} {'找到':<5} {'成功':<5} {'失败':<5} {'状态':<10}"
    print(header)
    print("-" * 70)
    for r in task_results:
        print(
            f"{r.get('keyword', ''):<16} "
            f"{r.get('order', ''):<10} "
            f"{r.get('count', ''):<5} "
            f"{r.get('found', ''):<5} "
            f"{r.get('success', ''):<5} "
            f"{r.get('fail', ''):<5} "
            f"{r.get('status', ''):<10}"
        )
    print("-" * 70)
    print(f"总计: 成功 {total_success}, 失败 {total_fail}")
    print(f"视频保存目录: {os.path.abspath(DOWNLOAD_DIR)}")
    print("=" * 70)

    # 保存汇总报告
    report_path = os.path.join(DOWNLOAD_DIR, "batch_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_success": total_success,
            "total_fail": total_fail,
            "tasks": task_results,
        }, f, ensure_ascii=False, indent=2)
    print(f"[保存] 汇总报告: {report_path}")


# ===================== 主流程 =====================

def main():
    print(f"bilibili-search-download v{__version__}\n")

    has_ffmpeg, ffmpeg_path = check_ffmpeg()
    if has_ffmpeg:
        print(f"[环境] ffmpeg ✓ {ffmpeg_path}")
    else:
        print("[环境] ⚠ ffmpeg 未检测到")
        print("       安装: https://ffmpeg.org/download.html\n")

    _init_cookies()

    # 解析参数
    if len(sys.argv) >= 3 and sys.argv[1] == "--excel":
        # Excel 批量模式
        run_excel(sys.argv[2])
    elif len(sys.argv) >= 2 and sys.argv[1] != "--excel":
        # 单关键词模式
        run_single(sys.argv[1])
    else:
        # 无参数，显示帮助
        print("用法:")
        print('  python bilibili_search_download.py "Python教程"       # 单关键词')
        print("  python bilibili_search_download.py --excel tasks.xlsx  # Excel 批量模式")
        print()
        if input("使用默认关键词「Python教程」继续？(y/n): ").strip().lower() == "y":
            run_single("Python教程")


if __name__ == "__main__":
    main()
