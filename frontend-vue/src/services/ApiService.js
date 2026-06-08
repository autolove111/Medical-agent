import axios from "axios";

// 自动决定 API baseURL：默认使用代理前缀 `/api`，
// 但当前端被一个不带代理的静态 node 服务器（例如 localhost:8890）托管时，
// 直接指向后端 Spring Boot 服务，避免请求落在前端进程导致 405。
let computedBase = "/api";
// Vite proxy 已将 /api → :8000, /v1 → :8000，直接用相对路径即可
if (typeof window !== "undefined" && window.location) {
  console.log("[ApiService] base:", computedBase, "location:", window.location.href);
}

const apiClient = axios.create({
  baseURL: computedBase,
  headers: {
    "Content-Type": "application/json",
  },
});

// Debug: 输出当前计算的 API 基址，便于排查请求是否落到前端静态服务
if (typeof window !== "undefined") {
  console.log(
    "[ApiService] computedBase:",
    computedBase,
    "window.location:",
    window.location.href,
  );
}

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
      // 使用明确的查询字符串，避免 axios 在某些环境下触发不必要的 preflight
      const url = `/v1/user/medical-history/append?disease=${encodeURIComponent(
        disease || "",
      )}&status=${encodeURIComponent(status || "")}`;
      const response = await apiClient.post(url, null);
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
      // 使用 URL 查询字符串，确保请求以 POST 到后端映射的路径，不依赖 axios params 语义
      const url = `/v1/user/drug-allergy/update?drugAllergy=${encodeURIComponent(
        drugAllergy || "",
      )}`;
      const response = await apiClient.post(url, null);
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

  // ================================================================
  // Phase 1-5 新增 API (对接自研 Python FastAPI 后端 :8000)
  // ================================================================

  async uploadLabReport(file, userId = "default", reportDate = null, age = 0, gender = "") {
    try {
      const formData = new FormData()
      formData.append("file", file)
      formData.append("user_id", userId)
      if (reportDate) formData.append("report_date", reportDate)
      if (age) formData.append("age", String(age))
      if (gender) formData.append("gender", gender)
      const response = await apiClient.post("/report/upload", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      })
      return response.data
    } catch (error) {
      console.error("Upload lab report failed:", error)
      throw error
    }
  },

  async getReportDetail(reportId) {
    const response = await apiClient.get(`/report/${reportId}`)
    return response.data
  },

  async listUserReports(userId = "default") {
    const response = await apiClient.get(`/report/user/${userId}/list`)
    return response.data
  },

  async chatSync(userId, message, reportId = null, useAgentLoop = false) {
    const response = await apiClient.post("/chat", {
      user_id: userId || "default", message, report_id: reportId, use_agent_loop: useAgentLoop,
    })
    return response.data
  },

  async streamChatV2(userId, message, reportId, onChunk, onError, onDone) {
    const params = new URLSearchParams()
    params.set("user_id", userId || "default")
    params.set("message", message)
    if (reportId) params.set("report_id", reportId)
    const prefix = ((apiClient.defaults && apiClient.defaults.baseURL) || "").replace(/\/$/, "")
    const url = `${prefix}/chat/stream?${params.toString()}`
    try {
      const token = localStorage.getItem("token")
      const headers = { Accept: "text/event-stream" }
      if (token) headers.Authorization = `Bearer ${token}`
      const response = await fetch(url, { method: "GET", headers })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const reader = response.body.getReader()
      const decoder = new TextDecoder("utf-8")
      let buffer = ""
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split("\n")
        buffer = lines.pop() || ""
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const payload = line.slice(6)
            if (payload.startsWith("{")) {
              try {
                const data = JSON.parse(payload)
                if (data.done) { if (onDone) onDone(data); return }
                else if (data.error) { if (onError) onError(data.error); return }
                else if (data.content !== undefined) onChunk(data.content)
              } catch (e) { onChunk(payload) }
            } else { onChunk(payload) }
          }
        }
      }
      if (onDone) onDone({})
    } catch (err) { if (onError) onError(err.message) }
  },

  async getChatSources(userId = "default") {
    const response = await apiClient.get(`/chat/sources?user_id=${userId}`)
    return response.data
  },

  async getUserProfile(userId = "default") {
    const response = await apiClient.get(`/user/profile?user_id=${userId}`)
    return response.data
  },

  async updateUserProfileV2(profile) {
    const response = await apiClient.put("/user/profile", profile)
    return response.data
  },

  async resetSession(userId = "default") {
    const response = await apiClient.post(`/user/reset?user_id=${userId}`)
    return response.data
  },

  async analyzeVision(filePath, model = null) {
    try {
      const response = await apiClient.post("/v1/ocr/analyze-vision", null, {
        params: {
          filePath,
          ...(model ? { model } : {}),
        },
      });
      return response.data;
    } catch (error) {
      console.error("Analyze vision failed:", error);
      throw error;
    }
  },

  /**
   * 流式对话（Fetch 方案 - 大厂主流做法）
   * 完美支持 POST 请求和携带 Authorization Header
   */
  async streamChat(userQuery, onMessage, onError, onDone, options = {}) {
    const token = localStorage.getItem("token");
    const requestPayload =
      typeof userQuery === "object" && userQuery !== null
        ? { ...userQuery }
        : { query: userQuery };
    const queryText = requestPayload.query || requestPayload.userQuery || "";

    // 构建完整的后端流式接口 URL，避免相对路径落到当前 origin（例如 :8888 静态服务器）
    const base =
      (apiClient.defaults && apiClient.defaults.baseURL) ||
      computedBase ||
      "/api";
    const prefix = base.replace(/\/$/, "");
    const streamUrl = `${prefix}/v1/agent/chat/stream?userQuery=${encodeURIComponent(
      queryText,
    )}`;

    const response = await fetch(streamUrl, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "text/event-stream",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        ...requestPayload,
        ...options,
        query: queryText,
      }),
    });

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
