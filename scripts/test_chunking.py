#!/usr/bin/env python3
"""
测试分块逻辑
"""

import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent / "ai-services"))

from rag.ingestion.chunkers import heading_aware_chunk


def main():
    # 读取内科学完整版
    md_file = Path("e:/xiangmu/dachuang/ai-services/memory/knowledge/docs/《内科学 第10版(1)带书签》完整版.md")

    if not md_file.exists():
        print(f"文件不存在: {md_file}")
        return

    with open(md_file, 'r', encoding='utf-8') as f:
        text = f.read()

    print(f"文件大小: {len(text)} 字符")
    print(f"文件行数: {text.count(chr(10))} 行")

    # 分块
    chunks = heading_aware_chunk(
        text=text,
        chunk_size=1000,
        chunk_overlap=100,
    )

    print(f"\n分块结果: {len(chunks)} 个块")

    # 显示前10个块
    print("\n前10个块:")
    for i, chunk in enumerate(chunks[:10]):
        print(f"\n{'='*60}")
        print(f"[块 {i}] heading: {chunk['heading']}")
        print(f"[块 {i}] 长度: {len(chunk['text'])} 字符")
        print(f"[块 {i}] 内容预览:")
        print(chunk['text'][:200] + "..." if len(chunk['text']) > 200 else chunk['text'])

    # 统计信息
    print(f"\n{'='*60}")
    print("统计信息:")
    print(f"总块数: {len(chunks)}")
    print(f"平均块大小: {sum(len(c['text']) for c in chunks) / len(chunks):.0f} 字符")
    print(f"最大块大小: {max(len(c['text']) for c in chunks)} 字符")
    print(f"最小块大小: {min(len(c['text']) for c in chunks)} 字符")


if __name__ == '__main__':
    main()
