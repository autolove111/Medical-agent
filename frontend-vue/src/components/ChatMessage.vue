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
  breaks: true, // 允许换行
});

const renderedContent = computed(() => {
  const raw = props.message.content || "";
  if (!raw.trim()) return "";

  const html = md.render(raw);

  // 配置 DOMPurify 允许markdown相关的HTML标签
  const config = {
    ALLOWED_TAGS: [
      "h1",
      "h2",
      "h3",
      "h4",
      "h5",
      "h6",
      "p",
      "br",
      "strong",
      "b",
      "em",
      "i",
      "ul",
      "ol",
      "li",
      "blockquote",
      "code",
      "pre",
      "a",
      "table",
      "thead",
      "tbody",
      "tr",
      "th",
      "td",
      "span",
      "div",
    ],
    ALLOWED_ATTR: ["href", "title", "class"],
  };

  const sanitized = DOMPurify.sanitize(html, config);

  // 调试：检查是否有HTML标签在输出中
  if (raw.includes("#") && !sanitized.includes("<h")) {
    console.warn("⚠️ Markdown heading render may have issues");
  }

  return sanitized;
});

function formatTime(date) {
  if (!date) return "";
  try {
    return new Date(date).toLocaleTimeString("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch (e) {
    return "";
  }
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

/* Markdown 样式支持 */
.message-content h1,
.message-content h2,
.message-content h3,
.message-content h4,
.message-content h5,
.message-content h6 {
  margin: 0.5rem 0;
  font-weight: bold;
  line-height: 1.3;
}

.message-content h1 {
  font-size: 1.5rem;
  border-bottom: 2px solid;
  padding-bottom: 0.3rem;
}

.message-content h2 {
  font-size: 1.3rem;
}

.message-content h3 {
  font-size: 1.1rem;
}

.message-content code {
  background-color: rgba(0, 0, 0, 0.05);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: "Courier New", monospace;
  font-size: 0.9em;
}

.message-content pre {
  background-color: rgba(0, 0, 0, 0.08);
  padding: 1rem;
  border-radius: 6px;
  overflow-x: auto;
  border-left: 3px solid;
  font-family: "Courier New", monospace;
  font-size: 0.85em;
  line-height: 1.4;
}

.message-content pre code {
  background: none;
  padding: 0;
  border-radius: 0;
}

.message-content ul,
.message-content ol {
  margin: 0.5rem 0;
  padding-left: 2rem;
}

.message-content li {
  margin: 0.3rem 0;
}

.message-content blockquote {
  border-left: 4px solid;
  margin: 0.5rem 0;
  padding: 0 0.5rem 0 1rem;
  opacity: 0.8;
  font-style: italic;
}

.message-content table {
  border-collapse: collapse;
  margin: 0.5rem 0;
  font-size: 0.9em;
}

.message-content table th,
.message-content table td {
  border: 1px solid rgba(0, 0, 0, 0.1);
  padding: 0.5rem;
  text-align: left;
}

.message-content table th {
  background-color: rgba(0, 0, 0, 0.05);
  font-weight: bold;
}

.message-content a {
  text-decoration: underline;
  cursor: pointer;
  color: inherit;
  opacity: 0.9;
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
