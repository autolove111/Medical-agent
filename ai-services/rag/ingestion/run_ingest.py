"""
数据预处理 + 索引构建 CLI 入口

三步流水线：
  Step 1: 清洗  — 从 docs/minerU_md/ 读取原始 md，清洗后存入 to_md/
  Step 2: 分块  — 从 to_md/ 读取清洗后的 md，分块后存入 node_md/
  Step 3: 索引  — 从 to_md/ 读取，分块 + embedding 后存入 PostgreSQL

使用方式：
    cd ai-services
    python -m rag.ingestion.run_ingest              # 执行全部三步
    python -m rag.ingestion.run_ingest --step clean  # 只执行清洗
    python -m rag.ingestion.run_ingest --step chunk  # 只执行分块
    python -m rag.ingestion.run_ingest --step index  # 只构建索引
"""

import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("rag.ingest")


def step_clean(src_dir: Path, out_dir: Path) -> None:
    """Step 1: 清洗 — 读取原始 md，去除 HTML 标签残留，保存到 to_md/。"""
    from rag.ingestion.cleaners import clean_markdown

    out_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(src_dir.glob("*.md"))

    if not files:
        logger.warning("No .md files found in %s", src_dir)
        return

    for f in files:
        raw = f.read_text(encoding="utf-8")
        cleaned = clean_markdown(raw)
        out_path = out_dir / f.name
        out_path.write_text(cleaned, encoding="utf-8")
        logger.info("Cleaned: %s (%d -> %d chars)", f.name, len(raw), len(cleaned))

    logger.info("Step 1 done | %d files cleaned -> %s", len(files), out_dir)


def step_chunk(src_dir: Path, out_dir: Path) -> None:
    """Step 2: 分块 — 读取清洗后的 md，递归标题感知分块，保存到 node_md/。"""
    from rag.ingestion.chunkers import save_nodes_to_files
    from llama_index.core import Document

    out_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(src_dir.glob("*.md"))

    if not files:
        logger.warning("No .md files found in %s", src_dir)
        return

    docs = []
    for f in files:
        text = f.read_text(encoding="utf-8")
        doc = Document(text=text, metadata={"file_name": f.name, "source": str(f)})
        docs.append(doc)

    saved = save_nodes_to_files(docs, output_dir=out_dir)
    logger.info("Step 2 done | %d files chunked -> %d node files in %s", len(docs), saved, out_dir)


def _load_nodes_from_files(node_dir: Path) -> list:
    """从 node_md/ 加载已分块的节点文件，解析为 TextNode 列表。

    返回的节点 id_ 为全局递增序号 (0, 1, 2, ...)。
    原始 Node 编号保存在 metadata["original_node_id"] 中。
    """
    import re
    from llama_index.core.schema import TextNode

    files = sorted(node_dir.glob("*.md"))
    if not files:
        logger.warning("No .md files found in %s", node_dir)
        return []

    nodes = []
    seq_id = 0  # 全局递增序号

    for f in files:
        source_name = f.stem.replace("_nodes", ".md")
        content = f.read_text(encoding="utf-8")

        # 按 --- 分割节点块
        # 格式: ---\n[Node #X] heading: xxx | len: xxx\n---\n内容
        # 去掉文件开头的 ---，避免第一个 block 包含前导 ---
        if content.startswith("---\n"):
            content = content[4:]
        blocks = re.split(r"\n---\n", content)
        i = 0
        while i < len(blocks):
            block = blocks[i].strip()
            if not block:
                i += 1
                continue

            # 检查是否是节点头 [Node #X] heading: xxx | len: xxx
            header_match = re.match(
                r"\[Node #(\d+)\]\s+heading:\s*(.*?)\s*\|\s*len:\s*\d+",
                block,
            )
            if header_match and i + 1 < len(blocks):
                original_id = int(header_match.group(1))
                heading = header_match.group(2)
                text = blocks[i + 1].strip()
                if text:
                    nodes.append(TextNode(
                        text=text,
                        id_=str(seq_id),
                        metadata={
                            "file_name": source_name,
                            "heading": heading,
                            "original_node_id": original_id,
                        },
                    ))
                    seq_id += 1
                i += 2
            else:
                # 没有头信息的块，跳过
                i += 1

    logger.info("Loaded %d nodes from %s", len(nodes), node_dir)
    return nodes


def step_index(node_dir: Path, embed_dim: int) -> None:
    """Step 3: 索引 — 从 node_md/ 加载已分块的节点，embedding 后存入 PostgreSQL。"""
    from rag.ingestion.index_builder import build_index

    nodes = _load_nodes_from_files(node_dir)
    if not nodes:
        logger.warning("No nodes loaded from %s", node_dir)
        return

    try:
        index = build_index(nodes=nodes, embed_dim=embed_dim)
        logger.info("Step 3 done | %d nodes stored in PostgreSQL", len(nodes))
    except Exception as exc:
        logger.error("Index build failed: %s", exc, exc_info=True)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="RAG 数据预处理 + 索引构建")
    parser.add_argument(
        "--step",
        choices=["clean", "chunk", "index", "all"],
        default="all",
        help="执行哪一步（默认 all = 全部执行）",
    )
    parser.add_argument("--embed-dim", type=int, default=768, help="Embedding 向量维度")
    args = parser.parse_args()

    # 初始化 LlamaIndex Settings
    from rag.config import init_llama_settings, DOCS_DIR, TO_MD_DIR, NODE_MD_DIR
    init_llama_settings()

    src_dir = DOCS_DIR / "minerU_md"

    if args.step in ("clean", "all"):
        logger.info("=" * 50)
        logger.info("Step 1: Cleaning %s -> %s", src_dir, TO_MD_DIR)
        logger.info("=" * 50)
        step_clean(src_dir, TO_MD_DIR)

    if args.step in ("chunk", "all"):
        logger.info("=" * 50)
        logger.info("Step 2: Chunking %s -> %s", TO_MD_DIR, NODE_MD_DIR)
        logger.info("=" * 50)
        step_chunk(TO_MD_DIR, NODE_MD_DIR)

    if args.step in ("index", "all"):
        logger.info("=" * 50)
        logger.info("Step 3: Building vector index from %s (dim=%d)", NODE_MD_DIR, args.embed_dim)
        logger.info("=" * 50)
        step_index(NODE_MD_DIR, args.embed_dim)

    logger.info("All done!")


if __name__ == "__main__":
    main()
