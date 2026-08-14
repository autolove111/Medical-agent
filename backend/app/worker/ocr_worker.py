"""
OCR Worker：从 OCR 队列拉取请求，调用 MinerU 识别，结果写入 Redis

启动方式：
    cd backend
    python -m app.worker.ocr_worker
"""

import json
import logging
import os
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [OCR-Worker] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ocr_worker")

# 路径设置：backend/app/（broker）和 ai-services/（AI 模块）
_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROJECT_DIR = os.path.dirname(_APP_DIR)
_AI_DIR = os.path.join(_PROJECT_DIR, "..", "ai-services")

for _p in [_APP_DIR, _AI_DIR]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _format_ocr_result(user_name: str, indicators: list[dict]) -> str:
    """格式化 OCR 结果为用户消息格式"""
    lines = [f"我是{user_name}，这是我的化验单结果："]
    for i in indicators:
        status_map = {
            "high": "↑", "low": "↓",
            "critical_high": "↑↑危急", "critical_low": "↓↓危急", "normal": "",
        }
        flag = status_map.get(i["status"], "")
        lines.append(f"{i['name']}（{i['key']}）：{i['value']} {i['unit']} [参考:{i['ref_range']}] {flag}")
    return "\n".join(lines)


def process_ocr_task(task_id: str, file_path: str) -> dict:
    """
    同步处理一个 OCR 任务：调用 MinerU → 指标分析。

    返回结果字典，由调用方写入 Redis。
    """
    import asyncio
    from ocr.ocr_service import call_mineru
    from indicator_analyse.indicator_analyse import parse_markdown_to_patient_labs, analyze_indicators

    # 1. 调用 MinerU OCR → 原始 Markdown
    logger.info("▶ OCR start | task_id=%s file=%s", task_id, os.path.basename(file_path))
    start = time.time()

    raw_markdown = asyncio.run(call_mineru(file_path))
    elapsed = time.time() - start

    logger.info("✓ OCR done | task_id=%s md_len=%d elapsed=%.1fs",
                task_id, len(raw_markdown), elapsed)

    # 2. 解析 Markdown → 指标字典
    patient_labs = parse_markdown_to_patient_labs(raw_markdown)
    logger.info("✓ Parse done | task_id=%s indicators=%d", task_id, len(patient_labs))

    # 3. 指标分析（从任务状态读取年龄和性别）
    from broker.redis_impl import RedisBroker
    broker = RedisBroker()
    task_status = broker.get_task_status(task_id, task_type="ocr")
    age = int((task_status or {}).get("age", 0))
    gender = (task_status or {}).get("gender", "")

    indicators = analyze_indicators(patient_labs, age=age, gender=gender)
    abnormal_count = sum(1 for i in indicators if i["status"] != "normal")
    normal_count = sum(1 for i in indicators if i["status"] == "normal")
    logger.info("✓ Analysis done | task_id=%s abnormal=%d normal=%d age=%d gender=%s",
                task_id, abnormal_count, normal_count, age, gender)

    # 4. 只写入原始 Markdown 到短期记忆（不写入分析结果）
    try:
        from memory.short_memory.store import ShortMemoryStore
        user_id = (task_status or {}).get("user_id", "default")
        session_id = (task_status or {}).get("session_id", "default")
        store = ShortMemoryStore(user_id=user_id, session_id=session_id)
        store.add_user_message("📋 化验单识别结果：\n\n" + raw_markdown)
        logger.info("✓ Raw markdown saved to memory | task_id=%s", task_id)
    except Exception as e:
        logger.warning("Memory save failed | task_id=%s: %s", task_id, e)

    # 5. 返回结果（不写入记忆，只返回给前端）
    report_id = f"rpt_{task_id[:12]}"
    report_date = time.strftime("%Y-%m-%d")

    return {
        "report_id": report_id,
        "report_date": report_date,
        "indicators": indicators,
        "abnormal_count": abnormal_count,
        "normal_count": normal_count,
        "raw_markdown": raw_markdown,
    }


def main():
    from broker.redis_impl import RedisBroker

    broker = RedisBroker()

    logger.info("=" * 50)
    logger.info("OCR Worker started")
    logger.info("=" * 50)

    while True:
        try:
            request = broker.pop_ocr_request(timeout=5)  # 阻塞等待，不空转
            if request is None:
                continue

            task_id = request["task_id"]
            file_path = request["file_path"]

            # 更新状态：处理中
            broker.update_task_status(task_id, "processing", task_type="ocr")

            # 处理 OCR
            result = process_ocr_task(task_id, file_path)

            # 结果写入 Redis Hash
            broker.update_task_status(task_id, "done", task_type="ocr", **result)

            # Pub/Sub 通知前端
            broker.publish_stream_chunk(task_id, "ocr_complete", {
                "status": "done",
                "report_id": result.get("report_id", ""),
                "indicators_count": len(result.get("indicators", [])),
                "abnormal_count": result.get("abnormal_count", 0),
            })

            logger.info("✓ OCR task complete | task_id=%s", task_id)

        except KeyboardInterrupt:
            logger.info("OCR Worker interrupted")
            break
        except Exception as exc:
            logger.error("OCR Worker error: %s", exc, exc_info=True)
            # 写入错误状态
            if "task_id" in locals():
                broker.update_task_status(task_id, "error", task_type="ocr", error=str(exc))
                broker.publish_stream_chunk(task_id, "ocr_complete", {
                    "status": "error", "error": str(exc),
                })


if __name__ == "__main__":
    main()
