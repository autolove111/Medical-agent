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
  </div>
</template>

<script>
import { ref, onMounted, computed, nextTick } from "vue";
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

    onMounted(async () => {
      if (!authStore.isLoggedIn && localStorage.getItem("token")) {
        authStore.restoreAuth();
      }

      if (!authStore.isLoggedIn) {
        router.push("/login");
        return;
      }

      try {
        await ApiService.checkHealth();
        console.log("Backend service is healthy");
      } catch (err) {
        error.value = "无法连接到后端服务，请检查服务是否运行";
      }
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
        await ApiService.streamChat(userMessage, (chunk) => {
          isStreaming.value = true; // 开始接收数据，隐藏加载圈圈

          // 【核心修复】：不再用 ID 查找，直接抓取列表里的最后一条消息
          const lastIndex = chatStore.messages.length - 1;
          const msg = chatStore.messages[lastIndex];

          // 确认最后一条确实是助手的消息，然后追加文字
          if (msg && msg.role === "assistant") {
            msg.content += chunk;
            scrollToBottom(); // 每次文字更新都保持滚动在最底部
          }
        });
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

    function handleLogout() {
      authStore.logout();
      router.push("/login");
    }

    return {
      userInput,
      fileInput,
      isLoading,
      isStreaming, // 暴露给模板
      error,
      messages,
      currentUser,
      sendMessage,
      uploadFile,
      handleFileUpload,
      handleLogout,
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
</style>
