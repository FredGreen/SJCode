"""
bilibili-search-download v1.0.0

Bilibili 关键词搜索 → 下载视频

功能:
  - 支持关键词搜索 B 站视频（B站搜索 API + yt-dlp 双引擎自动回退）
  - 自动查询视频格式，选择最高画质 video + 最高码率 audio 合并下载
  - 支持 cookies.txt（Get cookies.txt 插件导出）登录态下载
  - 自动检测 ffmpeg 环境

依赖:
  pip install requests yt-dlp
  ffmpeg: https://ffmpeg.org/download.html

用法:
  python bilibili_search_download.py "Python教程"
  python bilibili_search_download.py "机器学习"    # 自定义关键词
  python bilibili_search_download.py               # 默认关键词 Python教程

Cookie:
  将 "Get cookies.txt" 浏览器插件导出的 cookies.txt 放在脚本同目录即可

更新日志:
  v1.1.0 (2026-05-22) — 增加弹幕/收藏/点赞/发布日期展示，数字智能格式化(万/亿)，排序方式注释说明
  v1.0.0 (2026-05-22) — 首个正式版
    - B 站搜索 API（WBI 签名）+ yt-dlp 双搜索引擎
    - 明确格式 ID 下载，解决 bestvideo+bestaudio 选错格式导致只有音频的问题
    - Netscape 格式 cookies.txt 支持
    - ffmpeg 自动检测 + --ffmpeg-location 显式指定
    - UTF-8 编码处理，兼容 Windows GBK 终端
"""

__version__ = "1.1.0"

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
from http.cookiejar import MozillaCookieJar

import requests


# ===================== 配置 =====================

DEFAULT_PAGE_SIZE = 10
DOWNLOAD_DIR = "./bilibili_videos"
COOKIE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt")

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


# ===================== 搜索 =====================

def search_videos(keyword: str, page_size: int = DEFAULT_PAGE_SIZE) -> list[dict]:
    check_ytdlp()
    videos = _search_api(keyword, page_size)
    if videos:
        return videos
    print("[回退] API 搜索失败，尝试 yt-dlp 搜索...")
    return _search_ytdlp(keyword, page_size)


def _search_api(keyword: str, page_size: int) -> list[dict]:
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
        "order": "totalrank",
    }, img_key, sub_key)

    print(f"[搜索-API] 关键词: {keyword}")

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
        print(f"[API] 返回非 JSON，跳过")
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

        # ★ 跳过无效 URL
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
    """格式化数字：万以上显示 x.x万"""
    if not n or n == 0:
        return "0"
    if n >= 100000000:
        return f"{n / 100000000:.1f}亿"
    if n >= 10000:
        return f"{n / 10000:.1f}万"
    return str(n)


def _fmt_date(ts) -> str:
    """时间戳 → 日期字符串"""
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

    # 清理目录中的临时文件
    for f in os.listdir(save_dir):
        if f.endswith((".part", ".temp", ".ytdl")):
            os.remove(os.path.join(save_dir, f))

    success = fail = 0
    for v in videos:
        # ★ 跳过无效链接
        if not v["url"] or not v["url"].startswith("http"):
            print(f"\n[跳过] ({v['index']}/{len(videos)}) {v['title']} — 无有效链接")
            continue

        print(f"\n[下载] ({v['index']}/{len(videos)}) {v['title']}")
        print(f"       链接: {v['url']}")

        output_tpl = os.path.join(save_dir, "%(title).80s-%(id)s.%(ext)s")

        if has_ffmpeg:
            # 先查格式，明确指定 ID 下载
            fmt_output = query_formats(v["url"], has_cookie)
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
            # 简单验证：检查输出目录有没有新的大文件
            size_mb = 0
            newest = ""
            exts = (".mp4", ".mkv", ".webm")
            for f in os.listdir(save_dir):
                if f.endswith(exts):
                    p = os.path.join(save_dir, f)
                    s = os.path.getsize(p)
                    if s > size_mb:
                        size_mb = s
                        newest = f

            if size_mb > 1024 * 1024:  # > 1MB
                print(f"       ✓ 完成 ({size_mb / 1024 / 1024:.1f}MB)")
            elif size_mb > 0:
                print(f"       ✓ 完成 ({size_mb / 1024:.0f}KB，文件较小请确认)")
            else:
                print("       ✓ 完成")
            success += 1

        if v is not videos[-1]:
            time.sleep(3)

    print(f"\n[完成] 成功 {success}, 失败 {fail}，目录: {os.path.abspath(save_dir)}")


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

    keyword = sys.argv[1] if len(sys.argv) >= 2 else "蓝海赛道"

    videos = search_videos(keyword)
    if not videos:
        return

    print_video_list(videos)

    if input(f"下载以上 {len(videos)} 个视频？(y/n): ").strip().lower() != "y":
        print("已取消。")
        return

    download_videos(videos)

    json_path = os.path.join(DOWNLOAD_DIR, f"search_result_{keyword}.json")
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(videos, f, ensure_ascii=False, indent=2)
    print(f"[保存] 搜索结果: {json_path}")


if __name__ == "__main__":
    main()
