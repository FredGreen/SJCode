# -*- coding: utf-8 -*-
"""
V2 视频解析模块
功能：
  - 使用 Whisper 进行语音识别（ASR）
  - 使用 DeepSeek 进行文本清洗和结构化
  - 生成 Markdown 文档
  - 支持缓存机制
"""

__version__ = "2.0.0"

import os
import sys
import json
import hashlib
import subprocess
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

# DeepSeek 配置
DEEPSEEK_API_KEY = "sk-e25608a81abf4f25a2037489d3bd92af"
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-chat"

# Whisper 配置
WHISPER_MODEL = "medium"
WHISPER_LANGUAGE = "zh"

# 输出目录
DEFAULT_DOCS_DIR = PROJECT_ROOT / "output" / "v2_docs"
DEFAULT_ASR_CACHE_DIR = PROJECT_ROOT / "output" / "v2_asr_cache"


# ===================== Whisper ASR =====================

def _asr_cache_path(file_path: str, cache_dir: Path = None) -> str:
    """生成ASR缓存路径"""
    if cache_dir is None:
        cache_dir = DEFAULT_ASR_CACHE_DIR
    file_hash = hashlib.md5(os.path.abspath(file_path).encode('utf-8')).hexdigest()[:16]
    return str(cache_dir / f"{file_hash}.whisper.json")


def _load_asr_cache(file_path: str, cache_dir: Path = None) -> Optional[list]:
    """加载ASR缓存"""
    cache_file = _asr_cache_path(file_path, cache_dir)
    if not os.path.isfile(cache_file):
        return None
    
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            cache = json.load(f)
    except:
        return None
    
    # 验证文件是否变化
    stat = os.stat(file_path)
    if cache.get("video_size") != stat.st_size:
        return None
    
    return cache.get("sentences", [])


def _save_asr_cache(file_path: str, sentences: list, cache_dir: Path = None):
    """保存ASR缓存"""
    if cache_dir is None:
        cache_dir = DEFAULT_ASR_CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = _asr_cache_path(file_path, cache_dir)
    stat = os.stat(file_path)
    
    cache = {
        "video_path": os.path.abspath(file_path),
        "video_size": stat.st_size,
        "transcribe_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sentences": sentences,
    }
    
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def transcribe_with_whisper(
    video_path: str, 
    model: str = None,
    cache_dir: Path = None,
    progress_callback=None
) -> List[Dict]:
    """
    使用Whisper进行语音识别
    
    Args:
        video_path: 视频文件路径
        model: Whisper模型名称
        cache_dir: 缓存目录
        progress_callback: 进度回调函数
    
    Returns:
        句子列表 [{"text": "...", "start": 0.0, "end": 1.0}, ...]
    """
    if model is None:
        model = WHISPER_MODEL
    if cache_dir is None:
        cache_dir = DEFAULT_ASR_CACHE_DIR
    
    # 检查缓存
    cached = _load_asr_cache(video_path, cache_dir)
    if cached:
        if progress_callback:
            progress_callback(f"ASR 命中缓存，共 {len(cached)} 句")
        return cached
    
    if progress_callback:
        progress_callback(f"开始转写: {Path(video_path).name}")
        progress_callback(f"模型: {model}")
    
    # 提取音频
    audio_path = video_path + ".audio.wav"
    if progress_callback:
        progress_callback("提取音频...")
    
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le",
        "-ar", "16000", "-ac", "1",
        "-y", audio_path
    ]
    
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='ignore'
    )
    
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg 提取音频失败: {result.stderr}")
    
    try:
        import whisper
        
        if progress_callback:
            progress_callback("加载模型...")
        model_obj = whisper.load_model(model)
        
        if progress_callback:
            progress_callback("开始识别...")
        result = model_obj.transcribe(
            audio_path,
            language=WHISPER_LANGUAGE,
            verbose=False
        )
        
        sentences = []
        for seg in result.get("segments", []):
            sentences.append({
                "text": seg["text"].strip(),
                "start": seg.get("start", 0.0),
                "end": seg.get("end", 0.0),
            })
        
        if progress_callback:
            progress_callback(f"转写完成: 共 {len(sentences)} 句")
        
        # 保存缓存
        _save_asr_cache(video_path, sentences, cache_dir)
        
        return sentences
        
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)


