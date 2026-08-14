"""
Redis 数据查看器 - 查看短期记忆和队列状态
"""

import json
import sys
import io
import redis
from datetime import datetime

# Fix encoding on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Redis 连接（根据你的配置修改）
r = redis.Redis(
    host='localhost',
    port=6379,
    password='',  # 如果有密码填这里
    decode_responses=True
)

def view_short_memory():
    """查看所有短期记忆"""
    print("\n" + "="*60)
    print("📚 短期记忆 (Short-Term Memory)")
    print("="*60)

    # 搜索所有 stm keys
    stm_keys = r.keys("medlab:stm:*")
    if not stm_keys:
        print("  (空)")
        return

    for key in sorted(stm_keys):
        print(f"\n🔑 {key}")
        data = r.hgetall(key)
        for field, value in data.items():
            if field in ['messages', 'summary']:
                # 格式化 JSON
                try:
                    parsed = json.loads(value)
                    print(f"  {field}: [{len(parsed)} items]")
                    for i, msg in enumerate(parsed[:3]):  # 只显示前3条
                        role = msg.get('role', '?')
                        content = str(msg.get('content', ''))[:80]
                        print(f"    [{i}] {role}: {content}...")
                    if len(parsed) > 3:
                        print(f"    ... 还有 {len(parsed)-3} 条消息")
                except:
                    print(f"  {field}: {value[:100]}")
            else:
                print(f"  {field}: {value}")

def view_queues():
    """查看所有队列"""
    print("\n" + "="*60)
    print("📦 任务队列 (Queues)")
    print("="*60)

    queues = {
        "medlab:task_queue": "主任务队列",
        "medlab:llm_queue": "LLM队列",
        "medlab:rag_queue": "RAG队列",
        "medlab:dispatch_queue": "调度队列"
    }

    for queue_name, desc in queues.items():
        length = r.llen(queue_name)
        print(f"\n📋 {desc} ({queue_name})")
        print(f"   长度: {length}")

        if length > 0:
            # 显示前3条
            items = r.lrange(queue_name, 0, min(2, length-1))
            for i, item in enumerate(items):
                try:
                    data = json.loads(item)
                    print(f"   [{i}] {json.dumps(data, ensure_ascii=False, indent=2)[:200]}")
                except:
                    print(f"   [{i}] {item[:200]}")
            if length > 3:
                print(f"   ... 还有 {length-3} 条")

def view_task_states():
    """查看所有任务状态"""
    print("\n" + "="*60)
    print("📊 任务状态 (Task States)")
    print("="*60)

    task_keys = r.keys("medlab:task:*")
    # 排除队列 key
    task_keys = [k for k in task_keys if ':' not in k.split('medlab:task:')[1]]

    if not task_keys:
        print("  (空)")
        return

    for key in sorted(task_keys)[:10]:  # 最多显示10个
        data = r.hgetall(key)
        task_id = data.get('task_id', key.split(':')[-1][:8])
        status = data.get('status', '?')
        query = data.get('query', '')[:50]
        print(f"  [{status}] {task_id}... | {query}...")

def view_all_keys():
    """查看所有 medlab 相关的 key"""
    print("\n" + "="*60)
    print("🗂️  所有 MedLab Keys")
    print("="*60)

    all_keys = r.keys("medlab:*")
    # 按类型分组
    stm = [k for k in all_keys if 'stm' in k]
    tasks = [k for k in all_keys if 'task:' in k and 'task_' not in k]
    queues = [k for k in all_keys if 'queue' in k or 'dispatch' in k]
    cache = [k for k in all_keys if 'cache' in k]
    other = [k for k in all_keys if k not in stm + tasks + queues + cache]

    print(f"  短期记忆: {len(stm)} 个")
    print(f"  任务状态: {len(tasks)} 个")
    print(f"  队列: {len(queues)} 个")
    print(f"  缓存: {len(cache)} 个")
    print(f"  其他: {len(other)} 个")

    if other:
        print("\n  其他 keys:")
        for k in sorted(other)[:10]:
            print(f"    {k}")

if __name__ == "__main__":
    print("🔍 MedLab Redis 数据查看器")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        r.ping()
        print("✅ Redis 连接成功")
    except:
        print("❌ Redis 连接失败，请检查配置")
        exit(1)

    view_all_keys()
    view_short_memory()
    view_queues()
    view_task_states()

    print("\n" + "="*60)
    print("💡 提示: 可以在 Redis 管理工具中直接查看这些 key")
    print("="*60)
