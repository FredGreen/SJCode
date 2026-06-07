# -*- coding: utf-8 -*-
"""
视频转 Markdown 工具 - LLM 处理器
使用阿里云百炼千问模型：
  1. 文本清洗（润色语句、去无关内容）
  2. 结构化处理（生成主题、概要、分段）
"""

import json
import dashscope
from dashscope import Generation

from parser.config import DASHSCOPE_API_KEY, LLM_MODEL


def _call_llm(prompt: str) -> str:
    """调用 LLM 并返回原始文本内容"""
    api_key = DASHSCOPE_API_KEY
    if not api_key:
        raise ValueError("请设置 DASHSCOPE_API_KEY 环境变量")
    dashscope.api_key = api_key

    response = Generation.call(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        result_format="message",
    )

    if response.status_code != 200:
        raise RuntimeError(f"LLM 调用失败: {response.message}")

    return response.output.choices[0].message.content.strip()


def _extract_json(content: str) -> dict | list:
    """从 LLM 返回中提取 JSON，处理 markdown 代码块包裹"""
    if content.startswith("```"):
        lines = content.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        content = "\n".join(lines)
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"LLM 返回的 JSON 解析失败: {e}\n原始内容: {content[:500]}")


def clean(sentences: list[dict]) -> list[dict]:
    """
    文本清洗：润色语句、去除与主题无关的内容（如求关注、一键三连、广告等）。

    Args:
        sentences: ASR 原始句子列表

    Returns:
        清洗后的句子列表（格式不变，可能比原列表短）
    """
    # 构造带编号的文本
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

    print("  调用 LLM 清洗文本...")
    content = _call_llm(prompt)
    result = _extract_json(content)

    if "cleaned" not in result:
        raise RuntimeError(f"LLM 清洗结果缺少 cleaned 字段: {list(result.keys())}")

    cleaned_texts = result["cleaned"]
    cleaned_sentences = [{"text": text} for text in cleaned_texts]

    removed = len(sentences) - len(cleaned_sentences)
    print(f"  清洗完成: 原文 {len(sentences)} 句 → 保留 {len(cleaned_sentences)} 句, 去除 {removed} 句")

    return cleaned_sentences


def structure(sentences: list[dict]) -> dict:
    """
    调用 LLM 对清洗后的文本进行结构化处理。

    Args:
        sentences: 清洗后的句子列表

    Returns:
        {
            "topic": "视频主题",
            "summary": "视频概要",
            "segments": [
                {"title": "段落标题", "start": 0, "end": 5},
                ...
            ]
        }
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

    print("  调用 LLM 生成结构化内容...")
    content = _call_llm(prompt)
    result = _extract_json(content)

    if "topic" not in result or "summary" not in result or "segments" not in result:
        raise RuntimeError(f"LLM 返回结果缺少必要字段: {list(result.keys())}")

    last_index = len(sentences) - 1
    for seg in result["segments"]:
        if seg["end"] > last_index:
            seg["end"] = last_index
        if seg["start"] > last_index:
            seg["start"] = last_index

    print(f"  主题: {result['topic']}")
    print(f"  分段数: {len(result['segments'])}")

    return result