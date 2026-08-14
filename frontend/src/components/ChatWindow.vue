<template>
  <div class="chat-container">
    <div class="header-bar">
      <div class="header-left">
        <h1>MedLabAgent</h1>
        <span class="header-version">v0.2</span>
      </div>
      <div class="header-right">
        <div v-if="currentUser" class="user-info">
          <button class="user-name-btn">
            👤 {{ currentUser.realName }}
          </button>
          <button @click="handleLogout" class="logout-btn">登出</button>
        </div>
      </div>
    </div>

    <div class="chat-body">
      <!-- 最左侧：会话列表 -->
      <aside class="session-panel">
        <button class="new-session-btn" @click="createSession">＋ 新建对话</button>
        <div class="session-list">
          <div
            v-for="s in sessions"
            :key="s.id"
            :class="['session-item', { active: s.id === currentSessionId }]"
            @click="switchSession(s.id)"
          >
            <span class="session-label">{{ s.label }}</span>
            <button class="session-delete" @click.stop="deleteSession(s.id)" title="删除">✕</button>
          </div>
        </div>
      </aside>

      <!-- 中间：指标面板（上传报告后显示） -->
      <aside v-if="reportIndicators.length > 0" class="side-panel">
        <IndicatorPanel
          :indicators="reportIndicators"
          :reportDate="reportDate"
        />
        <button class="close-panel-btn" @click="reportIndicators = []">✕ 关闭</button>
      </aside>

      <!-- 右侧：聊天窗口 -->
      <div class="chat-window">
        <div ref="messagesAreaRef" class="messages-area">
          <div v-if="messages.length === 0" class="empty-state">
            <h2>欢迎使用 MedLabAgent</h2>
            <p>医疗检验报告智能解读助手</p>
            <p class="user-greeter">
              {{ currentUser ? `Hi, ${currentUser.realName}!` : "" }}
            </p>
            <p class="hint-text">上传化验单开始解读，或直接输入问题咨询</p>
          </div>

          <div v-for="msg in messages" :key="msg.id">
            <ChatMessage :message="msg" />
            <!-- Phase 7: 来源引用面板（模型回复后展示） -->
            <div
              v-if="msg.role === 'assistant' && msg.sources && msg.sources.length > 0 && !isLoading"
              class="sources-panel"
            >
              <div class="sources-header" @click="msg.showSources = !msg.showSources">
                📚 参考来源 ({{ msg.sources.length }}) {{ msg.showSources ? '▲' : '▼' }}
              </div>
              <div v-if="msg.showSources" class="sources-list">
                <div v-for="(s, i) in msg.sources" :key="i" class="source-item">
                  <span class="source-name">{{ s.source || s }}</span>
                  <span class="source-section" v-if="s.section">§ {{ s.section }}</span>
                  <span class="source-category" v-if="s.category">{{ s.category }}</span>
                </div>
              </div>
            </div>
            <!-- 原有的对话确认按钮 -->
            <div
              v-if="msg.role === 'assistant' && msg.content && !isLoading && msg.isMedical && !msg.confirmed && !msg.rejected"
              class="confirm-bar"
            >
              <span class="confirm-hint">是否将此次诊断记录到您的病历？</span>
              <button @click="showSaveDialog(msg)" class="confirm-btn">✅ 记录到病历</button>
              <button @click="msg.rejected = true" class="reject-btn">❌ 不记录</button>
            </div>
            <div v-if="msg.confirmed" class="confirm-bar confirmed">
              <span>✅ 已记录到病历</span>
            </div>
          </div>

          <div v-if="isLoading && !isStreaming" class="message assistant">
            <div class="message-content"><div class="spinner"></div></div>
          </div>
        </div>

        <div v-if="error" class="error-message">{{ error }}</div>

        <!-- 推荐问题按钮 -->
        <div v-if="suggestedQuestions.length > 0" class="suggested-questions">
          <div class="suggested-label">💡 你可能还想了解：</div>
          <div class="suggested-list">
            <button
              v-for="(q, i) in suggestedQuestions"
              :key="i"
              class="suggested-btn"
              @click="sendMessage(q)"
              :disabled="isLoading"
            >
              {{ q }}
            </button>
          </div>
        </div>

        <!-- Phase 7: 输入区集成 ReportUpload -->
        <div class="input-area">
          <ReportUpload @uploaded="onReportUploaded" :session-id="currentSessionId" />
          <input
            v-model="userInput"
            type="text"
            placeholder="输入您的问题..."
            @keyup.enter="sendMessage"
            :disabled="isLoading"
          />
          <button @click="sendMessage" :disabled="isLoading || !userInput">
            {{ isLoading ? "..." : "发送" }}
          </button>
        </div>
      </div>
    </div>

    <!-- Phase 7: 全局免责声明 -->
    <DisclaimerBar />

    <!-- 病历保存对话框 -->
    <div v-if="showMedicalDialog" class="dialog-overlay">
      <div class="dialog-box">
        <h3>📋 记录到病历</h3>
        <div class="dialog-field">
          <label>疾病/症状：</label>
          <input v-model="medicalForm.disease" type="text" placeholder="例如：急性扁桃体炎、高热" />
        </div>
        <div class="dialog-field">
          <label>药物过敏：</label>
          <input v-model="medicalForm.drugAllergy" type="text" placeholder="例如：青霉素（无则留空）" />
        </div>
        <div class="dialog-field">
          <label>当前状态：</label>
          <select v-model="medicalForm.status">
            <option value="未康复">未康复</option>
            <option value="已康复">已康复</option>
            <option value="待观察">待观察</option>
          </select>
        </div>
        <div class="dialog-actions">
          <button @click="confirmSave" class="confirm-btn">确认保存</button>
          <button @click="cancelSave" class="reject-btn">取消</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, onBeforeUnmount, computed, nextTick, watch } from "vue";
