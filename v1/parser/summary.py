# -*- coding: utf-8 -*-
"""
视频内容提炼总结模块
将 parser 解析后的 Markdown 文档提炼总结为商机内容

功能：
  - 读取已生成的 Markdown 文件
  - 按商机类别进行提炼总结
  - 保存到 output/summary 目录
"""

import os
import sys
import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from parser.config import DASHSCOPE_API_KEY, SUMMARY_DIR
from parser.llm_processor import _call_llm

# 提炼总结模型
SUMMARY_MODEL = "qwen-plus"


# ===================== 商机总结提示词 =====================

SUMMARY_PROMPT = """类别：描述
需求与痛点：普通人面临的问题、障碍、心理、认知等。
趋势与赛道：时代趋势、风口、技术变革（如短视频、AI）等。
资源与壁垒：认知门槛、信息壁垒、资本、风险规避、注意力等资源或障碍。
模式与盈利：如何赚钱、盈利方式、商业模式等。
风险与避坑：风险、骗局、安全、失败教训等。
实操与落地：具体行动建议、方法、步骤、技巧等。

请把文档内容按照以上类别进行一一对应，再分别总结后一一划分。如果没有对应的类型就不要强行划分。
最终输出一个Markdown格式。"""


# ===================== 核心函数 =====================

def summarize(content: str, source: str = "", author: str = "") -> str:
    """
    对文档内容进行商机提炼总结

    Args:
        content: 文档内容（Markdown 格式）
        source: 来源（如 Bilibili）
        author: 作者/UP主

    Returns:
        提炼总结后的 Markdown 内容
    """
    # 构造提示词
    prompt = f"""你是一个专业的商业分析师。请对以下内容进行提炼总结，按照商机分析的角度进行分类整理。

{SUMMARY_PROMPT}

以下是待分析的文档内容：

{content}"""

    print("  调用 LLM 进行商机提炼...")
    result = _call_llm(prompt)

    print("  提炼完成")
    return result


def summarize_file(
    input_path: str,
    output_dir: Optional[str] = None,
    metadata: Optional[dict] = None
) -> str:
    """
    对 Markdown 文件进行商机提炼总结

    Args:
        input_path: 输入文件路径（parser 生成的 .md 文件）
        output_dir: 输出目录（默认 output/summary）
        metadata: 元数据（source, author, date 等）

    Returns:
        生成的总结文件路径
    """
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"文件不存在: {input_path}")

    # 读取内容
    with open(input_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 提取标题（第一个 # 开头的行）
    title = input_path.stem
    for line in content.split("\n"):
        if line.strip().startswith("# "):
            title = line.strip()[2:].strip()
            break

    # 调用 LLM 提炼
    source = metadata.get("source", "") if metadata else ""
    author = metadata.get("author", "") if metadata else ""
    result = summarize(content, source=source, author=author)

    # 生成输出内容
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    src = metadata.get('source', '未知') if metadata else '未知'
    author_val = metadata.get('author', '未知') if metadata else '未知'
    date_val = metadata.get('date', now) if metadata else now
    output_content = f"""# {title} - 商机组

> 来源: {src} | 作者: {author_val} | 日期: {date_val}  
> 提炼时间: {now}  
> 原始文件: {input_path.name}

---

{result}
"""

    # 保存文件
    if output_dir:
        output_path = Path(output_dir)
    else:
        output_path = SUMMARY_DIR

    output_path.mkdir(parents=True, exist_ok=True)

    # 生成不冲突的文件名
    base_name = title[:50]  # 限制标题长度
    base_name = _sanitize_filename(base_name)
    output_file = output_path / f"{base_name}.md"

    # 如果文件名冲突，添加序号
    counter = 1
    while output_file.exists():
        output_file = output_path / f"{base_name}_{counter}.md"
        counter += 1

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(output_content)

    print(f"  总结已保存: {output_file}")
    return str(output_file)


def summarize_batch(
    input_dir: str,
    output_dir: Optional[str] = None,
    pattern: str = "*.md"
) -> list[str]:
    """
    批量处理目录中的 Markdown 文件

    Args:
        input_dir: 输入目录
        output_dir: 输出目录
        pattern: 文件匹配模式

    Returns:
        生成的总结文件路径列表
    """
    input_path = Path(input_dir)
    if not input_path.exists():
        raise FileNotFoundError(f"目录不存在: {input_path}")

    output_path = output_dir or str(SUMMARY_DIR)
    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)

    results = []
    md_files = list(input_path.glob(pattern))

    if not md_files:
        print(f"  未找到匹配的文件: {pattern}")
        return results

    print(f"  找到 {len(md_files)} 个文件待处理")

    for i, md_file in enumerate(md_files, 1):
        print(f"\n[{i}/{len(md_files)}] 处理: {md_file.name}")
        try:
            result_path = summarize_file(str(md_file), str(output_path))
            results.append(result_path)
        except Exception as e:
            print(f"  处理失败: {e}")

    return results


# ===================== 工具函数 =====================

def _sanitize_filename(name: str) -> str:
    """
    清理文件名中的非法字符
    """
    illegal_chars = '<>:"/\\|?*'
    for char in illegal_chars:
        name = name.replace(char, "_")
    # 移除首尾空格和点
    name = name.strip().strip(".")
    # 限制长度
    if len(name) > 80:
        name = name[:80]
    return name or "untitled"


def _generate_unique_filename(base_name: str, output_dir: Path) -> Path:
    """
    生成唯一的文件名
    """
    # 使用内容 hash 作为后缀确保唯一性
    content_hash = hashlib.md5(base_name.encode()).hexdigest()[:6]
    filename = f"{base_name}_{content_hash}.md"
    return output_dir / filename


# ===================== 主入口 =====================

def main():
    """
    命令行入口

    用法：
        python -m parser.summary <输入文件或目录> [--output <输出目录>]
        python -m parser.summary "output/video/AI教程.md"
        python -m parser.summary "output/" --pattern "*.md"
    """
    import argparse

    parser = argparse.ArgumentParser(description="视频内容商机提炼工具")
    parser.add_argument("input", help="输入文件或目录路径")
    parser.add_argument("--output", "-o", help="输出目录（默认 output/summary）")
    parser.add_argument("--pattern", "-p", default="*.md", help="文件匹配模式（批量时使用）")
    parser.add_argument("--source", help="来源")
    parser.add_argument("--author", help="作者/UP主")
    parser.add_argument("--date", help="日期")

    args = parser.parse_args()

    metadata = {
        "source": args.source or "",
        "author": args.author or "",
        "date": args.date or "",
    }

    input_path = Path(args.input)
    output_dir = args.output

    if not input_path.exists():
        print(f"错误: 文件或目录不存在 - {input_path}")
        sys.exit(1)

    if input_path.is_file():
        # 单文件处理
        print(f"提炼总结: {input_path.name}")
        result = summarize_file(str(input_path), output_dir, metadata)
        print(f"\n完成! 总结已保存到: {result}")

    elif input_path.is_dir():
        # 批量处理
        print(f"批量处理目录: {input_path}")
        results = summarize_batch(str(input_path), output_dir, args.pattern)
        print(f"\n完成! 共处理 {len(results)} 个文件")
        for r in results:
            print(f"  - {r}")


if __name__ == "__main__":
    main()
