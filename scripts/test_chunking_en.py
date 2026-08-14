#!/usr/bin/env python3
"""
Test chunking logic
"""

import sys
from pathlib import Path

# Add project path
sys.path.insert(0, str(Path(__file__).parent.parent / "ai-services"))

from rag.ingestion.chunkers import heading_aware_chunk


def main():
    # Read the complete internal medicine file
    md_file = Path("e:/xiangmu/dachuang/ai-services/memory/knowledge/docs/《内科学 第10版(1)带书签》完整版.md")

    if not md_file.exists():
        print(f"File not found: {md_file}")
        return

    with open(md_file, 'r', encoding='utf-8') as f:
        text = f.read()

    print(f"File size: {len(text)} characters")
    print(f"File lines: {text.count(chr(10))} lines")

    # Chunking
    chunks = heading_aware_chunk(
        text=text,
        chunk_size=1000,
        chunk_overlap=100,
    )

    print(f"\nChunking result: {len(chunks)} chunks")

    # Show first 10 chunks
    print("\nFirst 10 chunks:")
    for i, chunk in enumerate(chunks[:10]):
        print(f"\n{'='*60}")
        print(f"[Chunk {i}] heading: {chunk['heading']}")
        print(f"[Chunk {i}] length: {len(chunk['text'])} characters")
        print(f"[Chunk {i}] content preview:")
        # Print first 200 characters
        preview = chunk['text'][:200].encode('utf-8', errors='replace').decode('utf-8')
        print(preview + "..." if len(chunk['text']) > 200 else preview)

    # Statistics
    print(f"\n{'='*60}")
    print("Statistics:")
    print(f"Total chunks: {len(chunks)}")
    print(f"Average chunk size: {sum(len(c['text']) for c in chunks) / len(chunks):.0f} characters")
    print(f"Max chunk size: {max(len(c['text']) for c in chunks)} characters")
    print(f"Min chunk size: {min(len(c['text']) for c in chunks)} characters")


if __name__ == '__main__':
    main()