import ChatMessage from "./ChatMessage.vue";
import IndicatorPanel from "./IndicatorPanel.vue";
import ReportUpload from "./ReportUpload.vue";
import DisclaimerBar from "./DisclaimerBar.vue";
import { useChatStore } from "../stores/chatStore";
import { useAuthStore } from "../stores/authStore";
import ApiService from "../services/ApiService";
import wsService from "../services/wsService";
import { useRouter } from "vue-router";

// 修复：消息 ID 计数器，避免冲突
let msgIdCounter = 0;
function nextMsgId() {
  return `msg_${++msgIdCounter}_${Date.now()}`;
}

export default {
  name: "ChatWindow",
  components: {
    ChatMessage,
    IndicatorPanel,
    ReportUpload,
    DisclaimerBar,
  },
  setup() {
    const chatStore = useChatStore();
    const authStore = useAuthStore();
    const router = useRouter();
    const userInput = ref("");
    const isLoading = ref(false);
    const isStreaming = ref(false);
    const error = ref(null);

    // 修复：模板 ref
    const messagesAreaRef = ref(null);

    // Phase 7: 报告状态
    const reportIndicators = ref([]);
    const reportDate = ref("");
    const currentReportId = ref(null);
    const suggestedQuestions = ref([]);

    // Session 管理
    function generateSessionId() {
      const id = "sess_" + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
      localStorage.setItem("session_id", id);
      return id;
    }
    const currentSessionId = ref(localStorage.getItem("session_id") || generateSessionId());
    const sessions = ref([{ id: currentSessionId.value, label: "对话 1", createdAt: Date.now() }]);
    let sessionCounter = 1;

    function createSession() {
      sessionCounter++;
      const newId = generateSessionId();
      sessions.value.unshift({ id: newId, label: `对话 ${sessionCounter}`, createdAt: Date.now() });
      currentSessionId.value = newId;
      chatStore.clearMessages();
      reportIndicators.value = [];
      currentReportId.value = null;
    }

    async function switchSession(sessionId) {
      if (sessionId === currentSessionId.value) return;
      currentSessionId.value = sessionId;
      localStorage.setItem("session_id", sessionId);
      chatStore.clearMessages();
      reportIndicators.value = [];
      currentReportId.value = null;

      // 加载目标会话的历史
      try {
        const res = await ApiService.get("/chat/history", {
          params: { user_id: authStore.user?.idNumber || "default", session_id: sessionId },
        });
        const history = res.data?.data?.messages;
        if (history && history.length > 0) {
          for (const msg of history) {
            if (msg.role === "user" || msg.role === "assistant") {
              chatStore.addMessage({
                role: msg.role,
                content: msg.content || "",
                reasoningSteps: [],
              });
            }
          }
        }
      } catch (e) {
        console.warn("加载对话历史失败:", e);
      }
    }

    function deleteSession(sessionId) {
      const idx = sessions.value.findIndex(s => s.id === sessionId);
      if (idx === -1) return;
      sessions.value.splice(idx, 1);
      if (currentSessionId.value === sessionId) {
        if (sessions.value.length > 0) {
          switchSession(sessions.value[0].id);
        } else {
          createSession();
        }
      }
    }
    const showMedicalDialog = ref(false);
    const currentSaveMsg = ref(null);
    const medicalForm = ref({ disease: "", status: "未康复" });

    const messages = computed(() => chatStore.messages);
    const currentUser = computed(() => authStore.user);

    // 修复：使用模板 ref 滚动到底部
    const scrollToBottom = async () => {
      await nextTick();
      const container = messagesAreaRef.value;
      if (container) {
        container.scrollTop = container.scrollHeight;
      }
    };

    // 页面关闭/刷新时只清理本地状态，不清后端会话（保留快照供下次加载）
    function handlePageClose() {
      // 不再发送 logout beacon，让后端会话和快照保持不变
    }

    // 修复：保存事件回调引用，以便在组件卸载时移除
    const onThought = (data) => {
      const last = chatStore.messages[chatStore.messages.length - 1];
      if (last && last.role === "assistant") {
        if (!last.reasoningSteps) last.reasoningSteps = [];
        last.reasoningSteps.push({
          type: "thought",
          step: data.step,
          thinking: data.thinking,
          content: data.content,
        });
        scrollToBottom();
      }
    };

    const onToolCall = (data) => {
      const last = chatStore.messages[chatStore.messages.length - 1];
      if (last && last.role === "assistant") {
        if (!last.reasoningSteps) last.reasoningSteps = [];
        last.reasoningSteps.push({
          type: "tool_call", step: data.step, name: data.name, args: data.args,
        });
        scrollToBottom();
      }
    };

    const onToolResult = (data) => {
      const last = chatStore.messages[chatStore.messages.length - 1];
      if (last && last.role === "assistant") {
        if (!last.reasoningSteps) last.reasoningSteps = [];
        last.reasoningSteps.push({
          type: "observation", step: data.step, name: data.name, result: data.result,
        });
        scrollToBottom();
      }
    };

    const onFinalAnswer = (data) => {
      const last = chatStore.messages[chatStore.messages.length - 1];
      if (last && last.role === "assistant") {
        last.content = data.answer;
        isLoading.value = false;
        isStreaming.value = false;
        scrollToBottom();
      }
    };

    const onTaskResult = (data) => {
      isLoading.value = false;
      isStreaming.value = false;
      if (data.status === "failed") {
        error.value = "服务响应异常: " + (data.error || "未知错误");
      }
    };

    const onWsError = (data) => {
      isLoading.value = false;
      isStreaming.value = false;
      error.value = "WebSocket 错误";
    };

    const onDisconnected = () => {
      isLoading.value = false;
      isStreaming.value = false;
    };

    const onSuggestedQuestions = (data) => {
      if (data.questions && data.questions.length > 0) {
        suggestedQuestions.value = data.questions;
      }
    };

    onMounted(async () => {
      // 修复：await restoreAuth()，确保认证状态恢复完成
      if (!authStore.isLoggedIn && localStorage.getItem("token")) {
        await authStore.restoreAuth();
      }

      if (!authStore.isLoggedIn) {
        router.push("/login");
        return;
      }

      // 建立 WebSocket 连接
      const userId = authStore.user?.idNumber || "default";
      wsService.connect(userId);

      // 注册 WebSocket 事件处理
      wsService.on("thought", onThought);
      wsService.on("tool_call", onToolCall);
      wsService.on("tool_result", onToolResult);
      wsService.on("final_answer", onFinalAnswer);
      wsService.on("task_result", onTaskResult);
      wsService.on("error", onWsError);
      wsService.on("disconnected", onDisconnected);
      wsService.on("suggested_questions", onSuggestedQuestions);

      // 从后端快照恢复对话历史
      try {
        const res = await ApiService.get("/chat/history", {
          params: { user_id: userId, session_id: currentSessionId.value },
        });
        const history = res.data?.data?.messages;
        if (history && history.length > 0) {
          for (const msg of history) {
            // 只加载用户和助手消息，跳过工具调用等中间消息
            if (msg.role === "user" || msg.role === "assistant") {
              chatStore.addMessage({
                role: msg.role,
                content: msg.content || "",
                reasoningSteps: [],
              });
            }
          }
        }
      } catch (e) {
        console.warn("加载对话历史失败:", e);
      }

      window.addEventListener("beforeunload", handlePageClose);
    });

    onBeforeUnmount(() => {
      window.removeEventListener("beforeunload", handlePageClose);
      // 修复：移除所有 WebSocket 事件监听器
      wsService.off("thought", onThought);
      wsService.off("tool_call", onToolCall);
      wsService.off("tool_result", onToolResult);
      wsService.off("final_answer", onFinalAnswer);
      wsService.off("task_result", onTaskResult);
      wsService.off("error", onWsError);
      wsService.off("disconnected", onDisconnected);
      wsService.off("suggested_questions", onSuggestedQuestions);
      wsService.disconnect();
    });

    async function sendMessage(questionText) {
      // 兼容：推荐问题传入字符串，发送按钮传入 MouseEvent
      const text = typeof questionText === 'string' ? questionText : userInput.value;
      if (!text || !text.trim()) return;

      const userMessage = text;

      // 1. 添加用户消息
      chatStore.addMessage({
        role: "user",
        content: userMessage,
        id: nextMsgId(),
        timestamp: new Date(),
      });

      userInput.value = "";
      suggestedQuestions.value = [];
      isLoading.value = true;
      isStreaming.value = false;
      error.value = null;
      scrollToBottom();

      // 2. 预创建空的助手消息（推理步骤在这里填充）
      chatStore.addMessage({
        role: "assistant",
        content: "",
        reasoningSteps: [],
        id: nextMsgId(),
        timestamp: new Date(),
      });
      scrollToBottom();

      // 3. 通过 WebSocket 发送
      const sent = wsService.ask(userMessage, currentSessionId.value);
      if (!sent) {
        error.value = "WebSocket 未连接，请刷新页面重试";
        isLoading.value = false;
      }
    }

    async function sendOcrMessage(query, ocrResult) {
      if (!query.trim() || !ocrResult) return;

      chatStore.addMessage({
        role: "user",
        content: query,
        id: nextMsgId(),
        timestamp: new Date(),
      });

      isLoading.value = true;
      isStreaming.value = false;
      error.value = null;
      scrollToBottom();

      chatStore.addMessage({
        role: "assistant",
        content: "",
        id: nextMsgId(),
        timestamp: new Date(),
      });
      scrollToBottom();

      try {
        await ApiService.streamChat(
          {
            query,
            ocr_result: ocrResult,
          },
          (chunk) => {
            isStreaming.value = true;
            const lastIndex = chatStore.messages.length - 1;
            const msg = chatStore.messages[lastIndex];
            if (msg && msg.role === "assistant") {
              msg.content += chunk;
              scrollToBottom();
            }
          },
          (streamErr) => {
            console.error("Stream error:", streamErr);
          },
          (metadata) => {
            const lastMsg = chatStore.messages[chatStore.messages.length - 1];
            if (lastMsg && lastMsg.role === "assistant" && metadata) {
              lastMsg.isMedical = metadata.isMedical || false;
              lastMsg.extractedDiseases = metadata.diseases || "";
              lastMsg.extractedDrugAllergy = metadata.drugAllergies || "";
              lastMsg.content = lastMsg.content
                .replace(/\n?\[META\|[^\]]*\]/g, "")
                .trimEnd();
            }
          },
        );
      } catch (err) {
        // 修复：错误消息使用正确的中文
        error.value = "通信失败: " + err.message;
        const lastIndex = chatStore.messages.length - 1;
        const msg = chatStore.messages[lastIndex];
        if (msg && msg.role === "assistant") {
          msg.content = "抱歉，连接服务时出错了。";
        }
      } finally {
        isLoading.value = false;
        isStreaming.value = false;
      }
    }

    // Phase 7: 报告上传完成回调
    function onReportUploaded(result) {
      if (result && result.indicators) {
        reportIndicators.value = result.indicators
        reportDate.value = result.report_date || new Date().toISOString().slice(0, 10)
        currentReportId.value = result.report_id

        // 展示原始化验单 Markdown（渲染表格等）
        if (result.raw_markdown) {
          chatStore.addMessage({
            role: "user",
            content: "📋 **化验单识别结果：**\n\n" + result.raw_markdown,
            id: Date.now(),
            timestamp: new Date(),
          })
        }

        // 发送解读请求
        chatStore.addMessage({
          role: "user",
          content: "请对以上化验报告进行详细解读",
          id: Date.now() + 1,
          timestamp: new Date(),
        })

        // 预创建空的助手消息
        chatStore.addMessage({
          role: "assistant",
          content: "",
          reasoningSteps: [],
          id: Date.now() + 2,
          timestamp: new Date(),
        })

        isLoading.value = true
        scrollToBottom()

        // 通过 WebSocket 发送，task_type="report" 走 Plan 链路
        const sent = wsService.ask("请对以上化验报告进行详细解读", currentSessionId.value, "report")
        if (!sent) {
          error.value = "WebSocket 未连接，请刷新页面重试"
          isLoading.value = false
        }
      }
    }

    function uploadFile() {
      fileInput.value.click();
    }

    async function handleFileUpload(event) {
      const file = event.target.files[0];
      if (!file) return;

      isLoading.value = true;
      error.value = null;

      try {
        const response = await ApiService.uploadReport(file);
        if (response.status === "success") {
          const ocrResult = await ApiService.analyzeVision(response.filePath);
          await sendOcrMessage("请分析这张化验单", ocrResult);
        } else {
          error.value = response.message || "上传失败";
        }
      } catch (err) {
        error.value = "上传失败: " + err.message;
      } finally {
        isLoading.value = false;
        event.target.value = "";
      }
    }

    async function handleLogout() {
      await authStore.logout();
      chatStore.clearMessages();
      router.push("/login");
    }

    function showSaveDialog(msg) {
      currentSaveMsg.value = msg;
      medicalForm.value = {
        disease: msg.extractedDiseases || "",
        drugAllergy: msg.extractedDrugAllergy || "",
        status: "未康复",
      };
      showMedicalDialog.value = true;
    }

    async function confirmSave() {
      if (
        !medicalForm.value.disease.trim() &&
        !medicalForm.value.drugAllergy.trim()
      )
        return;
      try {
        if (medicalForm.value.disease.trim()) {
          await ApiService.appendMedicalHistory(
            medicalForm.value.disease,
            medicalForm.value.status,
          );
        }
        if (medicalForm.value.drugAllergy.trim()) {
          await ApiService.updateDrugAllergy(medicalForm.value.drugAllergy);
        }
        if (currentSaveMsg.value) {
          currentSaveMsg.value.confirmed = true;
        }
      } catch (err) {
        error.value = "保存病历失败: " + err.message;
      } finally {
        showMedicalDialog.value = false;
        currentSaveMsg.value = null;
      }
    }

    function cancelSave() {
      showMedicalDialog.value = false;
      currentSaveMsg.value = null;
    }

    return {
      userInput, isLoading, isStreaming, error, messages, currentUser,
      showMedicalDialog, medicalForm,
      // 修复：返回 messagesAreaRef
      messagesAreaRef,
      // Session 管理
      sessions, currentSessionId, createSession, switchSession, deleteSession,
      // Phase 7
      reportIndicators, reportDate, currentReportId, suggestedQuestions,
      onReportUploaded,
      // existing
      sendMessage, sendOcrMessage, handleFileUpload,
      handleLogout,
      showSaveDialog, confirmSave, cancelSave,
    };
  },
};
</script>

