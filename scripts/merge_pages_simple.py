#!/usr/bin/env python3
"""
最基础的页面合并：直接读取md文件按页码拼接，不做任何标题处理
"""

import re
import shutil
from pathlib import Path


def extract_page_number(folder_name: str) -> int:
    """从文件夹名提取页码数字"""
    match = re.search(r'page_(\d+)', folder_name)
    if match:
        return int(match.group(1))
    return 0


def find_md_file(page_dir: Path) -> Path | None:
    """查找页面目录下的md文件"""
    for vlm_dir in page_dir.rglob('vlm'):
        for md_file in vlm_dir.glob('*.md'):
            if '_content_list' not in md_file.name and '_middle' not in md_file.name and '_model' not in md_file.name:
                return md_file
    return None


def find_images_dir(page_dir: Path) -> Path | None:
    """查找页面目录下的images文件夹"""
    for vlm_dir in page_dir.rglob('vlm'):
        images_dir = vlm_dir / 'images'
        if images_dir.exists():
            return images_dir
    return None


def copy_images(images_dir: Path, target_dir: Path, page_num: int):
    """复制图片到目标目录"""
    if not images_dir.exists():
        return
    page_target = target_dir / f'page_{page_num}'
    page_target.mkdir(parents=True, exist_ok=True)
    for img_file in images_dir.glob('*.jpg'):
        shutil.copy2(img_file, page_target / img_file.name)
    for img_file in images_dir.glob('*.png'):
        shutil.copy2(img_file, page_target / img_file.name)


def update_image_paths(content: str, page_num: int) -> str:
    """更新md文件中的图片路径"""
    pattern = r'!\[([^\]]*)\]\(images/([^)]+)\)'
    def replace_path(match):
        alt_text = match.group(1)
        img_name = match.group(2)
        return f'![{alt_text}](images/page_{page_num}/{img_name})'
    return re.sub(pattern, replace_path, content)


def main():
    docs_dir = Path('e:/xiangmu/dachuang/ai-services/memory/knowledge/docs')
    book_dir = docs_dir / '《内科学 第10版(1)带书签》'
    output_file = docs_dir / '《内科学 第10版(1)带书签》完整版.md'
    images_output = docs_dir / 'images'

    print(f"Processing: {book_dir.name}")

    images_output.mkdir(parents=True, exist_ok=True)

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

    # 合并内容
    merged_content = []
    processed = 0

    for page_num, page_dir in page_folders:
        md_file = find_md_file(page_dir)
        if not md_file:
            print(f"Warning: page_{page_num} - no md file found")
            continue

        with open(md_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 复制图片
        images_dir = find_images_dir(page_dir)
        if images_dir:
            copy_images(images_dir, images_output, page_num)

        # 更新图片路径
        content = update_image_paths(content, page_num)

        if content.strip():
            merged_content.append(content)

        processed += 1
        if processed % 100 == 0:
            print(f"Processed {processed}/{len(page_folders)} pages")

    # 保存
    final_content = '\n\n'.join(merged_content)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(final_content)

    print(f"Done: {output_file}")
    print(f"Pages: {processed}, Size: {len(final_content)} chars")


if __name__ == '__main__':
    main()
