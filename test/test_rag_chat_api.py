#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LANGCHAIN_ROOT = PROJECT_ROOT / "langchain_service"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="测试聊天接口，并打印全局 RAG 检索命中的参考文档。"
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("LANGCHAIN_SERVICE_URL", "http://127.0.0.1:8000"),
        help="LangChain 服务地址，默认 http://127.0.0.1:8000",
    )
    parser.add_argument(
        "--agent-type",
        default="general",
        help="智能体类型，当前仅保留 general",
    )
    parser.add_argument(
        "--question",
        default="肌酐升高时应该做哪些检查？",
        help="测试问题",
    )
    parser.add_argument(
        "--skip-direct-rag",
        action="store_true",
        help="跳过直接 RAG 检索测试，只调用 HTTP 接口",
    )
    parser.add_argument(
        "--skip-api",
        action="store_true",
        help="跳过 HTTP 接口测试，只做直接 RAG 检索",
    )
    return parser.parse_args()


def print_title(title: str) -> None:
    print(f"\n{'=' * 24} {title} {'=' * 24}")


def preview_text(text: str, limit: int = 220) -> str:
    normalized = (text or "").replace("\r", " ").replace("\n", " ").strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit] + "..."


def print_source_items(items: Iterable[Tuple[str, Dict[str, Any], str]]) -> None:
    items = list(items)
    if not items:
        print("未检索到 sources。")
        return

    for idx, (label, metadata, content) in enumerate(items, start=1):
        print(f"[{idx}] 来源: {label or 'unknown'}")
        if metadata:
            print(f"    metadata: {json.dumps(metadata, ensure_ascii=False)}")
        print(f"    片段: {preview_text(content)}")


def run_direct_rag(question: str, agent_type: str) -> None:
    print_title("直接 RAG 检索")
    print(f"问题: {question}")
    print(f"agent_type: {agent_type}")

    sys.path.insert(0, str(LANGCHAIN_ROOT))
    try:
        from agents import create_agent  # type: ignore
    except Exception as exc:
        print(f"直接 RAG 测试失败，导入模块出错: {exc}")
        return

    try:
        agent = create_agent(agent_type=agent_type, user_id="rag-test-user")
        rag_text, sources = agent.resolve_rag_context(question)
    except Exception as exc:
        print(f"直接 RAG 检索失败: {exc}")
        return

    print("\nRAG 格式化结果:")
    print(rag_text or "无")
    print("\nRAG 原始命中文档:")
    print_source_items(
        (
            str(getattr(doc, "metadata", {}).get("source", "unknown")),
            getattr(doc, "metadata", {}),
            getattr(doc, "page_content", ""),
        )
        for doc in (sources or [])
    )


def post_json(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url=url,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw)


def run_chat_api(base_url: str, question: str, agent_type: str) -> None:
    print_title("聊天接口测试")
    print(f"URL: {base_url.rstrip('/')}/api/v1/agent/chat")
    print(f"问题: {question}")
    print(f"agent_type: {agent_type}")

    payload = {
        "query": question,
        "agent_type": agent_type,
        "user_id": "rag-test-user",
    }

    try:
        result = post_json(f"{base_url.rstrip('/')}/api/v1/agent/chat", payload)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP 请求失败: {exc.code} {exc.reason}")
        print(detail)
        return
    except Exception as exc:
        print(f"调用聊天接口失败: {exc}")
        return

    print("\n模型回答:")
    print(result.get("content", ""))

    print("\n接口返回的 RAG sources:")
    print_source_items(
        (
            str((item or {}).get("metadata", {}).get("source", "unknown")),
            (item or {}).get("metadata", {}),
            str((item or {}).get("content", "")),
        )
        for item in result.get("sources", []) or []
    )

    print("\nmetadata:")
    print(json.dumps(result.get("metadata", {}), ensure_ascii=False, indent=2))


def main() -> None:
    args = parse_args()

    print_title("测试参数")
    print(f"项目根目录: {PROJECT_ROOT}")
    print(f"问题: {args.question}")
    print(f"agent_type: {args.agent_type}")
    print(f"base_url: {args.base_url}")

    if not args.skip_direct_rag:
        run_direct_rag(args.question, args.agent_type)

    if not args.skip_api:
        run_chat_api(args.base_url, args.question, args.agent_type)


if __name__ == "__main__":
    main()
