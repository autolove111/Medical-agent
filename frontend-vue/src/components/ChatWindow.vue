<template>
  <div class="chat-container">
    <div class="header-bar">
      <div class="header-left">
        <h1>MedLabAgent</h1>
      </div>
      <div class="header-right">
        <div v-if="currentUser" class="user-info">
          <span>👤 {{ currentUser.realName }}</span>
          <button @click="handleLogout" class="logout-btn">登出</button>
        </div>
      </div>
    </div>

    <div class="chat-window">
      <div class="messages-area">
        <div v-if="messages.length === 0" class="empty-state">
          <h2>欢迎使用 MedLabAgent</h2>
          <p>医疗实验室AI智能体系统</p>
          <p class="user-greeter">
            {{ currentUser ? `Hi, ${currentUser.realName}!` : "" }}
          </p>
        </div>

        <div v-for="msg in messages" :key="msg.id">
          <ChatMessage :message="msg" />
          <!-- 对话确认按钮：仅在医疗诊断回复完成后显示 -->
          <div
            v-if="
              msg.role === 'assistant' &&
              msg.content &&
              !isLoading &&
              msg.isMedical &&
              !msg.confirmed &&
              !msg.rejected
            "
            class="confirm-bar"
          >
            <span class="confirm-hint">是否将此次诊断记录到您的病历？</span>
            <button @click="showSaveDialog(msg)" class="confirm-btn">
              ✅ 记录到病历
            </button>
            <button @click="msg.rejected = true" class="reject-btn">
              ❌ 不记录
            </button>
          </div>
          <div v-if="msg.confirmed" class="confirm-bar confirmed">
            <span>✅ 已记录到病历</span>
          </div>
        </div>

        <div v-if="isLoading && !isStreaming" class="message assistant">
          <div class="message-content">
            <div class="spinner"></div>
          </div>
        </div>
      </div>

      <div v-if="error" class="error-message">
        {{ error }}
      </div>

      <div class="input-area">
        <input
          v-model="userInput"
          type="text"
          placeholder="输入您的问题或上传医疗报告..."
          @keyup.enter="sendMessage"
          :disabled="isLoading"
        />
        <button @click="sendMessage" :disabled="isLoading || !userInput">
          {{ isLoading ? "发送中..." : "发送" }}
        </button>
        <button @click="uploadFile" :disabled="isLoading">📤 上传</button>
      </div>

      <input
        ref="fileInput"
        type="file"
        style="display: none"
        @change="handleFileUpload"
        accept="image/*,.pdf"
      />
    </div>

    <!-- 病历保存对话框 -->
    <div v-if="showMedicalDialog" class="dialog-overlay">
      <div class="dialog-box">
        <h3>📋 记录到病历</h3>
        <div class="dialog-field">
          <label>疾病/症状：</label>
          <input
            v-model="medicalForm.disease"
            type="text"
            placeholder="例如：急性扁桃体炎、高热"
          />
        </div>
        <div class="dialog-field">
          <label>药物过敏：</label>
          <input
            v-model="medicalForm.drugAllergy"
            type="text"
            placeholder="例如：青霉素（无则留空）"
          />
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
import { ref, onMounted, onBeforeUnmount, computed, nextTick } from "vue";
import ChatMessage from "./ChatMessage.vue";
import { useChatStore } from "../stores/chatStore";
import { useAuthStore } from "../stores/authStore";
import ApiService from "../services/ApiService";
import { useRouter } from "vue-router";

export default {
  name: "ChatWindow",
  components: {
    ChatMessage,
  },
  setup() {
    const chatStore = useChatStore();
    const authStore = useAuthStore();
    const router = useRouter();
    const userInput = ref("");
    const fileInput = ref(null);
    const isLoading = ref(false);
    const isStreaming = ref(false); // 新增：标记是否正在接收流数据
    const error = ref(null);
    const showMedicalDialog = ref(false);
    const currentSaveMsg = ref(null);
    const medicalForm = ref({ disease: "", status: "未康复" });

    const messages = computed(() => chatStore.messages);
    const currentUser = computed(() => authStore.user);

    // 新增：自动滚动到底部的函数
    const scrollToBottom = async () => {
      await nextTick();
      const container = document.querySelector(".messages-area");
      if (container) {
        container.scrollTop = container.scrollHeight;
      }
    };

    // 页面关闭/刷新时发送登出请求，清空会话历史
    function handlePageClose() {
      const token = localStorage.getItem("token");
      if (token) {
        navigator.sendBeacon(
          "/api/v1/auth/logout?token=" + encodeURIComponent(token),
        );
      }
    }

    onMounted(async () => {
      if (!authStore.isLoggedIn && localStorage.getItem("token")) {
        authStore.restoreAuth();
      }

      if (!authStore.isLoggedIn) {
        router.push("/login");
        return;
      }

      window.addEventListener("beforeunload", handlePageClose);

      try {
        await ApiService.checkHealth();
        console.log("Backend service is healthy");
      } catch (err) {
        error.value = "无法连接到后端服务，请检查服务是否运行";
      }
    });

    onBeforeUnmount(() => {
      window.removeEventListener("beforeunload", handlePageClose);
    });

    async function sendMessage() {
      if (!userInput.value.trim()) return;

      const userMessage = userInput.value;

      // 1. 添加用户消息到 Store
      chatStore.addMessage({
        role: "user",
        content: userMessage,
        id: Date.now(),
        timestamp: new Date(),
      });

      userInput.value = "";
      isLoading.value = true;
      isStreaming.value = false;
      error.value = null;
      scrollToBottom(); // 发送后立刻滚动到底部

      // 2. 预先创建一个“空”的助手消息对象
      chatStore.addMessage({
        role: "assistant",
        content: "",
        id: Date.now() + 1,
        timestamp: new Date(),
      });
      scrollToBottom();

      try {
        // 3. 调用流式接口
        await ApiService.streamChat(
          userMessage,
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
            console.log("Stream done, metadata:", metadata);
            const lastMsg = chatStore.messages[chatStore.messages.length - 1];
            if (lastMsg && lastMsg.role === "assistant" && metadata) {
              lastMsg.isMedical = metadata.isMedical || false;
              lastMsg.extractedDiseases = metadata.diseases || "";
              lastMsg.extractedDrugAllergy = metadata.drugAllergies || "";
              // 从显示内容中去掉 [META|...] 标记
              lastMsg.content = lastMsg.content
                .replace(/\n?\[META\|[^\]]*\]/g, "")
                .trimEnd();
            }
          },
        );
      } catch (err) {
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
          chatStore.addMessage({
            role: "user",
            content: `上传文件: ${file.name}`,
          });
          chatStore.addMessage({
            role: "assistant",
            content: `文件已成功上传。路径: ${response.filePath}`,
          });
          scrollToBottom();
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
      userInput,
      fileInput,
      isLoading,
      isStreaming,
      error,
      messages,
      currentUser,
      showMedicalDialog,
      medicalForm,
      sendMessage,
      uploadFile,
      handleFileUpload,
      handleLogout,
      showSaveDialog,
      confirmSave,
      cancelSave,
    };
  },
};
</script>

<style scoped>
/* 原有的样式完全保持不变 */
.chat-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  background: white;
  font-family:
    -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue",
    Arial, sans-serif;
}

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
</style>
