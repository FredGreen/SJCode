# -*- coding: utf-8 -*-
"""
bilibili_search_down_deepseek: 使用 DeepSeek 完成视频转文字

功能：
  - 使用 Whisper 进行语音识别（ASR）
  - 使用 DeepSeek 进行文本清洗和结构化
  - 生成 Markdown 文档

与原版区别：
  - 原版：阿里云 ASR (paraformer-v2) + 阿里云 LLM (qwen-plus)
  - 本版：OpenAI Whisper (本地) + DeepSeek API

依赖：
  pip install openai-whisper openai requests

环境变量：
  DEEPSEEK_API_KEY: DeepSeek API 密钥

用法：
  python bilibili_search_down_deepseek.py --video 视频.mp4
  python bilibili_search_down_deepseek.py --video 视频.mp4 --model deepseek-chat
"""

__version__ = "1.0.0"

import os
import sys
import json
import time
import hashlib
import subprocess
from pathlib import Path
from typing import Optional

# 添加项目路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ===================== 配置 =====================

# DeepSeek 配置
DEEPSEEK_API_KEY = "sk-d2e27860aa3243668a95a85e2bf8edcb"
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-chat"  # 可选: deepseek-chat, deepseek-reasoner

# Whisper 配置
WHISPER_MODEL = "medium"  # 可选: tiny, base, small, medium, large
WHISPER_LANGUAGE = "zh"

# 输出目录
OUTPUT_DIR = PROJECT_ROOT / "output" / "deepseek_docs"
ASR_CACHE_DIR = PROJECT_ROOT / "output" / "deepseek_asr_cache"


# ===================== Whisper ASR =====================

def _cache_path(file_path: str) -> str:
    """根据视频文件路径生成缓存文件路径"""
    file_hash = hashlib.md5(os.path.abspath(file_path).encode('utf-8')).hexdigest()[:16]
    return os.path.join(ASR_CACHE_DIR, f"{file_hash}.whisper.json")


def _load_cache(file_path: str) -> Optional[list]:
    """检查并加载缓存"""
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
    print(f"  命中缓存: {cache_file}")
    print(f"  共 {len(sentences)} 句")
    return sentences


def _save_cache(file_path: str, sentences: list):
    """保存转写结果到缓存"""
    os.makedirs(ASR_CACHE_DIR, exist_ok=True)
    cache_file = _cache_path(file_path)
    stat = os.stat(file_path)

    cache = {
        "video_path": os.path.abspath(file_path),
        "video_size": stat.st_size,
        "video_mtime": int(stat.st_mtime),
        "transcribe_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "sentences": sentences,
    }

    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def transcribe_with_whisper(video_path: str, use_cache: bool = True) -> list[dict]:
    """
    使用 Whisper 进行语音识别
    
    Args:
        video_path: 视频文件路径
        use_cache: 是否使用缓存
    
    Returns:
        句子列表 [{"text": "...", "start": 0.0, "end": 1.0}, ...]
    """
    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"视频文件不存在: {video_path}")

    # 检查缓存
    if use_cache:
        cached = _load_cache(video_path)
        if cached is not None:
            return cached

    print(f"  [Whisper] 开始转写: {Path(video_path).name}")
    print(f"  [Whisper] 模型: {WHISPER_MODEL}, 语言: {WHISPER_LANGUAGE}")

    # 使用 ffmpeg 提取音频
    audio_path = video_path + ".audio.wav"
    print(f"  [Whisper] 提取音频...")
    
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vn",  # 不要视频
        "-acodec", "pcm_s16le",  # PCM 16bit
        "-ar", "16000",  # 16kHz
        "-ac", "1",  # 单声道
        "-y",  # 覆盖
        audio_path
    ]
    
    # Windows 下需要处理编码问题
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
        # 导入 whisper
        try:
            import whisper
        except ImportError:
            raise ImportError(
                "未安装 whisper 模块，请运行: pip install openai-whisper\n"
                "或者使用其他 ASR 方案（如阿里云 ASR）"
            )
        
        print(f"  [Whisper] 加载模型 {WHISPER_MODEL}...")
        model = whisper.load_model(WHISPER_MODEL)
        
        print(f"  [Whisper] 开始识别...")
        result = model.transcribe(
            audio_path,
            language=WHISPER_LANGUAGE,
            verbose=False
        )
        
        # 转换为句子列表
        sentences = []
        for seg in result.get("segments", []):
            sentences.append({
                "text": seg["text"].strip(),
                "start": seg.get("start", 0.0),
                "end": seg.get("end", 0.0),
            })
        
        print(f"  [Whisper] 转写完成: 共 {len(sentences)} 句")
        
        # 保存缓存
        _save_cache(video_path, sentences)
        
        return sentences
        
    finally:
        # 清理临时音频文件
        if os.path.exists(audio_path):
            os.remove(audio_path)


