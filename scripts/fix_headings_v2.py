#!/usr/bin/env python3
"""
两步走：1. 去掉所有# 2. 重新添加正确的标题符号
"""

import re
from pathlib import Path


def remove_all_hashes(line: str) -> str:
    """去掉行首的所有#"""
    return re.sub(r'^#+\s*', '', line)


def add_heading(line: str) -> str:
    """根据文字内容添加正确的标题符号"""
    stripped = line.strip()
    if not stripped:
        return line

    # 第X篇 -> #
    if re.match(r'^第[一二三四五六七八九十百千\d]+篇', stripped):
        return '# ' + stripped

    # 第X章 -> ##
    if re.match(r'^第[一二三四五六七八九十百千\d]+章', stripped):
        return '## ' + stripped

    # 第X节 -> ###
    if re.match(r'^第[一二三四五六七八九十百千\d]+节', stripped):
        return '### ' + stripped

    # 一、二、三、... -> ####
    if re.match(r'^[一二三四五六七八九十]+、', stripped):
        return '#### ' + stripped

    # 【xxx】 -> #####（独立成行的）
    if re.match(r'^【[^】]+】', stripped):
        return '##### ' + stripped

    # （一）（二）... -> ######（全角）
    if re.match(r'^（[一二三四五六七八九十]+）', stripped):
        return '###### ' + stripped

    # (一)(二)... -> ######（半角）
    if re.match(r'^\([一二三四五六七八九十]+\)', stripped):
        return '###### ' + stripped

    return line


def main():
    md_file = Path('e:/xiangmu/dachuang/ai-services/memory/knowledge/docs/《内科学 第10版(1)带书签》完整版.md')

    print(f"Reading: {md_file}")
    with open(md_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    print(f"Total lines: {len(lines)}")

    # Step 1: 去掉所有#
    cleaned_lines = []
    removed = 0
    for line in lines:
        if line.strip().startswith('#'):
            cleaned = remove_all_hashes(line)
            cleaned_lines.append(cleaned)
            removed += 1
        else:
            cleaned_lines.append(line)
    print(f"Step 1: Removed # from {removed} lines")

    # Step 2: 重新添加标题符号
    final_lines = []
    added = 0
    for line in cleaned_lines:
        new_line = add_heading(line)
        if new_line != line:
            added += 1
        final_lines.append(new_line)
    print(f"Step 2: Added heading to {added} lines")

    # 保存
    with open(md_file, 'w', encoding='utf-8') as f:
        f.writelines(final_lines)

    print(f"Done!")


if __name__ == '__main__':
    main()
