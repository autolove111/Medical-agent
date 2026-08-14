"""
OCR Service - 调用 MinerU 精准解析 API，返回原始 Markdown

职责：调 MinerU → 下载 ZIP → 返回 full.md 原始文本
解析逻辑在 indicator_analyse.py 中

使用示例：
  raw_md = await call_mineru("uploads/report.jpg")
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import tempfile
import time
import zipfile

import httpx

logger = logging.getLogger("ocr_service")

# ── MinerU 配置 ──────────────────────────────────────────────
MINERU_API_BASE_URL = os.getenv("MINERU_API_BASE_URL", "https://mineru.net")
MINERU_API_TOKEN = os.getenv("MINERU_API_TOKEN", "")
MINERU_POLL_INTERVAL = int(os.getenv("MINERU_POLL_INTERVAL", "3"))
MINERU_POLL_TIMEOUT = int(os.getenv("MINERU_POLL_TIMEOUT", "300"))
MINERU_MODEL_VERSION = os.getenv("MINERU_MODEL_VERSION", "vlm")


# ═══════════════════════════════════════════════════════════════
# 公开 API
# ═══════════════════════════════════════════════════════════════

async def call_mineru(file_path: str) -> str:
    """
    调用 MinerU 精准解析 API，返回原始 Markdown 文本

    Args:
        file_path: 图片或 PDF 文件路径

    Returns:
        MinerU 输出的 full.md 原始文本
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")

    logger.info("[MinerU] 开始提取: %s", file_path)

    # Step 1: 获取上传 URL + batch_id
    batch_id, upload_url = await _get_upload_url(file_path)
    logger.info("[MinerU] 获取上传链接: batch_id=%s", batch_id)

    # Step 2: PUT 文件到 OSS（无 Content-Type）
    await _upload_file(upload_url, file_path)
    logger.info("[MinerU] 文件已上传")

    # Step 3: 轮询 batch 结果
    zip_url = await _poll_batch(batch_id)
    logger.info("[MinerU] 任务完成, ZIP URL: %s", zip_url[:80])

    # Step 4: 下载 ZIP → 解压 → 读取 full.md
    markdown_text = await _download_and_extract(zip_url)
    logger.info("[MinerU] 提取 full.md (%d 字符)", len(markdown_text))

    return markdown_text


# ═══════════════════════════════════════════════════════════════
# MinerU v4 API 流程
# ═══════════════════════════════════════════════════════════════

async def _get_upload_url(file_path: str) -> tuple[str, str]:
    """POST /api/v4/file-urls/batch → (batch_id, upload_url)"""
    base_url = MINERU_API_BASE_URL.rstrip("/")
    file_name = os.path.basename(file_path)

    headers = {}
    if MINERU_API_TOKEN:
        headers["Authorization"] = f"Bearer {MINERU_API_TOKEN}"

    payload = {
        "files": [{"name": file_name, "is_ocr": True}],
        "model_version": MINERU_MODEL_VERSION,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{base_url}/api/v4/file-urls/batch",
            headers=headers,
            json=payload,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"MinerU 获取上传链接失败: HTTP {resp.status_code} - {resp.text[:500]}")

        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"MinerU 获取上传链接错误: {data.get('msg', 'unknown')}")

        batch_id = data["data"]["batch_id"]
        file_urls = data["data"]["file_urls"]
        if not file_urls:
            raise RuntimeError(f"MinerU 未返回上传链接: {data}")

        return batch_id, file_urls[0]


async def _upload_file(upload_url: str, file_path: str) -> None:
    """PUT 文件到 OSS 预签名 URL（不设 Content-Type）"""
    with open(file_path, "rb") as f:
        file_content = f.read()

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        resp = await client.put(upload_url, content=file_content)
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"文件上传失败: HTTP {resp.status_code}")


async def _poll_batch(batch_id: str) -> str:
    """GET /api/v4/extract-results/batch/{batch_id} → full_zip_url"""
    base_url = MINERU_API_BASE_URL.rstrip("/")
    headers = {}
    if MINERU_API_TOKEN:
        headers["Authorization"] = f"Bearer {MINERU_API_TOKEN}"

    start_time = time.time()
    interval = MINERU_POLL_INTERVAL
    timeout = MINERU_POLL_TIMEOUT

    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout:
                raise TimeoutError(f"MinerU 批次 {batch_id} 超时 ({timeout}s)")

            resp = await client.get(
                f"{base_url}/api/v4/extract-results/batch/{batch_id}",
                headers=headers,
            )
            if resp.status_code != 200:
                logger.debug("轮询返回 %d, 重试中...", resp.status_code)
                await asyncio.sleep(interval)
                continue

            data = resp.json()
            results = data.get("data", {}).get("extract_result", [])
            if not results:
                logger.debug("轮询无结果, 重试中...")
                await asyncio.sleep(interval)
                continue

            result = results[0]
            state = result.get("state", "")

            if state == "done":
                zip_url = result.get("full_zip_url", "")
                if not zip_url:
                    raise RuntimeError(f"MinerU 完成但无 ZIP URL: {result}")
                return zip_url

            if state == "failed":
                err_msg = result.get("err_msg", "unknown error")
                raise RuntimeError(f"MinerU 解析失败: {err_msg}")

            progress = result.get("extract_progress", {})
            pages = f"{progress.get('extracted_pages', '?')}/{progress.get('total_pages', '?')}" if progress else ""
            logger.debug("[MinerU] 轮询 %s: state=%s pages=%s elapsed=%.0fs",
                         batch_id, state, pages, elapsed)
            await asyncio.sleep(interval)


async def _download_and_extract(zip_url: str) -> str:
    """下载 ZIP 压缩包，解压并返回 full.md 内容"""
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        resp = await client.get(zip_url)
        resp.raise_for_status()

    zip_bytes = resp.content
    logger.info("[MinerU] 下载 ZIP: %d bytes", len(zip_bytes))

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        extract_dir = tempfile.mkdtemp(prefix="mineru_")
        zf.extractall(extract_dir)

        full_md_path = None
        for root, dirs, files in os.walk(extract_dir):
            if "full.md" in files:
                full_md_path = os.path.join(root, "full.md")
                break

        if not full_md_path:
            all_files = []
            for root, dirs, files in os.walk(extract_dir):
                for f in files:
                    all_files.append(os.path.relpath(os.path.join(root, f), extract_dir))
            raise RuntimeError(f"ZIP 中未找到 full.md。可用文件: {all_files[:20]}")

        # 尝试多种编码读取
        raw_bytes = open(full_md_path, "rb").read()
        for encoding in ["utf-8", "gbk", "gb2312", "gb18030"]:
            try:
                return raw_bytes.decode(encoding)
            except (UnicodeDecodeError, LookupError):
                continue
        return raw_bytes.decode("utf-8", errors="replace")


# ═══════════════════════════════════════════════════════════════
# 测试入口
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    async def main():
        if len(sys.argv) < 2:
            print("用法: python ocr_service.py <图片路径>")
            sys.exit(1)

        raw_md = await call_mineru(sys.argv[1])
        print(raw_md)

    asyncio.run(main())