# ===================== DeepSeek LLM =====================

def _call_deepseek(prompt: str, system_prompt: str = None) -> str:
    """调用 DeepSeek API"""
    api_key = DEEPSEEK_API_KEY
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY 未配置")
    
    import requests
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 4096,
    }
    
    print(f"  [DeepSeek] 调用 {DEEPSEEK_MODEL}...")
    
    response = requests.post(
        f"{DEEPSEEK_BASE_URL}/chat/completions",
        headers=headers,
        json=payload,
        timeout=120
    )
    
    if response.status_code != 200:
        raise RuntimeError(f"DeepSeek API 调用失败: {response.status_code} - {response.text}")
    
    data = response.json()
    content = data["choices"][0]["message"]["content"].strip()
    
    return content


def _extract_json(content: str) -> dict:
    """从 LLM 返回中提取 JSON"""
    if content.startswith("```"):
        lines = content.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        content = "\n".join(lines)
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"JSON 解析失败: {e}\n原始内容: {content[:500]}")


def clean_with_deepseek(sentences: list[dict]) -> list[dict]:
    """
    使用 DeepSeek 清洗文本
    """
    numbered_lines = []
    for i, sent in enumerate(sentences):
        numbered_lines.append(f"[{i}] {sent['text']}")
    full_text = "\n".join(numbered_lines)

    prompt = f"""你是一个专业的文本编辑。请对以下视频转写文本进行清洗，要求：

1. **润色语句**：将口语化、不通顺的句子改为更通顺、更规范的书面表达，但不要改变原意
2. **去除无关内容**：删除与视频主题无关的内容，包括但不限于：
   - 求关注、求点赞、求一键三连等互动引导
   - 推广广告、赞助信息
   - 无意义的口头禅、重复废话
   - 开场/结尾的纯寒暄（与主题无关的部分）
3. **保留有效内容**：与主题相关的所有实质内容都要保留，不要概括或缩减

请严格按以下 JSON 格式输出，不要输出任何其他内容：
{{
  "cleaned": [
    "清洗润色后的第1句",
    "清洗润色后的第2句",
    "清洗润色后的第3句"
  ]
}}

注意：cleaned 数组中只包含保留并润色后的句子，按原文顺序排列。被删除的句子不要出现在数组中。

以下是视频转写文本：

{full_text}"""

    content = _call_deepseek(prompt)
    result = _extract_json(content)

    if "cleaned" not in result:
        raise RuntimeError(f"清洗结果缺少 cleaned 字段: {list(result.keys())}")

    cleaned_texts = result["cleaned"]
    cleaned_sentences = [{"text": text} for text in cleaned_texts]

    removed = len(sentences) - len(cleaned_sentences)
    print(f"  [DeepSeek] 清洗完成: 原文 {len(sentences)} 句 → 保留 {len(cleaned_sentences)} 句, 去除 {removed} 句")

    return cleaned_sentences


def structure_with_deepseek(sentences: list[dict]) -> dict:
    """
    使用 DeepSeek 对文本进行结构化处理
    """
    numbered_lines = []
    for i, sent in enumerate(sentences):
        numbered_lines.append(f"[{i}] {sent['text']}")
    full_text = "\n".join(numbered_lines)

    prompt = f"""你是一个专业的内容分析师。请对以下视频转写文本进行分析，输出该视频的主题、概要，并按内容语义将文本分段。

要求：
1. **主题**：用一句话概括视频的核心主题，不要用"探讨""分析"等空洞词，直接说清楚这个视频讲了什么
2. **概要**：2-3句话概括视频主要内容，突出关键信息点
3. **分段**：根据内容的语义逻辑进行分段，每段给出一个简洁明确的标题。分段要自然，不要分得太碎（每段至少3句话），也不要太长（每段不超过20句）。标题不要加序号

请严格按以下 JSON 格式输出，不要输出任何其他内容：
{{
  "topic": "视频主题",
  "summary": "视频概要",
  "segments": [
    {{"title": "段落标题", "start": 0, "end": 5}},
    {{"title": "段落标题", "start": 6, "end": 12}}
  ]
}}

其中 start 和 end 是句子编号，包含两端。段落之间不要有间隔，前一段的 end+1 应等于下一段的 start。第一个段落 start=0，最后一个段落的 end 应等于最后一个句子编号。

以下是视频转写文本：

{full_text}"""

    content = _call_deepseek(prompt)
    result = _extract_json(content)

    if "topic" not in result or "summary" not in result or "segments" not in result:
        raise RuntimeError(f"返回结果缺少必要字段: {list(result.keys())}")

    last_index = len(sentences) - 1
    for seg in result["segments"]:
        if seg["end"] > last_index:
            seg["end"] = last_index
        if seg["start"] > last_index:
            seg["start"] = last_index

    print(f"  [DeepSeek] 主题: {result['topic']}")
    print(f"  [DeepSeek] 分段数: {len(result['segments'])}")

    return result


