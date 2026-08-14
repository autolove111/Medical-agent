#!/usr/bin/env python3
"""
合并页面脚本
将一本书的所有页面合并为一个完整文档
"""

import os
import re
import shutil
from pathlib import Path


def extract_page_number(folder_name: str) -> int:
    """从文件夹名提取页码数字"""
    # page_1 -> 1, page_10 -> 10
    match = re.search(r'page_(\d+)', folder_name)
    if match:
        return int(match.group(1))
    return 0


def find_md_file(page_dir: Path) -> Path | None:
    """查找页面目录下的md文件"""
    # 递归查找vlm目录下的.md文件
    for vlm_dir in page_dir.rglob('vlm'):
        for md_file in vlm_dir.glob('*.md'):
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

    # 创建目标目录
    page_target = target_dir / f'page_{page_num}'
    page_target.mkdir(parents=True, exist_ok=True)

    # 复制所有图片
    for img_file in images_dir.glob('*.jpg'):
        shutil.copy2(img_file, page_target / img_file.name)
    for img_file in images_dir.glob('*.png'):
        shutil.copy2(img_file, page_target / img_file.name)


def update_image_paths(content: str, page_num: int) -> str:
    """更新md文件中的图片路径"""
    # 匹配 ![](images/xxx.jpg) 格式
    pattern = r'!\[([^\]]*)\]\(images/([^)]+)\)'

    def replace_path(match):
        alt_text = match.group(1)
        img_name = match.group(2)
        return f'![{alt_text}](images/page_{page_num}/{img_name})'

    return re.sub(pattern, replace_path, content)


def merge_pages(book_dir: Path, output_dir: Path):
    """合并所有页面"""
    print(f"开始合并: {book_dir.name}")

    # 创建输出目录
    output_dir.mkdir(parents=True, exist_ok=True)
    images_output = output_dir / 'images'
    images_output.mkdir(exist_ok=True)

    # 扫描所有页面文件夹
    page_folders = []
    for pages_dir in book_dir.glob('pages_*'):
        for page_dir in pages_dir.glob('page_*'):
            page_num = extract_page_number(page_dir.name)
            if page_num > 0:
                page_folders.append((page_num, page_dir))

    # 按页码排序
    page_folders.sort(key=lambda x: x[0])
    print(f"找到 {len(page_folders)} 个页面")

    # 合并内容
    merged_content = []
    processed = 0

    for page_num, page_dir in page_folders:
        # 查找md文件
        md_file = find_md_file(page_dir)
        if not md_file:
            print(f"警告: page_{page_num} 没有找到md文件")
            continue

        # 读取md文件内容
        with open(md_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 查找并复制图片
        images_dir = find_images_dir(page_dir)
        if images_dir:
            copy_images(images_dir, images_output, page_num)

        # 更新图片路径
        content = update_image_paths(content, page_num)

        # 添加到合并内容
        merged_content.append(content)
        processed += 1

        if processed % 50 == 0:
            print(f"已处理 {processed}/{len(page_folders)} 个页面")

    # 合并所有内容
    final_content = '\n\n'.join(merged_content)

    # 保存结果
    output_file = output_dir / f'{book_dir.name}完整版.md'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(final_content)

    print(f"合并完成: {output_file}")
    print(f"共处理 {processed} 个页面")
    print(f"图片目录: {images_output}")


def main():
    # 配置路径
    docs_dir = Path('e:/xiangmu/dachuang/ai-services/memory/knowledge/docs')
    output_dir = Path('e:/xiangmu/dachuang/ai-services/memory/knowledge/docs')

    # 处理内科学
    book_dir = docs_dir / '《内科学 第10版(1)带书签》'
    if book_dir.exists():
        merge_pages(book_dir, output_dir)
    else:
        print(f"目录不存在: {book_dir}")


if __name__ == '__main__':
    main()