# ===================== DeepSeek LLM =====================

def _call_deepseek(prompt: str, progress_callback=None) -> str:
    """调用DeepSeek API"""
    import requests
    
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 4096,
    }
    
    if progress_callback:
        progress_callback(f"调用 {DEEPSEEK_MODEL}...")
    
    response = requests.post(
        f"{DEEPSEEK_BASE_URL}/chat/completions",
        headers=headers,
        json=payload,
        timeout=120
    )
    
    if response.status_code != 200:
        raise RuntimeError(f"DeepSeek API 失败: {response.status_code}")
    
    return response.json()["choices"][0]["message"]["content"].strip()


def _extract_json(content: str) -> dict:
    """提取JSON"""
    if content.startswith("```"):
        lines = content.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        content = "\n".join(lines)
    return json.loads(content)


def clean_with_deepseek(
    sentences: List[Dict], 
    progress_callback=None
) -> List[Dict]:
    """
    使用DeepSeek清洗文本
    
    Args:
        sentences: 句子列表
        progress_callback: 进度回调函数
    
    Returns:
        清洗后的句子列表
    """
    numbered = [f"[{i}] {s['text']}" for i, s in enumerate(sentences)]
    full_text = "\n".join(numbered)
    
    prompt = f"""请对以下视频转写文本进行清洗：
1. 润色语句，使其更通顺
2. 去除无关内容（求关注、广告、口头禅等）
3. 保留所有有效内容

输出JSON格式：{{"cleaned": ["句子1", "句子2", ...]}}

转写文本：
{full_text}"""
    
    content = _call_deepseek(prompt, progress_callback)
    result = _extract_json(content)
    
    cleaned = [{"text": t} for t in result.get("cleaned", [])]
    if progress_callback:
        progress_callback(f"清洗完成: {len(sentences)} → {len(cleaned)} 句")
    return cleaned


def structure_with_deepseek(
    sentences: List[Dict], 
    title: str = "",
    progress_callback=None
) -> Dict:
    """
    使用DeepSeek结构化文本
    
    Args:
        sentences: 句子列表
        title: 视频标题
        progress_callback: 进度回调函数
    
    Returns:
        结构化结果 {"topic": "...", "summary": "...", "sections": [...]}
    """
    full_text = "\n".join([s['text'] for s in sentences])
    
    prompt = f"""请将以下视频内容整理成结构化的Markdown文档：

要求：
1. 提取主题（topic）
2. 生成摘要（summary，100字以内）
3. 按内容逻辑分段（sections），每段包含标题和内容

输出JSON格式：
{{
  "topic": "主题",
  "summary": "摘要",
  "sections": [
    {{"title": "段落标题", "content": "段落内容"}},
    ...
  ]
}}

视频标题：{title}

视频内容：
{full_text}"""
    
    content = _call_deepseek(prompt, progress_callback)
    result = _extract_json(content)
    
    if progress_callback:
        progress_callback(f"主题: {result.get('topic', '未知')}")
        progress_callback(f"分段数: {len(result.get('sections', []))}")
    
    return result


# ===================== Markdown 生成 =====================