# ===================== Markdown 生成 =====================

def generate_markdown(sentences: list[dict], structure: dict, video_name: str) -> str:
    """生成 Markdown 文档"""
    lines = []
    lines.append(f"# {structure['topic']}")
    lines.append("")
    lines.append(f"> **视频**: {video_name}")
    lines.append(f"> **生成时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"> **AI模型**: DeepSeek + Whisper")
    lines.append("")
    lines.append("## 概要")
    lines.append("")
    lines.append(structure["summary"])
    lines.append("")

    for seg in structure["segments"]:
        title = seg["title"]
        start_idx = seg["start"]
        end_idx = seg["end"]

        lines.append(f"## {title}")
        lines.append("")

        for i in range(start_idx, end_idx + 1):
            if i < len(sentences):
                lines.append(sentences[i]["text"])
                lines.append("")

    return "\n".join(lines)


# ===================== 主流程 =====================

def process_video(video_path: str, output_dir: str = None) -> str:
    """
    处理单个视频：ASR → 清洗 → 结构化 → 生成 Markdown
    
    Args:
        video_path: 视频文件路径
        output_dir: 输出目录，默认为 OUTPUT_DIR
    
    Returns:
        生成的 Markdown 文件路径
    """
    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"视频文件不存在: {video_path}")

    video_name = Path(video_path).stem
    output_dir = output_dir or str(OUTPUT_DIR)
    os.makedirs(output_dir, exist_ok=True)

    print(f"\n{'='*50}")
    print(f"处理视频: {Path(video_path).name}")
    print(f"{'='*50}")

    # 1. ASR 转写
    print("\n[1/4] 语音识别 (Whisper)...")
    sentences = transcribe_with_whisper(video_path)
    
    if not sentences:
        raise RuntimeError("ASR 转写结果为空")

    # 2. 文本清洗
    print("\n[2/4] 文本清洗 (DeepSeek)...")
    cleaned_sentences = clean_with_deepseek(sentences)

    # 3. 结构化处理
    print("\n[3/4] 结构化处理 (DeepSeek)...")
    structure = structure_with_deepseek(cleaned_sentences)

    # 4. 生成 Markdown
    print("\n[4/4] 生成 Markdown...")
    markdown = generate_markdown(cleaned_sentences, structure, video_name)

    # 保存文件
    output_path = os.path.join(output_dir, f"{video_name}.md")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(markdown)

    print(f"\n{'='*50}")
    print(f"完成！输出文件: {output_path}")
    print(f"{'='*50}")

    return output_path


# ===================== 命令行入口 =====================

def main():
    import argparse

    global DEEPSEEK_MODEL, WHISPER_MODEL
    
    parser = argparse.ArgumentParser(description="使用 DeepSeek + Whisper 进行视频转文字")
    parser.add_argument("--video", "-v", required=True, help="视频文件路径")
    parser.add_argument("--output", "-o", default=None, help="输出目录")
    parser.add_argument("--model", "-m", default=DEEPSEEK_MODEL, help=f"DeepSeek 模型 (默认: {DEEPSEEK_MODEL})")
    parser.add_argument("--whisper-model", default=WHISPER_MODEL, help=f"Whisper 模型 (默认: {WHISPER_MODEL})")
    args = parser.parse_args()

    DEEPSEEK_MODEL = args.model
    WHISPER_MODEL = args.whisper_model

    try:
        output_path = process_video(args.video, args.output)
        print(f"\n结果已保存到: {output_path}")
    except Exception as e:
        print(f"\n[错误] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
