<template>
  <div class="login-container">
    <div class="login-box">
      <h1 class="login-title">医疗AI智能体</h1>
      <p class="login-subtitle">MedLabAgent - 健康管理助手</p>

      <!-- 登录表单 -->
      <form @submit.prevent="handleLogin" class="login-form" v-if="!isRegister">
        <div class="form-group">
          <label for="idNumber">身份证号</label>
          <input
            v-model="loginForm.idNumber"
            type="text"
            id="idNumber"
            placeholder="请输入身份证号"
            class="form-control"
            required
          />
        </div>

        <div class="form-group">
          <label for="password">密码</label>
          <input
            v-model="loginForm.password"
            type="password"
            id="password"
            placeholder="请输入密码"
            class="form-control"
            required
          />
        </div>

        <!-- 错误信息 -->
        <div v-if="errorMessage" class="error-message">
          {{ errorMessage }}
        </div>

        <!-- 加载按钮 -->
        <button type="submit" class="btn btn-primary" :disabled="isLoading">
          <span v-if="!isLoading">登 录</span>
          <span v-else>登录中...</span>
        </button>
      </form>

      <!-- 注册表单 -->
      <form @submit.prevent="handleRegister" class="register-form" v-else>
        <div class="form-group">
          <label for="reg-realname">真实姓名</label>
          <input
            v-model="registerForm.realName"
            type="text"
            id="reg-realname"
            placeholder="请输入您的真实姓名"
            class="form-control"
            required
          />
        </div>

        <div class="form-group">
          <label for="reg-idnumber">身份证号</label>
          <input
            v-model="registerForm.idNumber"
            type="text"
            id="reg-idnumber"
            placeholder="18位身份证号"
            class="form-control"
            required
          />
        </div>

        <div class="form-group">
          <label for="reg-password">密码</label>
          <input
            v-model="registerForm.password"
            type="password"
            id="reg-password"
            placeholder="至少 6 字符"
            class="form-control"
            required
          />
        </div>

        <div class="form-group">
          <label for="reg-confirm-password">确认密码</label>
          <input
            v-model="registerForm.confirmPassword"
            type="password"
            id="reg-confirm-password"
            placeholder="确认密码"
            class="form-control"
            required
          />
        </div>

        <!-- 错误信息 -->
        <div v-if="errorMessage" class="error-message">
          {{ errorMessage }}
        </div>

        <!-- 注册按钮 -->
        <button type="submit" class="btn btn-primary" :disabled="isLoading">
          <span v-if="!isLoading">注 册</span>
          <span v-else>注册中...</span>
        </button>
      </form>

      <!-- 切换登录/注册 -->
      <div class="form-footer">
        <button type="button" class="toggle-btn" @click="toggleForm">
          {{ isRegister ? "已有账号？返回登录" : "没有账号？立即注册" }}
        </button>
      </div>
    </div>

    <!-- 底部信息 -->
    <div class="login-footer">
      <p>医疗数据已加密存储 • 隐私保护通过国际认证</p>
      <p>© 2026 MedLabAgent. All rights reserved.</p>
    </div>
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
.login-container {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 20px;
  font-family:
    -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue",
    Arial, sans-serif;
}

.login-box {
  background: white;
  border-radius: 10px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
  padding: 50px 40px;
  width: 100%;
  max-width: 500px;
}

.login-title {
  text-align: center;
  color: #333;
  margin: 0 0 10px 0;
  font-size: 28px;
  font-weight: 600;
}

.login-subtitle {
  text-align: center;
  color: #999;
  margin: 0 0 30px 0;
  font-size: 14px;
}

.login-form,
.register-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 15px;
}

.form-group {
  display: flex;
  flex-direction: column;
}

.form-group label {
  color: #333;
  font-size: 14px;
  font-weight: 500;
  margin-bottom: 8px;
}

.form-control {
  padding: 12px 14px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 14px;
  transition: all 0.3s ease;
  background-color: #f9f9f9;
}

.form-control:focus {
  outline: none;
  border-color: #667eea;
  background-color: white;
  box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
}

.form-group.checkbox {
  flex-direction: row;
  align-items: center;
  margin: 10px 0;
}

.form-group.checkbox label {
  display: flex;
  align-items: center;
  margin: 0;
  font-size: 13px;
  color: #666;
}

.form-group.checkbox input[type="checkbox"] {
  margin-right: 8px;
  cursor: pointer;
  width: 16px;
  height: 16px;
}

.error-message {
  color: #dc3545;
  background-color: #f8d7da;
  border: 1px solid #f5c6cb;
  padding: 12px;
  border-radius: 6px;
  font-size: 14px;
  text-align: center;
}

.btn {
  padding: 12px;
  font-size: 16px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 600;
  transition: all 0.3s ease;
}

.btn-primary {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.btn-primary:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4);
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.form-footer {
  display: flex;
  justify-content: center;
  margin-top: 20px;
}

.toggle-btn {
  background: none;
  border: none;
  color: #667eea;
  font-size: 14px;
  cursor: pointer;
  text-decoration: underline;
  transition: color 0.3s ease;
}

.toggle-btn:hover {
  color: #764ba2;
}

.login-footer {
  text-align: center;
  color: rgba(255, 255, 255, 0.8);
  font-size: 12px;
  margin-top: 40px;
}

.login-footer p {
  margin: 5px 0;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .login-box {
    padding: 30px 20px;
  }

  .form-row {
    grid-template-columns: 1fr;
  }

  .login-title {
    font-size: 24px;
  }
}
</style>
