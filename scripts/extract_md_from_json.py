#!/usr/bin/env python3
"""
从JSON文件重新提取Markdown，保留标题层级
"""

import json
import re
from pathlib import Path


def extract_page_number(folder_name: str) -> int:
    """从文件夹名提取页码数字"""
    match = re.search(r'page_(\d+)', folder_name)
    if match:
        return int(match.group(1))
    return 0


def find_json_file(page_dir: Path) -> Path | None:
    """查找页面目录下的content_list_v2.json文件"""
    for vlm_dir in page_dir.rglob('vlm'):
        json_file = vlm_dir / '*_content_list_v2.json'
        for f in vlm_dir.glob('*_content_list_v2.json'):
            return f
    return None


def infer_heading_level(title_text: str) -> int:
    """根据标题内容推断层级"""
    # 第X篇 -> level 1
    if re.match(r'^第[一二三四五六七八九十百千\d]+篇', title_text):
        return 1
    # 第X章 -> level 2
    elif re.match(r'^第[一二三四五六七八九十百千\d]+章', title_text):
        return 2
    # 第X节 -> level 3
    elif re.match(r'^第[一二三四五六七八九十百千\d]+节', title_text):
        return 3
    # 一、二、三... -> level 4
    elif re.match(r'^[一二三四五六七八九十]+、', title_text):
        return 4
    # (一)、(二)... -> level 5
    elif re.match(r'^（[一二三四五六七八九十]+）', title_text):
        return 5
    # 1. 2. 3. ... -> level 6
    elif re.match(r'^\d+[\.\、]', title_text):
        return 6
    # 默认 level 1
    else:
        return 1


def merge_consecutive_titles(items: list) -> list:
    """合并相邻的短标题块（如"第二篇" + "呼吸系统疾病" -> "第二篇 呼吸系统疾病"）"""
    merged = []
    i = 0
    while i < len(items):
        item = items[i]
        item_type = item.get('type', '')

        if item_type == 'title':
            content = item.get('content', {})
            title_content = content.get('title_content', [])
            title_text = ''
            for tc in title_content:
                if tc.get('type') == 'text':
                    title_text += tc.get('content', '')

            # 检查是否需要与下一个标题合并
            # 条件：当前标题较短（< 10字），且下一项也是标题
            if title_text and len(title_text) < 10 and i + 1 < len(items):
                next_item = items[i + 1]
                if next_item.get('type') == 'title':
                    next_content = next_item.get('content', {})
                    next_title_content = next_content.get('title_content', [])
                    next_text = ''
                    for tc in next_title_content:
                        if tc.get('type') == 'text':
                            next_text += tc.get('content', '')

                    if next_text:
                        # 合并两个标题
                        combined = title_text + ' ' + next_text
                        new_item = dict(item)
                        new_item['content'] = dict(content)
                        new_item['content']['title_content'] = [{'type': 'text', 'content': combined}]
                        merged.append(new_item)
                        i += 2  # 跳过下一个标题
                        continue

        merged.append(item)
        i += 1

    return merged


def json_to_markdown(json_data: list) -> str:
    """将JSON数据转换为Markdown，保留标题层级"""
    # 先合并相邻的短标题
    json_data = merge_consecutive_titles(json_data)

    markdown_parts = []

    for item in json_data:
        item_type = item.get('type', '')

        if item_type == 'title':
            # 标题：根据内容推断层级
            content = item.get('content', {})
            title_content = content.get('title_content', [])

            # 提取标题文本
            title_text = ''
            for tc in title_content:
                if tc.get('type') == 'text':
                    title_text += tc.get('content', '')

            if title_text:
                # 根据内容推断层级
                level = infer_heading_level(title_text)
                heading = '#' * level + ' ' + title_text
                markdown_parts.append(heading)

        elif item_type == 'paragraph':
            # 段落：直接添加内容
            content = item.get('content', {})
            paragraph_content = content.get('paragraph_content', [])

            paragraph_text = ''
            for pc in paragraph_content:
                if pc.get('type') == 'text':
                    paragraph_text += pc.get('content', '')

            if paragraph_text:
                markdown_parts.append(paragraph_text)

        elif item_type == 'table':
            # 表格：需要特殊处理
            content = item.get('content', {})
            table_content = content.get('table_content', [])

            if table_content:
                # 简单处理：将表格内容作为文本添加
                table_text = ''
                for row in table_content:
                    row_text = ''
                    for cell in row:
                        if isinstance(cell, dict):
                            cell_content = cell.get('content', '')
                            if isinstance(cell_content, list):
                                for cc in cell_content:
                                    if cc.get('type') == 'text':
                                        row_text += cc.get('content', '') + ' | '
                            else:
                                row_text += str(cell_content) + ' | '
                        else:
                            row_text += str(cell) + ' | '
                    table_text += row_text.rstrip(' | ') + '\n'

                if table_text:
                    markdown_parts.append(table_text)

        elif item_type == 'image':
            # 图片：添加图片引用
            content = item.get('content', {})
            img_path = content.get('img_path', '')
            if img_path:
                markdown_parts.append(f'![]({img_path})')

    return '\n\n'.join(markdown_parts)


def process_book(book_dir: Path, output_file: Path):
    """处理整本书"""
    print(f"Processing: {book_dir.name}")

    # 扫描所有页面文件夹
    page_folders = []
    for pages_dir in book_dir.glob('pages_*'):
        for page_dir in pages_dir.glob('page_*'):
            page_num = extract_page_number(page_dir.name)
            if page_num > 0:
                page_folders.append((page_num, page_dir))

    # 按页码排序
    page_folders.sort(key=lambda x: x[0])
    print(f"Found {len(page_folders)} pages")

    # 处理每个页面
    all_markdown = []
    processed = 0

    for page_num, page_dir in page_folders:
        # 查找JSON文件
        json_file = find_json_file(page_dir)
        if not json_file:
            print(f"Warning: page_{page_num} - no JSON file found")
            continue

        # 读取JSON文件
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
        except Exception as e:
            print(f"Error reading {json_file}: {e}")
            continue

        # 转换为Markdown
        if isinstance(json_data, list) and len(json_data) > 0:
            # 有些JSON文件是嵌套列表
            if isinstance(json_data[0], list):
                json_data = json_data[0]

            markdown = json_to_markdown(json_data)
            if markdown.strip():
                all_markdown.append(markdown)

        processed += 1
        if processed % 100 == 0:
            print(f"Processed {processed}/{len(page_folders)} pages")

    # 合并所有内容
    final_markdown = '\n\n'.join(all_markdown)

    # 保存结果
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(final_markdown)

    print(f"Saved to: {output_file}")
    print(f"Total pages: {processed}")
    print(f"File size: {len(final_markdown)} characters")


def main():
    # 配置路径
    docs_dir = Path('e:/xiangmu/dachuang/ai-services/memory/knowledge/docs')
    book_dir = docs_dir / '《内科学 第10版(1)带书签》'
    output_file = docs_dir / '《内科学 第10版(1)带书签》完整版.md'

    if not book_dir.exists():
        print(f"Book directory not found: {book_dir}")
        return

    process_book(book_dir, output_file)


if __name__ == '__main__':
    main()
