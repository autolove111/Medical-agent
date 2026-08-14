"""
事件写入缓冲（Write-Behind 模式）

职责：
  - 从 Redis 同步队列读取待持久化消息
  - 后台线程定时批量写入 PostgreSQL
  - 同步刷盘确保最终结果不丢

数据流：
  ShortMemoryStore._push_sync() → Redis List → EventBuffer → PostgreSQL
"""

import logging
import threading
import time
from typing import Optional

from memory.persistence.database import get_session as get_db_session
from memory.persistence.repositories.events_record_repo import EventsRecordRepo
from memory.short_memory.store import ShortMemoryStore

logger = logging.getLogger(__name__)

# 刷盘间隔（秒）
FLUSH_INTERVAL = 1.5

# 单次最大批量条数
FLUSH_BATCH_SIZE = 100


class EventBuffer:
    """对话事件写入缓冲（Write-Behind）。

    从 Redis 同步队列读取消息，后台线程定时批量写入 PostgreSQL。
    压缩只影响主消息列表，不影响同步队列。
    """

    def __init__(self, user_id: str, session_id: str):
        self._user_id = user_id
        self._session_id = session_id
        self._stm = ShortMemoryStore(user_id, session_id)
        self._running = False
        self._flush_thread: Optional[threading.Thread] = None

    def start(self):
        """启动后台刷盘线程。"""
        if self._running:
            return
        self._running = True
        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._flush_thread.start()
        logger.info("EventBuffer flush thread started (interval=%.1fs)", FLUSH_INTERVAL)

    def stop(self):
        """停止后台线程并刷完剩余数据。"""
        self._running = False
        if self._flush_thread:
            self._flush_thread.join(timeout=5)
        self.flush_sync()
        logger.info("EventBuffer stopped")

    def flush_sync(self):
        """同步刷盘（阻塞直到写完）。"""
        while True:
            batch = self._stm.pop_sync_batch(FLUSH_BATCH_SIZE)
            if not batch:
                break
            self._write_to_db(batch)

    def _flush_loop(self):
        """后台刷盘循环。"""
        while self._running:
            time.sleep(FLUSH_INTERVAL)

            # 循环刷直到队列清空
            while self._running:
                batch = self._stm.pop_sync_batch(FLUSH_BATCH_SIZE)
                if not batch:
                    break
                try:
                    self._write_to_db(batch)
                except Exception as exc:
                    logger.error("EventBuffer flush failed: %s", exc)
                    # 写失败的放回队列头部
                    self._push_back(batch)
                    break

    def _push_back(self, batch: list[dict]):
        """将失败的批次放回 Redis 队列头部。"""
        import json
        from memory.short_memory.store import _get_redis
        r = _get_redis()
        # lpush 是头插，需要反转顺序保持原来的时间序
        items = [json.dumps(x, ensure_ascii=False) for x in reversed(batch)]
        r.lpush(self._stm._sync_key, *items)

    def _write_to_db(self, batch: list[dict]):
        """批量写入 PostgreSQL。"""
        if not batch:
            return
        db = get_db_session()
        repo = EventsRecordRepo(db)
        try:
            for item in batch:
                repo.save_message(
                    patient_id=self._user_id,
                    role=item["role"],
                    content=item["content"],
                )
            db.commit()
            logger.info("EventBuffer flushed %d events to PG", len(batch))
        except Exception as exc:
            db.rollback()
            logger.error("EventBuffer write_to_db failed: %s", exc)
            raise

    @property
    def pending_count(self) -> int:
        """同步队列中待写入的消息数。"""
        return self._stm.sync_pending_count()
