# -*- coding: utf-8 -*-
"""
视频转 Markdown 工具 - ASR 客户端
基于阿里云百炼 paraformer-v2 录音文件识别 API

流程：
1. 检查本地缓存，命中则直接返回
2. 上传本地文件到 DashScope 临时 OSS → 获得 oss:// URL
3. 提交异步转写任务
4. 轮询等待完成
5. 解析返回的 JSON 结果并缓存
"""

import os
import json
import time
import requests
from pathlib import Path
from http import HTTPStatus
from urllib import request as urllib_request

from dashscope.audio.asr import Transcription
import dashscope

from parser.config import DASHSCOPE_API_KEY, ASR_MODEL, ASR_LANGUAGE_HINTS, ASR_CACHE_DIR

# oss:// URL 需要此请求头，否则后端无法解析
OSS_HEADERS = {"X-DashScope-OssResourceResolve": "enable"}


def _cache_path(file_path: str) -> str:
    """根据视频文件路径生成缓存文件路径"""
    video_name = Path(file_path).stem
    return os.path.join(ASR_CACHE_DIR, f"{video_name}.asr.json")


def _load_cache(file_path: str) -> list[dict] | None:
    """
    检查缓存是否有效。
    验证条件：缓存文件存在，且视频文件大小和修改时间与缓存记录一致。
    """
    cache_file = _cache_path(file_path)
    if not os.path.isfile(cache_file):
        return None

    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            cache = json.load(f)
    except (json.JSONDecodeError, KeyError):
        return None

    # 验证视频文件是否变化
    stat = os.stat(file_path)
    if cache.get("video_size") != stat.st_size or cache.get("video_mtime") != int(stat.st_mtime):
        print("  缓存失效（视频文件已变化），重新转写")
        return None

    sentences = cache.get("sentences", [])
    duration_ms = cache.get("duration_ms", 0)
    duration_min = duration_ms / 60000
    print(f"  命中缓存: {cache_file}")
    print(f"  音频时长: {duration_min:.1f} 分钟, 共 {len(sentences)} 句")
    return sentences


def _save_cache(file_path: str, sentences: list[dict], duration_ms: int = 0):
    """将转写结果保存为缓存"""
    os.makedirs(ASR_CACHE_DIR, exist_ok=True)
    cache_file = _cache_path(file_path)
    stat = os.stat(file_path)

    cache = {
        "video_path": os.path.abspath(file_path),
        "video_size": stat.st_size,
        "video_mtime": int(stat.st_mtime),
        "transcribe_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_ms": duration_ms,
        "sentences": sentences,
    }

    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    print(f"  转写结果已缓存: {cache_file}")


def _get_upload_policy(api_key: str, model_name: str) -> dict:
    """获取文件上传凭证"""
    url = "https://dashscope.aliyuncs.com/api/v1/uploads"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    params = {"action": "getPolicy", "model": model_name}
    resp = requests.get(url, headers=headers, params=params)
    if resp.status_code != 200:
        raise RuntimeError(f"获取上传凭证失败 [{resp.status_code}]: {resp.text}")
    return resp.json()["data"]


def _upload_file_to_oss(policy_data: dict, file_path: str) -> str:
    """将文件上传到 DashScope 临时 OSS，返回 oss:// URL"""
    file_name = Path(file_path).name
    key = f"{policy_data['upload_dir']}/{file_name}"

    with open(file_path, "rb") as f:
        files = {
            "OSSAccessKeyId": (None, policy_data["oss_access_key_id"]),
            "Signature": (None, policy_data["signature"]),
            "policy": (None, policy_data["policy"]),
            "x-oss-object-acl": (None, policy_data["x_oss_object_acl"]),
            "x-oss-forbid-overwrite": (None, policy_data["x_oss_forbid_overwrite"]),
            "key": (None, key),
            "success_action_status": (None, "200"),
            "file": (file_name, f),
        }
        resp = requests.post(policy_data["upload_host"], files=files)
        if resp.status_code != 200:
            raise RuntimeError(f"上传文件到 OSS 失败 [{resp.status_code}]: {resp.text[:500]}")

    oss_url = f"oss://{key}"
    print(f"  文件上传成功: {oss_url} (48小时内有效)")
    return oss_url


def transcribe(file_path: str) -> list[dict]:
    """对本地音视频文件进行语音转写，优先使用缓存。"""
    api_key = DASHSCOPE_API_KEY
    if not api_key:
        raise ValueError("请设置 DASHSCOPE_API_KEY 环境变量，或在 config.py 中填写")
    dashscope.api_key = api_key

    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")

    # 检查缓存
    print(f"[1/3] 检查缓存: {file_path}")
    cached = _load_cache(file_path)
    if cached is not None:
        return cached

    # 上传本地文件
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    print(f"  文件大小: {file_size_mb:.1f} MB")
    if file_size_mb > 2048:
        raise ValueError(f"文件超过 2GB 限制（当前 {file_size_mb:.1f} MB）")

    policy = _get_upload_policy(api_key, ASR_MODEL)
    file_url = _upload_file_to_oss(policy, file_path)

    # 提交转写任务（需加 OSS 解析头）
    print(f"[2/3] 提交转写任务 (模型: {ASR_MODEL})...")
    task_response = Transcription.async_call(
        model=ASR_MODEL,
        file_urls=[file_url],
        language_hints=ASR_LANGUAGE_HINTS,
        headers=OSS_HEADERS,
    )

    task_id = task_response.output.task_id
    task_status = task_response.output.task_status
    print(f"  任务ID: {task_id}, 状态: {task_status}")

    if task_status == "FAILED":
        raise RuntimeError(f"转写任务提交失败: {task_response.output.message}")

    # 等待转写完成（需加 OSS 解析头）
    print("[3/3] 等待转写完成...")
    transcription_response = Transcription.wait(
        task=task_id,
        headers=OSS_HEADERS,
    )

    if transcription_response.status_code != HTTPStatus.OK:
        raise RuntimeError(f"转写任务失败: {transcription_response.output.message}")

    # 解析结果
    sentences = []
    duration_ms = 0
    for transcription in transcription_response.output["results"]:
        if transcription["subtask_status"] != "SUCCEEDED":
            print(f"  警告: 子任务失败 - {transcription}")
            continue

        url = transcription["transcription_url"]
        result = json.loads(urllib_request.urlopen(url).read().decode("utf8"))

        props = result.get("properties", {})
        duration_ms = props.get("original_duration_in_milliseconds", 0)
        duration_min = duration_ms / 60000
        print(f"  音频时长: {duration_min:.1f} 分钟")

        for transcript in result.get("transcripts", []):
            for sent in transcript.get("sentences", []):
                sentences.append({
                    "text": sent["text"],
                    "begin_time": sent["begin_time"],
                    "end_time": sent["end_time"],
                })

    print(f"  转写完成，共 {len(sentences)} 句")

    # 保存缓存
    _save_cache(file_path, sentences, duration_ms)

    return sentences