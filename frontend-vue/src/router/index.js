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

// 路由守卫：检查认证状态
router.beforeEach(async (to, from, next) => {
  const authStore = useAuthStore();

  // 首次加载时，从 localStorage 恢复并验证认证状态
  if (!authStore.isLoggedIn && localStorage.getItem("token")) {
    await authStore.restoreAuth();
  }

  // 如果路由需要认证
  if (to.meta.requiresAuth) {
    if (authStore.isLoggedIn) {
      // 已认证，允许访问
      next();
    } else {
      // 未认证，重定向到登录页
      next({
        path: "/login",
        query: { redirect: to.fullPath },
      });
    }
  } else {
    // 路由不需要认证
    if (to.path === "/login" && authStore.isLoggedIn) {
      // 已登录用户不能访问登录页，重定向到首页
      next("/");
    } else {
      next();
    }
  }
});

export default router;
