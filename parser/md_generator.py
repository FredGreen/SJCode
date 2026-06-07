# -*- coding: utf-8 -*-
"""
视频转 Markdown 工具 - Markdown 生成器
将 ASR 结果 + LLM 结构化输出组装为面向 RAG 的 Markdown 文档
"""


def generate(
    sentences: list[dict],
    structure: dict,
    metadata: dict | None = None,
) -> str:
    """生成 Markdown 文档。"""
    lines = []

    topic = structure.get("topic", "未命名视频")
    lines.append(f"# {topic}")
    lines.append("")

    if metadata:
        meta_parts = []
        if metadata.get("source"):
            meta_parts.append(f"来源：{metadata['source']}")
        if metadata.get("author"):
            meta_parts.append(f"UP主：{metadata['author']}")
        if metadata.get("duration"):
            meta_parts.append(f"时长：{metadata['duration']}")
        if metadata.get("date"):
            meta_parts.append(f"日期：{metadata['date']}")
        if meta_parts:
            lines.append("> " + " | ".join(meta_parts))
            lines.append("")

    summary = structure.get("summary", "")
    if summary:
        lines.append(summary)
        lines.append("")

    segments = structure.get("segments", [])
    for i, seg in enumerate(segments):
        title = seg.get("title", f"第{i+1}段")
        start = seg.get("start", 0)
        end = seg.get("end", len(sentences) - 1)

        lines.append(f"### {title}")
        lines.append("")

        for j in range(start, min(end + 1, len(sentences))):
            lines.append(sentences[j]["text"])

        lines.append("")

        if i < len(segments) - 1:
            lines.append("---")
            lines.append("")

    return "\n".join(lines)