import { createRouter, createWebHistory } from "vue-router";
import Login from "../views/Login.vue";
import ChatWindow from "../components/ChatWindow.vue";
import { useAuthStore } from "@/stores/authStore";

/**
 * Vue Router 配置
 *
 * 职责：
 * 1. 定义应用的所有路由
 * 2. 管理URL与组件的映射
 * 3. 处理路由导航和跳转
 * 4. 实现路由守卫（认证检查）
 */
const routes = [
  {
    path: "/login",
    name: "Login",
    component: Login,
    meta: { requiresAuth: false },
  },
  {
    path: "/",
    name: "Home",
    component: ChatWindow,
    meta: { requiresAuth: true },
  },
  {
    path: "/chat",
    name: "Chat",
    component: ChatWindow,
    meta: { requiresAuth: true },
  },
  {
    path: "/dashboard",
    name: "Dashboard",
    component: ChatWindow,
    meta: { requiresAuth: true },
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

// 路由守卫：暂时关闭认证（开发调试阶段）
router.beforeEach(async (to, from, next) => {
  next();  // TODO: 恢复认证逻辑
});

export default router;
