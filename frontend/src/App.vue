<template>
  <div id="app" class="app-container">
    <main class="main-content">
      <router-view />
    </main>
  </div>
</template>

<script setup>
// App 组件只负责布局容器，不渲染 header
// header 已移到 ChatWindow.vue 内部
</script>

<style scoped>
.app-container {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f5f5f5;
}

.main-content {
  flex: 1;
  display: flex;
  overflow: hidden;
  min-height: 0;
  width: 100%;
}
</style>
