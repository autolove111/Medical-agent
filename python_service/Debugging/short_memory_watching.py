"""
短期记忆实时监控 — 浏览器查看内存中的消息列表、summary、长度

用法：
    方式1：随 server.py 自动启动（推荐）
        server.py 的 lifespan 会在后台线程启动本服务
        浏览器打开：http://localhost:8002

    方式2：独立运行
        cd python_service && python Debugging/short_memory_watching.py
"""

import sys
import os
import threading
import uvicorn
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

app = FastAPI(title="短期记忆监控")

# ========== 全局注册表 ==========
# key: (user_id, session_id) -> MemorySystem 实例
_registry: dict[tuple, object] = {}
_registry_lock = threading.Lock()


def register_memory(user_id: str, session_id: str, memory_system):
    """注册 MemorySystem 实例到监控"""
    with _registry_lock:
        _registry[(user_id, session_id)] = memory_system


def unregister_memory(user_id: str, session_id: str):
    """注销"""
    with _registry_lock:
        _registry.pop((user_id, session_id), None)


def get_all_sessions() -> list[dict]:
    """获取所有已注册的会话列表"""
    with _registry_lock:
        return [
            {"user_id": k[0], "session_id": k[1], "has_data": v._stm is not None}
            for k, v in _registry.items()
        ]


def get_memory(user_id: str, session_id: str):
    """获取指定会话的 MemorySystem"""
    with _registry_lock:
        return _registry.get((user_id, session_id))


# ========== 页面 ==========

