<template>
  <div class="login-page">
    <div class="login-card">
      <!-- Logo 区域 -->
      <div class="login-logo">
        <div class="logo-icon">🏥</div>
        <h1>MedLabAgent</h1>
        <p>医疗AI智能体 · 健康管理助手</p>
      </div>

      <!-- 登录表单 -->
      <form @submit.prevent="handleLogin" v-if="!isRegister">
        <div class="input-group">
          <label>身份证号</label>
          <input
            v-model="loginForm.idNumber"
            type="text"
            placeholder="请输入18位身份证号"
            required
          />
        </div>

        <div class="input-group">
          <label>密码</label>
          <input
            v-model="loginForm.password"
            type="password"
            placeholder="请输入密码"
            required
          />
        </div>

        <div v-if="errorMessage" class="error-msg">{{ errorMessage }}</div>

        <button type="submit" class="submit-btn" :disabled="isLoading">
          {{ isLoading ? "登录中..." : "登 录" }}
        </button>
      </form>

      <!-- 注册表单 -->
      <form @submit.prevent="handleRegister" v-else>
        <div class="input-group">
          <label>真实姓名</label>
          <input
            v-model="registerForm.realName"
            type="text"
            placeholder="请输入真实姓名"
            required
          />
        </div>

        <div class="input-group">
          <label>身份证号</label>
          <input
            v-model="registerForm.idNumber"
            type="text"
            placeholder="18位身份证号"
            required
          />
        </div>

        <div class="input-group">
          <label>密码</label>
          <input
            v-model="registerForm.password"
            type="password"
            placeholder="至少6个字符"
            required
          />
        </div>

        <div class="input-group">
          <label>确认密码</label>
          <input
            v-model="registerForm.confirmPassword"
            type="password"
            placeholder="再次输入密码"
            required
          />
        </div>

        <div v-if="errorMessage" class="error-msg">{{ errorMessage }}</div>

        <button type="submit" class="submit-btn" :disabled="isLoading">
          {{ isLoading ? "注册中..." : "注 册" }}
        </button>
      </form>

      <!-- 切换 -->
      <div class="switch-link">
        <span @click="toggleForm">
          {{ isRegister ? "已有账号？返回登录" : "没有账号？立即注册" }}
        </span>
      </div>
    </div>

    <!-- 底部 -->
    <p class="footer-text">
      医疗数据已加密存储 · 隐私保护通过国际认证<br />© 2026 MedLabAgent
    </p>
  </div>
</template>

<script>
import { useAuthStore } from "@/stores/authStore";

export default {
  name: "Login",
  data() {
    return {
      isRegister: false,
      isLoading: false,
      errorMessage: "",
      loginForm: {
        idNumber: "",
        password: "",
      },
      registerForm: {
        realName: "",
        idNumber: "",
        password: "",
        confirmPassword: "",
      },
    };
  },
  methods: {
    async handleLogin() {
      this.errorMessage = "";
      this.isLoading = true;

      try {
        const authStore = useAuthStore();
        await authStore.login(this.loginForm);
        this.$router.push("/dashboard");
      } catch (error) {
        this.errorMessage = error.message || "登录失败，请重试";
      } finally {
        this.isLoading = false;
      }
    },

    async handleRegister() {
      this.errorMessage = "";

      if (this.registerForm.password !== this.registerForm.confirmPassword) {
        this.errorMessage = "两次输入的密码不一致";
        return;
      }

      this.isLoading = true;

      try {
        const authStore = useAuthStore();
        await authStore.register(this.registerForm);
        this.$router.push("/dashboard");
      } catch (error) {
        this.errorMessage = error.message || "注册失败，请重试";
      } finally {
        this.isLoading = false;
      }
    },

    toggleForm() {
      this.isRegister = !this.isRegister;
      this.errorMessage = "";
      this.loginForm = { idNumber: "", password: "" };
      this.registerForm = {
        realName: "",
        idNumber: "",
        password: "",
        confirmPassword: "",
      };
    },
  },
};
</script>

<style scoped>
.login-page {
  position: fixed;
  inset: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  z-index: 100;
}

.login-card {
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  padding: 48px 40px 36px;
  width: 420px;
  max-width: 90vw;
}

/* Logo */
.login-logo {
  text-align: center;
  margin-bottom: 32px;
}

.logo-icon {
  font-size: 48px;
  margin-bottom: 8px;
}

.login-logo h1 {
  font-size: 26px;
  font-weight: 700;
  color: #2d3748;
  margin: 0 0 6px;
}

.login-logo p {
  font-size: 13px;
  color: #a0aec0;
  margin: 0;
}

/* 表单 */
.input-group {
  margin-bottom: 20px;
}

.input-group label {
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: #4a5568;
  margin-bottom: 6px;
}

.input-group input {
  width: 100%;
  padding: 11px 14px;
  border: 1.5px solid #e2e8f0;
  border-radius: 8px;
  font-size: 14px;
  color: #2d3748;
  background: #f7fafc;
  transition: all 0.2s;
  box-sizing: border-box;
}

.input-group input:focus {
  outline: none;
  border-color: #667eea;
  background: #fff;
  box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.15);
}

.input-group input::placeholder {
  color: #cbd5e0;
}

/* 错误 */
.error-msg {
  background: #fff5f5;
  color: #c53030;
  border: 1px solid #feb2b2;
  border-radius: 8px;
  padding: 10px 14px;
  font-size: 13px;
  text-align: center;
  margin-bottom: 16px;
}

/* 按钮 */
.submit-btn {
  width: 100%;
  padding: 12px;
  border: none;
  border-radius: 8px;
  font-size: 15px;
  font-weight: 600;
  color: #fff;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  cursor: pointer;
  transition: all 0.25s;
  letter-spacing: 4px;
}

.submit-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(102, 126, 234, 0.45);
}

.submit-btn:active:not(:disabled) {
  transform: translateY(0);
}

.submit-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

/* 切换链接 */
.switch-link {
  text-align: center;
  margin-top: 20px;
}

.switch-link span {
  font-size: 13px;
  color: #667eea;
  cursor: pointer;
}

.switch-link span:hover {
  color: #764ba2;
  text-decoration: underline;
}

/* 底部 */
.footer-text {
  color: rgba(255, 255, 255, 0.65);
  font-size: 11px;
  text-align: center;
  margin-top: 32px;
  line-height: 1.6;
}

@media (max-width: 480px) {
  .login-card {
    padding: 32px 24px 28px;
  }
}
</style>
