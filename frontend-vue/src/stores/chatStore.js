import { defineStore } from "pinia";
import { ref, computed } from "vue";

/**
 * 聊天状态管理
 * 使用Pinia进行全局状态管理
 *
 * 职责：
 * 1. 管理聊天消息列表
 * 2. 管理用户信息和会话状态
 * 3. 管理加载状态和错误状态
 */
export const useChatStore = defineStore("chat", () => {
  const messages = ref([]);
  const isLoading = ref(false);
  const error = ref(null);
  const userInfo = ref({
    id: "user_001",
    name: "User",
    avatar: "https://via.placeholder.com/40",
  });

  const messageCount = computed(() => messages.value.length);

  function addMessage(message) {
    messages.value.push({
      id: Date.now(),
      role: message.role,
      content: message.content,
      timestamp: new Date(),
      avatar: message.role === "user" ? userInfo.value.avatar : null,
    });
  }

  function clearMessages() {
    messages.value = [];
  }

  function setLoading(value) {
    isLoading.value = value;
  }

  function setError(message) {
    error.value = message;
  }

  function clearError() {
    error.value = null;
  }

  return {
    messages,
    isLoading,
    error,
    userInfo,
    messageCount,
    addMessage,
    clearMessages,
    setLoading,
    setError,
    clearError,
  };
});