def generate_markdown(
    structure: Dict, 
    title: str = "",
    output_dir: Path = None,
    progress_callback=None
) -> str:
    """
    生成Markdown文档
    
    Args:
        structure: 结构化结果
        title: 视频标题
        output_dir: 输出目录
        progress_callback: 进度回调函数
    
    Returns:
        Markdown文件路径
    """
    if output_dir is None:
        output_dir = DEFAULT_DOCS_DIR
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 生成文件名
    safe_title = title[:50].replace("/", "_").replace("\\", "_") if title else "untitled"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{safe_title}_{timestamp}.md"
    filepath = output_dir / filename
    
    # 生成Markdown内容
    lines = []
    lines.append(f"# {structure.get('topic', title or '未命名')}")
    lines.append("")
    
    # 元信息
    lines.append(f"> 原标题：{title}")
    lines.append(f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    
    # 摘要
    summary = structure.get("summary", "")
    if summary:
        lines.append("## 摘要")
        lines.append("")
        lines.append(summary)
        lines.append("")
    
    # 正文
    sections = structure.get("sections", [])
    if sections:
        lines.append("## 正文")
        lines.append("")
        
        for section in sections:
            section_title = section.get("title", "")
            section_content = section.get("content", "")
            
            if section_title:
                lines.append(f"### {section_title}")
                lines.append("")
            
            if section_content:
                lines.append(section_content)
                lines.append("")
    
    # 写入文件
    content = "\n".join(lines)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    
    if progress_callback:
        progress_callback(f"Markdown已保存: {filepath}")
    
    return str(filepath)


# ===================== 完整流程 =====================

def process_video(
    video_path: str,
    title: str = "",
    whisper_model: str = None,
    output_dir: Path = None,
    cache_dir: Path = None,
    progress_callback=None
) -> Dict:
    """
    完整处理流程：视频 → ASR → LLM → Markdown
    
    Args:
        video_path: 视频文件路径
        title: 视频标题
        whisper_model: Whisper模型
        output_dir: 输出目录
        cache_dir: 缓存目录
        progress_callback: 进度回调函数
    
    Returns:
        处理结果 {"status": "success/failed", "markdown_path": "...", ...}
    """
    try:
        # 1. ASR转写
        if progress_callback:
            progress_callback("\n[1/3] 语音识别...")
        sentences = transcribe_with_whisper(video_path, whisper_model, cache_dir, progress_callback)
        
        if not sentences:
            return {"status": "failed", "message": "ASR转写结果为空"}
        
        # 2. LLM清洗
        if progress_callback:
            progress_callback("\n[2/3] 文本清洗...")
        cleaned = clean_with_deepseek(sentences, progress_callback)
        
        # 3. LLM结构化
        if progress_callback:
            progress_callback("\n[3/3] 结构化处理...")
        structure = structure_with_deepseek(cleaned, title, progress_callback)
        
        # 4. 生成Markdown
        if progress_callback:
            progress_callback("\n生成Markdown...")
        markdown_path = generate_markdown(structure, title, output_dir, progress_callback)
        
        return {
            "status": "success",
            "markdown_path": markdown_path,
            "topic": structure.get("topic", ""),
            "summary": structure.get("summary", ""),
            "sentence_count": len(sentences),
            "cleaned_count": len(cleaned),
        }
        
    except Exception as e:
        if progress_callback:
            progress_callback(f"处理失败: {e}")
        return {"status": "failed", "message": str(e)}


# ===================== 状态查询 =====================

def is_video_transcribed(video_path: str, cache_dir: Path = None) -> bool:
    """检查视频是否已转写"""
    cache_file = _asr_cache_path(video_path, cache_dir)
    return os.path.isfile(cache_file)


def get_transcription_status(video_path: str, cache_dir: Path = None) -> Dict:
    """获取视频转写状态"""
    cache_file = _asr_cache_path(video_path, cache_dir)
    
    if not os.path.isfile(cache_file):
        return {"transcribed": False, "sentence_count": 0}
    
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            cache = json.load(f)
        return {
            "transcribed": True,
            "sentence_count": len(cache.get("sentences", [])),
            "transcribe_time": cache.get("transcribe_time", ""),
        }
    except:
        return {"transcribed": False, "sentence_count": 0}


# ===================== 命令行入口 =====================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="V2 视频解析模块")
    parser.add_argument("--video", "-v", required=True, help="视频文件路径")
    parser.add_argument("--title", "-t", default="", help="视频标题")
    parser.add_argument("--model", "-m", default="medium", help="Whisper模型")
    parser.add_argument("--output", "-o", help="输出目录")
    
    args = parser.parse_args()
    
    video_path = args.video
    if not os.path.exists(video_path):
        print(f"错误: 视频文件不存在: {video_path}")
        sys.exit(1)
    
    output_dir = Path(args.output) if args.output else None
    
    result = process_video(
        video_path,
        args.title,
        args.model,
        output_dir,
        progress_callback=lambda msg: print(msg)
    )
    
    if result["status"] == "success":
        print(f"\n处理完成!")
        print(f"Markdown: {result['markdown_path']}")
    else:
        print(f"\n处理失败: {result['message']}")
