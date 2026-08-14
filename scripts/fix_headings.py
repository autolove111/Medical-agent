#!/usr/bin/env python3
"""
扫描md文件，根据文字内容添加正确的标题符号
"""

import re
from pathlib import Path


def fix_heading(line: str) -> str:
    """根据文字内容添加正确的标题符号"""
    stripped = line.strip()

    # 如果已经有正确的多级标题，跳过
    if stripped.startswith('##'):
        return line

    # 去掉已有的单个 #
    if stripped.startswith('#'):
        stripped = stripped[1:].strip()

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

    # 【xxx】 -> #####（只匹配独立成行的）
    if re.match(r'^【[^】]+】', stripped):
        return '##### ' + stripped

    # （一）（二）... -> ######
    if re.match(r'^（[一二三四五六七八九十]+）', stripped):
        return '###### ' + stripped

    return line


def main():
    md_file = Path('e:/xiangmu/dachuang/ai-services/memory/knowledge/docs/《内科学 第10版(1)带书签》完整版.md')

    print(f"Reading: {md_file}")
    with open(md_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    print(f"Total lines: {len(lines)}")

    # 处理每一行
    new_lines = []
    changes = 0
    for line in lines:
        new_line = fix_heading(line)
        if new_line != line:
            changes += 1
        new_lines.append(new_line)

    # 保存
    with open(md_file, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)

    print(f"Done. Changes: {changes}")


if __name__ == '__main__':
    main()
