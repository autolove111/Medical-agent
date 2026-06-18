"""
短期记忆实时监控 — 浏览器查看内存中的消息列表、summary、长度

用法：
    在 analyze_runtime.py 中注入 memory 后自动启动
    浏览器打开：http://localhost:8002
"""

import sys
import os
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

app = FastAPI(title="短期记忆监控")

# 全局引用，由主程序注入
_memory_system = None


def set_memory(memory_system):
    """主程序调用，注入 MemorySystem 实例"""
    global _memory_system
    _memory_system = memory_system


@app.get("/", response_class=HTMLResponse)
async def index():
    """监控页面"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>短期记忆监控</title>
        <style>
            body { font-family: 'Consolas', monospace; background: #1e1e1e; color: #d4d4d4; padding: 20px; }
            h1 { color: #569cd6; }
            h2 { color: #4ec9b0; margin-top: 24px; }
            .msg { margin: 8px 0; padding: 10px; border-radius: 6px; border-left: 4px solid; }
            .system { background: #1a2332; border-color: #569cd6; }
            .user { background: #1a2e1a; border-color: #6a9955; }
            .assistant { background: #2a2a1a; border-color: #dcdcaa; }
            .tool { background: #2a1a1a; border-color: #f44747; }
            .role { font-weight: bold; margin-right: 8px; }
            .content { white-space: pre-wrap; word-break: break-all; }
            .tool-call { color: #c586c0; margin-left: 20px; }
            .meta { color: #808080; font-size: 12px; }
            .stat { display: inline-block; background: #264f78; color: white; padding: 4px 12px; border-radius: 4px; margin-right: 8px; }
            .header { display: flex; align-items: center; gap: 16px; margin-bottom: 20px; }
            .summary-box { background: #1a1a2e; border: 1px solid #333; border-radius: 8px; padding: 16px; margin: 12px 0; }
            #refresh { background: #264f78; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; }
            #refresh:hover { background: #3a6fa0; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>📦 短期记忆监控</h1>
            <button id="refresh" onclick="load()">刷新</button>
            <span class="meta">每 2 秒自动刷新</span>
        </div>
        <div id="stats"></div>
        <h2>📋 Summary</h2>
        <div id="summary"></div>
        <h2>💬 Messages</h2>
        <div id="messages"></div>

        <script>
            async function load() {
                const res = await fetch('/api/data');
                const data = await res.json();

                // 统计信息
                const stats = document.getElementById('stats');
                stats.innerHTML =
                    '<span class="stat">消息数: ' + data.message_count + '</span>' +
                    '<span class="stat">Summary数: ' + data.summary_count + '</span>' +
                    '<span class="stat">消息长度: ' + data.message_len + '</span>';

                // Summary
                const summaryDiv = document.getElementById('summary');
                summaryDiv.innerHTML = '';
                data.summary.forEach(function(s, i) {
                    const div = document.createElement('div');
                    div.className = 'summary-box';
                    div.innerHTML = '<span class="role">[' + i + '] ' + (s.role || '?') + '</span>' +
                        '<div class="content">' + escapeHtml(s.content || '') + '</div>';
                    summaryDiv.appendChild(div);
                });

                // Messages
                const container = document.getElementById('messages');
                container.innerHTML = '';
                data.messages.forEach(function(msg, i) {
                    const div = document.createElement('div');
                    const role = msg.role || '?';
                    div.className = 'msg ' + role;
                    let html = '<span class="role">[' + i + '] ' + role + '</span>';
                    if (msg.content) {
                        html += '<div class="content">' + escapeHtml(msg.content) + '</div>';
                    }
                    if (msg.tool_calls) {
                        msg.tool_calls.forEach(function(tc) {
                            const fn = tc.function || {};
                            html += '<div class="tool-call">🔧 ' + fn.name + '(' + fn.arguments + ')</div>';
                        });
                    }
                    if (msg.tool_call_id) {
                        html += '<div class="tool-call">← tool_call_id: ' + msg.tool_call_id + '</div>';
                    }
                    div.innerHTML = html;
                    container.appendChild(div);
                });
            }

            function escapeHtml(text) {
                return text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
            }

            setInterval(load, 2000);
            load();
        </script>
    </body>
    </html>
    """


@app.get("/api/data")
async def get_data():
    """获取短期记忆的完整数据"""
    if _memory_system is None:
        return {"error": "MemorySystem 未注入"}
    stm = _memory_system._stm
    return {
        "messages": stm.messages if stm else [],
        "summary": stm.summary if stm else [],
        "message_count": len(stm.messages) if stm else 0,
        "summary_count": len(stm.summary) if stm else 0,
        "message_len": stm.message_len if stm else 0,
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
