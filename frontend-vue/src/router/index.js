import { createRouter, createWebHistory } from "vue-router";
import ChatWindow from "../components/ChatWindow.vue";

/**
 * Vue Router 配置
 *
 * 职责：
 * 1. 定义应用的所有路由
 * 2. 管理URL与组件的映射
 * 3. 处理路由导航和跳转
 */
const routes = [
  {
    path: "/",
    name: "Home",
    component: ChatWindow,
  },
  {
    path: "/chat",
    name: "Chat",
    component: ChatWindow,
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

export default router;
