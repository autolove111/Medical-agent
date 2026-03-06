<template>
  <div class="chat-window">
    <div class="messages-area">
      <div v-if="messages.length === 0" class="empty-state">
        <h2>欢迎使用 MedLabAgent</h2>
        <p>医疗实验室AI智能体系统</p>
      </div>

      <div v-for="msg in messages" :key="msg.id">
        <ChatMessage :message="msg" />
      </div>

      <div v-if="isLoading" class="message assistant">
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
</template>

<script setup>
import { ref, onMounted } from "vue";
import ChatMessage from "./ChatMessage.vue";
import { useChatStore } from "../stores/chatStore";
import ApiService from "../services/ApiService";

const chatStore = useChatStore();
const userInput = ref("");
const fileInput = ref(null);
const isLoading = ref(false);
const error = ref(null);

const messages = chatStore.messages;

onMounted(async () => {
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
  chatStore.addMessage({
    role: "user",
    content: userMessage,
  });

  userInput.value = "";
  isLoading.value = true;
  error.value = null;

  try {
    const response = await ApiService.chat(userMessage);
    if (response.status === "success") {
      chatStore.addMessage({
        role: "assistant",
        content: response.response,
      });
    } else {
      error.value = response.message || "请求失败";
    }
  } catch (err) {
    error.value = "请求失败: " + err.message;
    chatStore.addMessage({
      role: "assistant",
      content: "抱歉，处理您的请求时出错了。",
    });
  } finally {
    isLoading.value = false;
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
</script>

<style scoped>
.chat-window {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: white;
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