@app.get("/", response_class=HTMLResponse)
async def index():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>短期记忆监控</title>
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; }
            body { font-family: 'Consolas', 'Courier New', monospace; background: #0d1117; color: #c9d1d9; padding: 20px; min-height: 100vh; }
            h1 { color: #58a6ff; font-size: 22px; }
            h2 { color: #3fb950; margin-top: 20px; font-size: 16px; border-bottom: 1px solid #21262d; padding-bottom: 6px; }
            .header { display: flex; align-items: center; gap: 16px; margin-bottom: 16px; flex-wrap: wrap; }
            .session-picker { display: flex; align-items: center; gap: 8px; }
            .session-picker select { background: #161b22; color: #c9d1d9; border: 1px solid #30363d; padding: 6px 10px; border-radius: 6px; font-family: inherit; font-size: 13px; }
            .stat { display: inline-block; background: #1f6feb; color: white; padding: 4px 14px; border-radius: 12px; margin-right: 8px; font-size: 13px; }
            .stat.warn { background: #d29922; }
            .msg { margin: 6px 0; padding: 10px 14px; border-radius: 6px; border-left: 4px solid; font-size: 13px; line-height: 1.5; }
            .system { background: #0d1d30; border-color: #58a6ff; }
            .user { background: #0d2818; border-color: #3fb950; }
            .assistant { background: #1d1b0f; border-color: #d29922; }
            .tool { background: #1f0d0d; border-color: #f85149; }
            .role { font-weight: bold; margin-right: 8px; font-size: 12px; text-transform: uppercase; }
            .role.system { color: #58a6ff; }
            .role.user { color: #3fb950; }
            .role.assistant { color: #d29922; }
            .role.tool { color: #f85149; }
            .content { white-space: pre-wrap; word-break: break-all; margin-top: 4px; }
            .tool-call { color: #bc8cff; margin-left: 20px; font-size: 12px; }
            .meta { color: #484f58; font-size: 12px; }
            .summary-box { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 14px; margin: 8px 0; font-size: 13px; line-height: 1.5; }
            .empty { color: #484f58; font-style: italic; padding: 20px; text-align: center; }
            #refresh { background: #238636; color: white; border: none; padding: 7px 16px; border-radius: 6px; cursor: pointer; font-family: inherit; font-size: 13px; }
            #refresh:hover { background: #2ea043; }
            .badge { display: inline-block; background: #30363d; color: #8b949e; padding: 2px 8px; border-radius: 10px; font-size: 11px; margin-left: 4px; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>📦 短期记忆监控</h1>
            <div class="session-picker">
                <span class="meta">会话:</span>
                <select id="sessionSelect" onchange="onSessionChange()"></select>
            </div>
            <button id="refresh" onclick="load()">刷新</button>
            <span class="meta" id="status">加载中...</span>
        </div>
        <div id="stats"></div>
        <h2>📋 Summary</h2>
        <div id="summary"></div>
        <h2>💬 Messages</h2>
        <div id="messages"></div>

        <script>
            let currentUser = '';
            let currentSession = '';
            let sessions = [];

            async function loadSessions() {
                const res = await fetch('/api/sessions');
                sessions = await res.json();
                const sel = document.getElementById('sessionSelect');
                const prev = sel.value;
                sel.innerHTML = '';
                if (sessions.length === 0) {
                    sel.innerHTML = '<option value="">无活跃会话</option>';
                    return;
                }
                sessions.forEach(function(s, i) {
                    const opt = document.createElement('option');
                    opt.value = i;
                    opt.textContent = s.user_id + '/' + s.session_id.substring(0, 8) + '...';
                    sel.appendChild(opt);
                });
                // 恢复之前的选中
                if (prev && prev < sessions.length) {
                    sel.value = prev;
                }
                onSessionChange();
            }

            function onSessionChange() {
                const sel = document.getElementById('sessionSelect');
                const idx = parseInt(sel.value);
                if (isNaN(idx) || !sessions[idx]) return;
                currentUser = sessions[idx].user_id;
                currentSession = sessions[idx].session_id;
                load();
            }

            async function load() {
                if (!currentUser || !currentSession) {
                    document.getElementById('stats').innerHTML = '';
                    document.getElementById('summary').innerHTML = '<div class="empty">请先选择一个会话</div>';
                    document.getElementById('messages').innerHTML = '';
                    document.getElementById('status').textContent = '等待选择会话...';
                    return;
                }

                try {
                    const res = await fetch('/api/data?user_id=' + encodeURIComponent(currentUser) + '&session_id=' + encodeURIComponent(currentSession));
                    const data = await res.json();

                    if (data.error) {
                        document.getElementById('status').textContent = data.error;
                        return;
                    }

                    document.getElementById('status').textContent = '自动刷新中 · ' + new Date().toLocaleTimeString();

                    // 统计
                    const pct = data.message_len > 0 ? Math.min(100, Math.round(data.message_len / 500)) : 0;
                    const warnClass = pct > 80 ? ' warn' : '';
                    document.getElementById('stats').innerHTML =
                        '<span class="stat">消息: ' + data.message_count + '</span>' +
                        '<span class="stat">摘要: ' + data.summary_count + '</span>' +
                        '<span class="stat' + warnClass + '">长度: ' + data.message_len + '</span>' +
                        '<span class="badge">' + currentUser + '</span>';

                    // Summary
                    const summaryDiv = document.getElementById('summary');
                    if (data.summary.length === 0) {
                        summaryDiv.innerHTML = '<div class="empty">暂无摘要</div>';
                    } else {
                        summaryDiv.innerHTML = '';
                        data.summary.forEach(function(s, i) {
                            const div = document.createElement('div');
                            div.className = 'summary-box';
                            div.innerHTML = '<span class="role ' + (s.role || 'system') + '">[' + i + '] ' + (s.role || '?') + '</span>' +
                                '<div class="content">' + escapeHtml(s.content || '') + '</div>';
                            summaryDiv.appendChild(div);
                        });
                    }

                    // Messages
                    const container = document.getElementById('messages');
                    if (data.messages.length === 0) {
                        container.innerHTML = '<div class="empty">暂无消息</div>';
                    } else {
                        container.innerHTML = '';
                        data.messages.forEach(function(msg, i) {
                            const div = document.createElement('div');
                            const role = msg.role || '?';
                            div.className = 'msg ' + role;
                            let html = '<span class="role ' + role + '">[' + i + '] ' + role + '</span>';
                            if (msg.content) {
                                html += '<div class="content">' + escapeHtml(msg.content) + '</div>';
                            }
                            if (msg.tool_calls) {
                                msg.tool_calls.forEach(function(tc) {
                                    const fn = tc.function || {};
                                    html += '<div class="tool-call">🔧 ' + escapeHtml(fn.name || '') + '(' + escapeHtml(fn.arguments || '') + ')</div>';
                                });
                            }
                            if (msg.tool_call_id) {
                                html += '<div class="tool-call">← tool_call_id: ' + escapeHtml(msg.tool_call_id) + '</div>';
                            }
                            div.innerHTML = html;
                            container.appendChild(div);
                        });
                    }
                } catch (e) {
                    document.getElementById('status').textContent = '请求失败: ' + e.message;
                }
            }

            function escapeHtml(text) {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }

            // 启动
            loadSessions();
            setInterval(loadSessions, 5000);  // 每5秒刷新会话列表
            setInterval(load, 2000);           // 每2秒刷新数据
        </script>
    </body>
    </html>
    """


# ========== API ==========

@app.get("/api/sessions")
async def api_sessions():
    """返回所有已注册的会话列表"""
    return get_all_sessions()


@app.get("/api/data")
async def api_data(
    user_id: str = Query(default="default"),
    session_id: str = Query(default="default"),
):
    """获取指定会话的短期记忆数据"""
    mem = get_memory(user_id, session_id)
    if mem is None:
        return {"error": f"未找到会话 {user_id}/{session_id[:8]}..."}
    stm = mem._stm
    if stm is None:
        return {"messages": [], "summary": [], "message_count": 0, "summary_count": 0, "message_len": 0}
    return {
        "messages": stm.messages,
        "summary": stm.summary,
        "message_count": len(stm.messages),
        "summary_count": len(stm.summary),
        "message_len": stm.message_len,
    }


# ========== 启动 ==========

def start_monitor_server(host: str = "0.0.0.0", port: int = 8002):
    """在后台线程启动监控服务"""
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True, name="memory-monitor")
    thread.start()
    return thread


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)
