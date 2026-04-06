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
 * 1. 封装所有HTTP请求（axios / fetch）
 * 2. 处理认证令牌的自动添加
 * 3. 统一错误处理
 * 4. 管理请求/响应拦截器
 */

// 请求拦截器：自动添加认证令牌
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem("token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  },
);

// 响应拦截器：处理 401 未授权情况
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      // Token 过期或无效，清除本地存储并重定向到登录页
      localStorage.removeItem("token");
      localStorage.removeItem("user");
      window.location.href = "/login";
    }
    return Promise.reject(error.response?.data || error);
  },
);

export default {
  /**
   * 设置认证令牌
   */
  setAuthToken(token) {
    if (token) {
      apiClient.defaults.headers.common["Authorization"] = `Bearer ${token}`;
    } else {
      delete apiClient.defaults.headers.common["Authorization"];
    }
  },

  post(url, data) {
    return apiClient.post(url, data);
  },

  get(url, config) {
    return apiClient.get(url, config);
  },

  put(url, data) {
    return apiClient.put(url, data);
  },

  delete(url) {
    return apiClient.delete(url);
  },

  async checkHealth() {
    try {
      const response = await apiClient.get("/v1/health");
      return response.data;
    } catch (error) {
      console.error("Health check failed:", error);
      throw error;
    }
  },

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
   * AI对话 (传统的同步阻塞方式，等待全部生成完毕才返回)
   * 注意：前端流式对话功能已改用 fetch 实现，完美支持 POST 请求和携带 Authorization Header
   * 这个接口仍保留给非流式对话使用，或者作为后端测试接口
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
   * 追加病历记录（对话确认后调用）
   */
  async appendMedicalHistory(disease, status) {
    try {
      const response = await apiClient.post(
        "/v1/user/medical-history/append",
        null,
        {
          params: { disease, status },
        },
      );
      return response.data;
    } catch (error) {
      console.error("Append medical history failed:", error);
      throw error;
    }
  },

  /**
   * 更新过敏药物
   */
  async updateDrugAllergy(drugAllergy) {
    try {
      const response = await apiClient.post(
        "/v1/user/drug-allergy/update",
        null,
        {
          params: { drugAllergy },
        },
      );
      return response.data;
    } catch (error) {
      console.error("Update drug allergy failed:", error);
      throw error;
    }
  },

  /**
   * 查询用户病历历史
   */
  async getMedicalHistory() {
    try {
      const response = await apiClient.get("/v1/user/medical-history");
      return response.data;
    } catch (error) {
      console.error("Get medical history failed:", error);
      throw error;
    }
  },

  /**
   * 用户登出：通知后端清空会话对话历史
   */
  async logout() {
    try {
      await apiClient.post("/v1/auth/logout");
    } catch (error) {
      console.error("Logout request failed:", error);
    }
  },

  /**
   * 从AI回复中提取疾病和药物过敏信息
   */
  async extractKeywords(text) {
    try {
      const response = await apiClient.post("/v1/agent/extract-keywords", {
        text,
      });
      return {
        isMedical: response.data.isMedical || false,
        diseases: response.data.diseases || "",
        drugAllergies: response.data.drugAllergies || "",
      };
    } catch (error) {
      console.error("Extract keywords failed:", error);
      return { isMedical: false, diseases: "", drugAllergies: "" };
    }
  },

  /**
   * 流式对话（Fetch 方案 - 大厂主流做法）
   * 完美支持 POST 请求和携带 Authorization Header
   */
  async streamChat(userQuery, onMessage, onError, onDone) {
    const token = localStorage.getItem("token");

    // 注意：这里需要带上后端代理前缀 /api
    const response = await fetch(
      `/api/v1/agent/chat/stream?userQuery=${encodeURIComponent(userQuery)}`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: "text/event-stream",
        },
      },
    );

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    // 获取流式读取器
    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    let streamDone = false;
    let streamMeta = null;

    function processEvent(eventText) {
      const dataLines = [];
      for (const line of eventText.split(/\r?\n/)) {
        const trimmed = line.trim();
        if (trimmed.startsWith("data:")) {
          dataLines.push(trimmed.replace(/^data:\s*/, ""));
        }
      }
      if (dataLines.length === 0) return;
      const fullData = dataLines.join("\n").trim();
      if (!fullData || fullData === "[DONE]") {
        streamDone = true;
        return;
      }

      // 解析 [META:{...}] 元数据事件
      if (fullData.startsWith("[META:") && fullData.endsWith("]")) {
        try {
          const metaJson = fullData.substring(6, fullData.length - 1);
          streamMeta = JSON.parse(metaJson);
        } catch (e) {
          console.error("META parse error:", e);
        }
        return;
      }

      try {
        const parsed = JSON.parse(fullData);
        if (parsed.content !== undefined) {
          onMessage(parsed.content);
          return;
        }
      } catch (e) {
        // 不是JSON，直接作为文本
      }
      onMessage(fullData);
    }

    try {
      while (true) {
        const { value, done } = await reader.read();
        console.log("[SSE] read:", {
          done,
          chunkLen: value?.length,
          raw: value
            ? decoder.decode(value.slice(0, 200), { stream: false })
            : null,
        });
        if (done || streamDone) {
          if (buffer.trim()) {
            processEvent(buffer);
          }
          break;
        }

        buffer += decoder.decode(value, { stream: true });

        // SSE事件以双换行 \n\n 分隔
        const events = buffer.split(/\n\n/);
        buffer = events.pop() || "";

        for (const event of events) {
          processEvent(event);
          if (streamDone) break;
        }
        // [DONE] 已收到，立即退出，不再等待下次 read
        if (streamDone) break;
      }
    } finally {
      try {
        reader.cancel();
      } catch (e) {
        /* ignore */
      }
      if (onDone) onDone(streamMeta);
    }
  },
};
