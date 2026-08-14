"""
测试集构建辅助工具

用法：
    cd ai-services
    python -m rag.tests.build_test_set

交互式输入问题，自动检索并展示 chunk，用户选择正确的 chunk ID。
最终输出 test_set.json 文件。
"""

import json
import logging
from pathlib import Path
from typing import List, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)
logger = logging.getLogger("rag.build_test_set")


def search_chunks(query: str, top_k: int = 10) -> List[Tuple[str, float, str, str]]:
    """检索并返回 (node_id, score, heading, text_preview) 列表。"""
    from rag.config import init_llama_settings
    init_llama_settings()

    from rag.retrieval.query_engine import get_query_engine

    engine = get_query_engine()
    answer, nodes = engine.retrieve(
        query,
        top_k=top_k,
        use_hybrid=True,
        use_rerank=False,  # 不重排，展示原始检索结果
    )

    results = []
    for node in nodes:
        node_id = node.node.id_ if hasattr(node, 'node') else str(node.id_)
        score = node.score or 0.0
        text = node.get_content()
        # 提取标题（第一行）
        lines = text.strip().split("\n")
        heading = lines[0][:60] if lines else ""
        preview = text[:200].replace("\n", " ")
        results.append((node_id, score, heading, preview))

    return results


def interactive_build():
    """交互式构建测试集。"""
    logger.info("=" * 60)
    logger.info("  RAG 测试集构建工具")
    logger.info("=" * 60)
    logger.info("")
    logger.info("输入问题，系统会检索相关 chunk。")
    logger.info("选择正确的 chunk ID，构建测试集。")
    logger.info("输入 'quit' 退出，输入 'save' 保存。")
    logger.info("")

    test_set = []
    output_file = Path(__file__).parent / "test_set.json"

    while True:
        # 输入问题
        question = input("\n请输入问题: ").strip()
        if question.lower() == "quit":
            break
        if question.lower() == "save":
            break

        if not question:
            continue

        # 检索
        logger.info("\n检索中...")
        results = search_chunks(question, top_k=10)

        # 展示结果
        logger.info("\n检索结果：")
        logger.info("-" * 60)
        for i, (node_id, score, heading, preview) in enumerate(results):
            logger.info("[%d] score=%.4f  %s", i + 1, score, heading)
            logger.info("    ID: %s", node_id)
            logger.info("    %s", preview[:100])
            logger.info("")

        # 选择正确的 chunk
        logger.info("选择正确的 chunk（输入序号，多个用逗号分隔，0=跳过）：")
        choice = input(">>> ").strip()

        if choice == "0" or not choice:
            logger.info("跳过此问题")
            continue

        try:
            indices = [int(x.strip()) - 1 for x in choice.split(",")]
            relevant_ids = []
            for idx in indices:
                if 0 <= idx < len(results):
                    relevant_ids.append(results[idx][0])
                    logger.info("  选择: [%d] %s", idx + 1, results[idx][2])
        except ValueError:
            logger.warning("输入无效，跳过")
            continue

        if relevant_ids:
            test_set.append({
                "question": question,
                "relevant_ids": relevant_ids,
            })
            logger.info("已添加到测试集（共 %d 条）", len(test_set))

    # 保存
    if test_set:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(test_set, f, ensure_ascii=False, indent=2)
        logger.info("\n测试集已保存到: %s（共 %d 条）", output_file, len(test_set))
    else:
        logger.info("\n测试集为空，未保存")


def main():
    interactive_build()


if __name__ == "__main__":
    main()
