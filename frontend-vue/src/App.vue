<template>
  <div id="app" class="app-container">
    <div v-if="showIntro" class="intro-overlay">
      <video
        ref="introVideo"
        class="intro-video"
        src="/videos/intro.mp4"
        autoplay
        playsinline
        muted
        @ended="hideIntro"
      ></video>
      <button class="skip-btn" @click="hideIntro">跳过</button>
    </div>

    <header v-if="showHeader" class="header">
      <h1>🏥 MedLabAgent - Medical AI System</h1>
    </header>

    <main class="main-content" :aria-hidden="showIntro">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from "vue";
import { useRoute } from "vue-router";

const route = useRoute();
const showHeader = computed(() => route.name !== "Login");

const showIntro = ref(true);
const introVideo = ref(null);

function hideIntro() {
  try {
    if (introVideo.value && introVideo.value.pause) introVideo.value.pause();
  } catch (e) {}
  showIntro.value = false;
}

onMounted(() => {
  // 尝试自动播放（某些浏览器需要静音或用户交互）
  if (introVideo.value && introVideo.value.play) {
    const p = introVideo.value.play();
    if (p && p.catch) p.catch(() => {});
  }
});
</script>

<style scoped>
.app-container {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f5f5f5;
}

.header {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  padding: 1.5rem 2rem;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.15);
  text-align: center;
  z-index: 5;
}

.header h1 {
  font-size: 1.8rem;
  font-weight: 700;
  margin: 0;
}

.main-content {
  flex: 1;
  display: flex;
  overflow: hidden;
  min-height: 0;
  width: 100%;
}

/* Intro video overlay */
.intro-overlay {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.95);
  z-index: 9999;
}

.intro-video {
  max-width: 100%;
  max-height: 100%;
  width: auto;
  height: auto;
  outline: none;
}

.skip-btn {
  position: absolute;
  top: 20px;
  right: 20px;
  background: rgba(255, 255, 255, 0.12);
  color: #fff;
  border: 1px solid rgba(255, 255, 255, 0.18);
  padding: 8px 12px;
  border-radius: 6px;
  cursor: pointer;
  backdrop-filter: blur(4px);
}

.skip-btn:hover {
  background: rgba(255, 255, 255, 0.18);
}
</style>
