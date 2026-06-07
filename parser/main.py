# -*- coding: utf-8 -*-
"""
视频转 Markdown 工具 - 主入口

用法：
    python main.py <视频文件路径> [--source 来源] [--author 作者] [--date 日期]

示例：
    python main.py "D:/videos/短视频选题逻辑.mp4"
    python main.py "D:/videos/test.mp4" --source Bilibili --author 张三 --date 2026-05-24
"""

import argparse
import os
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中，解决 IDE 和命令行运行时的导入问题
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from parser.config import DOCS_DIR
from parser.asr_client import transcribe
from parser.llm_processor import clean, structure
from parser.md_generator import generate as md_generate


def main():
    parser = argparse.ArgumentParser(description="视频转 Markdown 工具（基于阿里云百炼 paraformer-v2）")
    parser.add_argument("video", help="视频文件路径（支持 mp4/mp3/wav/mkv/mov 等格式）")
    parser.add_argument("--source", default="", help="视频来源（如 Bilibili）")
    parser.add_argument("--author", default="", help="视频作者/UP主")
    parser.add_argument("--date", default="", help="视频日期（如 2026-05-24）")
    args = parser.parse_args()

    video_path = args.video
    if not os.path.isfile(video_path):
        print(f"错误: 文件不存在 - {video_path}")
        sys.exit(1)

    metadata = {
        "source": args.source,
        "author": args.author,
        "date": args.date,
    }

    print("=" * 60)
    print(f"视频转 Markdown 工具")
    print(f"文件: {video_path}")
    print("=" * 60)

    # Step 1: ASR 语音识别
    print("\n--- Step 1: 语音识别 ---")
    sentences = transcribe(video_path)

    if not sentences:
        print("错误: 未识别到任何语音内容")
        sys.exit(1)

    # Step 2: LLM 文本清洗
    print("\n--- Step 2: LLM 文本清洗 ---")
    cleaned_sentences = clean(sentences)

    if not cleaned_sentences:
        print("错误: 清洗后无有效内容")
        sys.exit(1)

    # Step 3: LLM 结构化处理
    print("\n--- Step 3: LLM 结构化处理 ---")
    struct = structure(cleaned_sentences)

    # Step 4: 生成 Markdown
    print("\n--- Step 4: 生成 Markdown ---")
    md_content = md_generate(cleaned_sentences, struct, metadata)

    os.makedirs(DOCS_DIR, exist_ok=True)
    video_name = Path(video_path).stem
    output_path = os.path.join(DOCS_DIR, f"{video_name}.md")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    print(f"\n✅ 完成! Markdown 已保存到: {output_path}")
    print(f"   主题: {struct.get('topic', 'N/A')}")
    print(f"   段落数: {len(struct.get('segments', []))}")
    print(f"   原始句数: {len(sentences)} → 清洗后: {len(cleaned_sentences)}")


if __name__ == "__main__":
    main()