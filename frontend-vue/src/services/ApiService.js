import axios from "axios";

const apiClient = axios.create({
  baseURL: "/api",
  headers: {
    "Content-Type": "application/json",
  },
});

/**
 * API 服务模块
 *
 * 职责：
 * 1. 封装所有HTTP请求（axios）
 * 2. 处理EventSource流式响应
 * 3. 统一错误处理
 * 4. 管理请求/响应拦截器
 */
export default {
  /**
   * 健康检查
   */
  async checkHealth() {
    try {
      const response = await apiClient.get("/v1/health");
      return response.data;
    } catch (error) {
      console.error("Health check failed:", error);
      throw error;
    }
  },

  /**
   * 分析医疗报告
   */
  async analyzeReport(reportContent) {
    try {
      const response = await apiClient.post("/v1/agent/analyze-report", null, {
        params: { reportContent },
      });
      return response.data;
    } catch (error) {
      console.error("Analyze report failed:", error);
      throw error;
    }
  },

  /**
   * AI对话
   */
  async chat(userQuery) {
    try {
      const response = await apiClient.post("/v1/agent/chat", null, {
        params: { userQuery },
      });
      return response.data;
    } catch (error) {
      console.error("Chat request failed:", error);
      throw error;
    }
  },

  /**
   * 上传医疗报告文件
   */
  async uploadReport(file) {
    try {
      const formData = new FormData();
      formData.append("file", file);
      const response = await apiClient.post(
        "/v1/agent/upload-report",
        formData,
        {
          headers: {
            "Content-Type": "multipart/form-data",
          },
        },
      );
      return response.data;
    } catch (error) {
      console.error("Upload report failed:", error);
      throw error;
    }
  },

  /**
   * 搜索知识库
   */
  async searchKnowledge(keyword) {
    try {
      const response = await apiClient.get("/v1/knowledge/search", {
        params: { keyword },
      });
      return response.data;
    } catch (error) {
      console.error("Search knowledge failed:", error);
      throw error;
    }
  },

  /**
   * 流式对话（EventSource）
   */
  streamChat(userQuery, onMessage, onError) {
    const eventSource = new EventSource(
      `/api/v1/agent/chat-stream?userQuery=${encodeURIComponent(userQuery)}`,
    );

    eventSource.onmessage = (event) => {
      onMessage(event.data);
    };

    eventSource.onerror = (error) => {
      eventSource.close();
      onError(error);
    };

    return eventSource;
  },
};
