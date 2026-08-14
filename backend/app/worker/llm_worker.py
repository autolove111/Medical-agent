"""
LLM Worker：从 LLM 队列拉取请求，调用模型 API，回传结果

启动方式：
    cd backend
    python -m app.worker.llm_worker
"""

import json
import logging
import sys
import os
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [LLM-Worker] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("llm_worker")

# 路径设置：backend/app/（broker）和 ai-services/（AI 模块）
_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROJECT_DIR = os.path.dirname(_APP_DIR)
_AI_DIR = os.path.join(_PROJECT_DIR, "..", "ai-services")

for _p in [_APP_DIR, _AI_DIR]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


def do_llm_call(messages: list, tools: list = None) -> dict:
    """调用 LLM API，返回响应。"""
    from llm.chat_model import ChatModel

    llm = ChatModel()
    response = llm.invoke(messages, tools=tools if tools else None)
    assistant = response.choices[0].message

    result = {
        "content": assistant.content or "",
        "reasoning_content": getattr(assistant, "reasoning_content", None),
        "finish_reason": response.choices[0].finish_reason,
        "tool_calls": None,
    }

    if assistant.tool_calls:
        result["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in assistant.tool_calls
        ]

    return result


def main():
    from broker.redis_impl import RedisBroker

    broker = RedisBroker()

    logger.info("=" * 50)
    logger.info("LLM Worker started")
    logger.info("=" * 50)

    # 预热
    try:
        from llm.chat_model import ChatModel
        ChatModel()
        logger.info("LLM warmup complete")
    except Exception as exc:
        logger.warning("LLM warmup failed: %s", exc)

    while True:
        try:
            request = broker.pop_llm_request(timeout=0)
            if request is None:
                continue

            task_id = request["task_id"]
            messages = request["messages"]
            tools = request.get("tools", [])

            logger.info("▶ LLM request | task_id=%s msgs=%d", task_id, len(messages))
            # 打印完整 messages 用于调试
            logger.info("  Full messages: %s", json.dumps(messages, ensure_ascii=False, indent=2)[:5000])
            for i, m in enumerate(messages):
                role = m.get("role", "?")
                if role == "assistant" and m.get("tool_calls"):
                    for tc in m["tool_calls"]:
                        logger.info("  [%d] assistant tool_call id=%s", i, tc.get("id"))
                elif role == "tool":
                    logger.info("  [%d] tool id=%s", i, m.get("tool_call_id"))

            start = time.time()
            result = do_llm_call(messages, tools)
            elapsed = time.time() - start

            broker.push_llm_result({
                "type": "llm_result",
                "task_id": task_id,
                "content": result["content"],
                "reasoning_content": result["reasoning_content"],
                "tool_calls": result["tool_calls"],
                "finish_reason": result["finish_reason"],
            })

            logger.info("✓ LLM done | task_id=%s elapsed=%.1fs finish=%s",
                        task_id, elapsed, result["finish_reason"])

        except KeyboardInterrupt:
            logger.info("LLM Worker interrupted")
            break
        except Exception as exc:
            logger.error("LLM Worker error: %s", exc, exc_info=True)
            if "task_id" in locals():
                broker.push_llm_result({
                    "type": "llm_result",
                    "task_id": task_id,
                    "content": "",
                    "tool_calls": None,
                    "finish_reason": "error",
                    "error": str(exc),
                })


if __name__ == "__main__":
    main()
