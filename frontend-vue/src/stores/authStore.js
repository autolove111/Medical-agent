import { defineStore } from "pinia";
import ApiService from "@/services/ApiService";

export const useAuthStore = defineStore("auth", {
  state: () => ({
    user: null,
    token: localStorage.getItem("token") || null,
    isAuthenticated: false,
    loading: false,
    error: null,
  }),

  getters: {
    /**
     * 获取当前用户信息
     */
    getCurrentUser: (state) => state.user,

    /**
     * 获取认证令牌
     */
    getToken: (state) => state.token,

    /**
     * 是否已认证
     */
    isLoggedIn: (state) => state.isAuthenticated,

    /**
     * 获取错误信息
     */
    getError: (state) => state.error,
  },

  actions: {
    /**
     * 用户登录
     */
    async login(credentials) {
      this.loading = true;
      this.error = null;

      try {
        const response = await ApiService.post("/v1/auth/login", {
          idNumber: credentials.idNumber,
          password: credentials.password,
        });

        // 后端返回结构: { code, message, data: { token, user, ... } }
        const authData = response.data.data;

        if (authData && authData.token) {
          // 保存 token 和用户信息
          this.token = authData.token;
          this.user = authData.user;
          this.isAuthenticated = true;

          // 保存到 localStorage
          localStorage.setItem("token", authData.token);
          localStorage.setItem("user", JSON.stringify(authData.user));

          // 设置 API 请求头
          ApiService.setAuthToken(authData.token);

          return authData;
        } else {
          throw new Error("登录失败：未收到有效的令牌");
        }
      } catch (error) {
        // 提供详细的错误信息
        let errorMsg = "登录失败";
        if (error.message) {
          errorMsg = error.message;
        } else if (error.code) {
          errorMsg = error.code + ": " + (error.message || "未知错误");
        }
        console.error("[AuthStore Login Error]", error);
        this.error = errorMsg;
        this.isAuthenticated = false;
        throw error;
      } finally {
        this.loading = false;
      }
    },

    /**
     * 用户注册 - 简化版本
     */
    async register(userData) {
      this.loading = true;
      this.error = null;

      try {
        const response = await ApiService.post("/v1/auth/register", {
          realName: userData.realName,
          idNumber: userData.idNumber,
          age: Number(userData.age),
          password: userData.password,
          confirmPassword: userData.confirmPassword,
        });

        // 后端返回结构: { code, message, data: { token, user, ... } }
        const authData = response.data.data;

        if (authData && authData.token) {
          // 自动登录
          this.token = authData.token;
          this.user = authData.user;
          this.isAuthenticated = true;

          // 保存到 localStorage
          localStorage.setItem("token", authData.token);
          localStorage.setItem("user", JSON.stringify(authData.user));

          // 设置 API 请求头
          ApiService.setAuthToken(authData.token);

          return authData;
        } else {
          throw new Error("注册失败：未收到有效的令牌");
        }
      } catch (error) {
        this.error = error.message || "注册失败或服务器错误";
        throw error;
      } finally {
        this.loading = false;
      }
    },

    /**
     * 用户登出
     */
    async logout() {
      // 先调用后端登出接口，清空会话对话历史
      await ApiService.logout();

      this.token = null;
      this.user = null;
      this.isAuthenticated = false;
      this.error = null;

      // 清空 localStorage
      localStorage.removeItem("token");
      localStorage.removeItem("user");

      // 清空 API 请求头
      ApiService.setAuthToken(null);
    },

    /**
     * 恢复认证状态（页面刷新时使用）
     * 会向后端验证 token 是否仍然有效
     */
    async restoreAuth() {
      const token = localStorage.getItem("token");
      const user = localStorage.getItem("user");

      if (token && user) {
        this.token = token;
        this.user = JSON.parse(user);
        this.isAuthenticated = true;
        ApiService.setAuthToken(token);

        // 向后端验证 token 有效性
        try {
          await ApiService.get("/v1/auth/me");
        } catch (e) {
          // token 无效或过期，清除登录状态
          this.logout();
        }
      }
    },

    /**
     * 更新用户信息
     */
    updateUserInfo(userInfo) {
      this.user = {
        ...this.user,
        ...userInfo,
      };
      localStorage.setItem("user", JSON.stringify(this.user));
    },

    /**
     * 清除错误信息
     */
    clearError() {
      this.error = null;
    },
  },
});