<style scoped>
.chat-container {
  display: flex; flex-direction: column; height: 100%; width: 100%;
  background: white;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}

/* Phase 7: 左右分栏布局 */
.chat-body { display: flex; flex: 1; overflow: hidden; min-height: 0; }

/* Session 列表面板 */
.session-panel {
  width: 200px; flex-shrink: 0; display: flex; flex-direction: column;
  background: #f5f5f5; border-right: 1px solid #e0e0e0; overflow: hidden;
}
.new-session-btn {
  margin: 12px; padding: 10px; background: #667eea; color: white; border: none;
  border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 600;
  transition: background 0.2s;
}
.new-session-btn:hover { background: #764ba2; }
.session-list { flex: 1; overflow-y: auto; padding: 0 8px; }
.session-item {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 12px; margin-bottom: 4px; border-radius: 8px;
  cursor: pointer; transition: background 0.2s; font-size: 14px; color: #333;
}
.session-item:hover { background: #e8e8e8; }
.session-item.active { background: #667eea; color: white; }
.session-item.active .session-delete { color: rgba(255,255,255,0.7); }
.session-item.active .session-delete:hover { color: white; }
.session-label { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.session-delete {
  background: none; border: none; color: #999; cursor: pointer; font-size: 12px;
  padding: 2px 6px; border-radius: 4px; opacity: 0; transition: opacity 0.2s;
}
.session-item:hover .session-delete { opacity: 1; }
.session-delete:hover { background: rgba(0,0,0,0.1); }

.side-panel {
  width: 340px; flex-shrink: 0; padding: 12px; border-right: 1px solid #eee;
  overflow-y: auto; background: #fafafa; position: relative;
}
.close-panel-btn {
  position: absolute; top: 8px; right: 8px; background: #eee; border: none;
  padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: 12px;
}

/* Phase 7: 来源引用面板 */
.sources-panel { margin: 4px 0 8px 40px; }
.sources-header {
  font-size: 13px; color: #667eea; cursor: pointer; padding: 4px 8px;
  background: #f0f2ff; border-radius: 6px; display: inline-block;
}
.sources-list { margin-top: 6px; }
.source-item {
  display: flex; gap: 8px; align-items: center; padding: 4px 10px;
  font-size: 12px; background: #fafafa; border-radius: 4px; margin-bottom: 3px;
}
.source-name { font-weight: 600; color: #333; }
.source-section { color: #667eea; }
.source-category {
  margin-left: auto; font-size: 10px; padding: 1px 6px;
  background: #eee; border-radius: 8px; color: #888;
}

.header-version { font-size: 12px; color: rgba(255,255,255,0.6); margin-left: 10px; }
.hint-text { font-size: 14px; color: #bbb; margin-top: 8px; }

.header-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 2rem;
  height: 60px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.header-left h1 {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 20px;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 15px;
  font-size: 14px;
}

.user-name-btn {
  background: transparent;
  border: none;
  color: white;
  font-size: 14px;
  cursor: pointer;
  padding: 0;
}
.user-name-btn:hover {
  text-decoration: underline;
}
.user-name-btn {
  padding: 8px 16px;
  background: rgba(255, 255, 255, 0.2);
  color: white;
  border: 1px solid rgba(255, 255, 255, 0.4);
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.3s ease;
}
.user-name-btn:hover {
  background: rgba(255, 255, 255, 0.3);
  transform: translateY(-1px);
}
.logout-btn {
  padding: 8px 16px;
  background: rgba(255, 255, 255, 0.2);
  color: white;
  border: 1px solid rgba(255, 255, 255, 0.4);
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.3s ease;
}

.logout-btn:hover {
  background: rgba(255, 255, 255, 0.3);
  transform: translateY(-1px);
}

.chat-window {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow: hidden;
}

.messages-area {
  flex: 1;
  overflow-y: auto;
  padding: 2rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #999;
}

.empty-state h2 {
  font-size: 2rem;
  margin-bottom: 0.5rem;
  color: #667eea;
}

.user-greeter {
  font-size: 16px;
  margin-top: 1rem;
  color: #667eea;
}

.message {
  display: flex;
  margin-bottom: 1rem;
}

.message.user {
  justify-content: flex-end;
}

.message.assistant {
  justify-content: flex-start;
}

.message-content {
  max-width: 70%;
  padding: 0.8rem 1.2rem;
  border-radius: 12px;
  word-wrap: break-word;
  line-height: 1.5;
}

.message.user .message-content {
  background-color: #667eea;
  color: white;
}

.message.assistant .message-content {
  background-color: #e8e8e8;
  color: #333;
}

.spinner {
  display: inline-block;
  width: 20px;
  height: 20px;
  border: 3px solid rgba(0, 0, 0, 0.1);
  border-radius: 50%;
  border-top-color: #667eea;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.error-message {
  padding: 1rem;
  background-color: #fee;
  color: #c33;
  border: 1px solid #fcc;
  margin: 0 1rem;
  border-radius: 4px;
}

.input-area {
  display: flex;
  gap: 0.8rem;
  padding: 1.5rem;
  border-top: 1px solid #eee;
  background: #fafafa;
}

.input-area input {
  flex: 1;
  padding: 0.8rem 1rem;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 1rem;
  font-family: inherit;
}

.input-area input:focus {
  outline: none;
  border-color: #667eea;
  box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
}

.input-area button {
  padding: 0.8rem 1.5rem;
  background: #667eea;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 600;
  transition: background 0.3s;
}

.input-area button:hover:not(:disabled) {
  background: #764ba2;
}

.input-area button:disabled {
  background: #ccc;
  cursor: not-allowed;
}

@media (max-width: 768px) {
  .message-content {
    max-width: 85%;
  }

  .input-area {
    flex-wrap: wrap;
  }

  .input-area input {
    min-width: 100%;
  }
}

/* 确认栏 */
.confirm-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  margin-top: 4px;
  font-size: 13px;
  color: #666;
}

.confirm-bar.confirmed {
  color: #2e7d32;
  font-weight: 500;
}

.confirm-hint {
  margin-right: 4px;
}

.confirm-btn {
  padding: 4px 12px;
  background: #4caf50;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
}

.confirm-btn:hover {
  background: #388e3c;
}

.reject-btn {
  padding: 4px 12px;
  background: #eee;
  color: #666;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
}

.reject-btn:hover {
  background: #ddd;
}

/* 对话框 */
.dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.dialog-box {
  background: white;
  border-radius: 12px;
  padding: 24px;
  width: 380px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
}

.dialog-box h3 {
  margin: 0 0 16px;
  font-size: 18px;
}

.dialog-field {
  margin-bottom: 14px;
}

.dialog-field label {
  display: block;
  margin-bottom: 4px;
  font-size: 14px;
  color: #555;
}

.dialog-field input,
.dialog-field select {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 14px;
  box-sizing: border-box;
}

.dialog-field input:focus,
.dialog-field select:focus {
  outline: none;
  border-color: #667eea;
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 18px;
}

.dialog-actions .confirm-btn {
  padding: 8px 20px;
}

.dialog-actions .reject-btn {
  padding: 8px 20px;
}

/* 推荐问题 */
.suggested-questions {
  padding: 0 1.5rem;
}
.suggested-label {
  font-size: 13px;
  color: #999;
  margin-bottom: 8px;
}
.suggested-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.suggested-btn {
  padding: 10px 16px;
  background: #f0f2ff;
  color: #667eea;
  border: 1px solid #d0d5ff;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  text-align: left;
  width: 100%;
  transition: all 0.2s;
}
.suggested-btn:hover:not(:disabled) {
  background: #667eea;
  color: white;
  border-color: #667eea;
}
.suggested-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
