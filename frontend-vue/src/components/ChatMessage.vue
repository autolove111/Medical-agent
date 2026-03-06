<template>
  <div class="chat-message" :class="message.role">
    <div class="avatar" v-if="message.role === 'assistant'">🤖</div>
    <div class="message-body">
      <div class="message-content" v-html="renderedContent"></div>
      <div class="timestamp">{{ formatTime(message.timestamp) }}</div>
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";
import MarkdownIt from "markdown-it";
import DOMPurify from "dompurify";

const props = defineProps({
  message: {
    type: Object,
    required: true,
  },
});

const md = new MarkdownIt({
  html: false,
  linkify: true,
  typographer: true,
});

const renderedContent = computed(() => {
  const raw = props.message.content || "";
  const html = md.render(raw);
  return DOMPurify.sanitize(html);
});

function formatTime(date) {
  return new Date(date).toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
  });
}
</script>

<style scoped>
.chat-message {
  display: flex;
  margin-bottom: 1rem;
  align-items: flex-end;
}

.chat-message.user {
  justify-content: flex-end;
}

.avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 0.5rem;
  font-size: 1.5rem;
}

.message-body {
  display: flex;
  flex-direction: column;
}

.message-content {
  max-width: 500px;
  padding: 0.8rem 1.2rem;
  border-radius: 12px;
  word-wrap: break-word;
  line-height: 1.5;
}

.chat-message.user .message-content {
  background-color: #667eea;
  color: white;
}

.chat-message.assistant .message-content {
  background-color: #e8e8e8;
  color: #333;
}

.timestamp {
  font-size: 0.75rem;
  color: #999;
  margin-top: 0.3rem;
  padding: 0 0.8rem;
}
</style>
