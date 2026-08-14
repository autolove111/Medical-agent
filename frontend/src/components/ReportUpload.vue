<template>
  <div class="report-upload">
    <!-- 上传触发按钮 -->
    <button @click="showDialog = true" class="upload-trigger-btn" :disabled="uploading">
      {{ uploading ? "识别中..." : "上传化验单" }}
    </button>

    <!-- 上传对话框 -->
    <div v-if="showDialog" class="dialog-overlay" @click.self="close">
      <div class="dialog-box">
        <h3>上传化验单</h3>

        <!-- 拖拽区域 -->
        <div
          class="drop-zone"
          :class="{ dragging }"
          @dragover.prevent="dragging = true"
          @dragleave="dragging = false"
          @drop.prevent="handleDrop"
          @click="$refs.fileInput.click()"
        >
          <div v-if="!preview" class="drop-hint">
            <p>拖拽化验单图片到此处</p>
            <p class="sub">或点击选择文件 (JPG/PNG/PDF)</p>
          </div>
          <img v-else :src="preview" class="preview-img" />
        </div>

        <input
          ref="fileInput"
          type="file"
          accept="image/*,.pdf"
          style="display:none"
          @change="handleFileSelect"
        />

        <!-- 年龄和性别输入 -->
        <div class="form-row">
          <label>年龄：</label>
          <input v-model.number="age" type="number" min="0" max="120" placeholder="岁" />
          <label>性别：</label>
          <select v-model="gender">
            <option value="">未知</option>
            <option value="male">男</option>
            <option value="female">女</option>
          </select>
        </div>

        <!-- 上传进度 -->
        <div v-if="uploading" class="progress-bar">
          <div class="progress-fill"></div>
        </div>
        <div v-if="uploadError" class="error-msg">{{ uploadError }}</div>

        <!-- 结果预览 -->
        <div v-if="uploadResult" class="upload-result">
          <p>识别到 <strong>{{ uploadResult.indicators?.length || 0 }}</strong> 项指标</p>
          <p v-if="uploadResult.abnormal_count">
            异常 <strong>{{ uploadResult.abnormal_count }}</strong> 项，
            正常 {{ uploadResult.normal_count }} 项
          </p>
        </div>

        <!-- 按钮 -->
        <div class="dialog-actions">
          <button @click="close" :disabled="uploading" class="cancel-btn">取消</button>
          <button @click="doUpload" :disabled="!file || uploading" class="upload-btn">
            {{ uploading ? "识别中..." : "开始识别" }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from "vue"
import ApiService from "../services/ApiService"
import { useAuthStore } from "../stores/authStore"

const props = defineProps({
  sessionId: { type: String, default: "default" }
})
const emit = defineEmits(["uploaded"])
const authStore = useAuthStore()

const showDialog = ref(false)
const file = ref(null)
const preview = ref(null)
const reportDate = ref("")
const age = ref(0)
const gender = ref("")
const dragging = ref(false)
const uploading = ref(false)
const uploadError = ref(null)
const uploadResult = ref(null)

function handleFileSelect(e) {
  const f = e.target.files[0]
  if (!f) return

  // 修复：添加文件类型和大小校验
  const allowedTypes = ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'application/pdf']
  const maxSize = 10 * 1024 * 1024 // 10MB

  if (!allowedTypes.includes(f.type)) {
    uploadError.value = "仅支持 JPG/PNG/GIF/WebP/PDF 文件"
    return
  }
  if (f.size > maxSize) {
    uploadError.value = "文件大小不能超过 10MB"
    return
  }

  file.value = f
  uploadError.value = null
  uploadResult.value = null
  if (f.type.startsWith("image/")) {
    const reader = new FileReader()
    reader.onload = (ev) => { preview.value = ev.target.result }
    reader.readAsDataURL(f)
  } else {
    preview.value = null
  }
}

function handleDrop(e) {
  dragging.value = false
  const f = e.dataTransfer.files[0]
  if (!f) return

  // 修复：添加文件类型和大小校验
  const allowedTypes = ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'application/pdf']
  const maxSize = 10 * 1024 * 1024 // 10MB

  if (!allowedTypes.includes(f.type)) {
    uploadError.value = "仅支持 JPG/PNG/GIF/WebP/PDF 文件"
    return
  }
  if (f.size > maxSize) {
    uploadError.value = "文件大小不能超过 10MB"
    return
  }

  file.value = f
  uploadError.value = null
  if (f.type.startsWith("image/")) {
    const reader = new FileReader()
    reader.onload = (ev) => { preview.value = ev.target.result }
    reader.readAsDataURL(f)
  }
}

async function doUpload() {
  if (!file.value) return
  uploading.value = true
  uploadError.value = null
  uploadResult.value = null
  try {
    // 1. 上传文件，拿到 task_id
    const submitResult = await ApiService.uploadLabReport(
      file.value, authStore.user?.idNumber || "default", props.sessionId, age.value, gender.value
    )
    // 2. 轮询等待 OCR 完成
    const result = await ApiService.pollOcrStatus(submitResult.task_id)
    uploadResult.value = result
    emit("uploaded", result)
    setTimeout(() => close(), 1500)
  } catch (e) {
    uploadError.value = "上传失败: " + (e.message || e)
  } finally {
    uploading.value = false
  }
}

function close() {
  showDialog.value = false
  file.value = null
  preview.value = null
  uploadError.value = null
  uploadResult.value = null
}
</script>

<style scoped>
.upload-trigger-btn {
  padding: 8px 16px; background: #667eea; color: white; border: none;
  border-radius: 6px; cursor: pointer; font-weight: 600; transition: background 0.3s;
}
.upload-trigger-btn:hover { background: #764ba2; }
.upload-trigger-btn:disabled { background: #ccc; cursor: not-allowed; }

.dialog-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.4);
  display: flex; align-items: center; justify-content: center; z-index: 1000;
}
.dialog-box {
  background: white; border-radius: 12px; padding: 24px; width: 440px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.2);
}
.dialog-box h3 { margin: 0 0 16px; font-size: 18px; }

.drop-zone {
  border: 2px dashed #ccc; border-radius: 8px; padding: 32px; text-align: center;
  cursor: pointer; transition: all 0.3s; margin-bottom: 12px;
}
.drop-zone:hover, .drop-zone.dragging { border-color: #667eea; background: #f0f2ff; }
.drop-hint p { margin: 0; color: #666; }
.drop-hint .sub { font-size: 13px; color: #999; margin-top: 6px; }
.preview-img { max-width: 100%; max-height: 200px; border-radius: 4px; }

.form-row { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; }
.form-row label { font-size: 13px; color: #666; white-space: nowrap; }
.form-row input, .form-row select {
  flex: 1; padding: 6px 10px; border: 1px solid #ddd; border-radius: 4px; font-size: 13px;
}

.progress-bar { height: 4px; background: #eee; border-radius: 2px; margin: 8px 0; overflow: hidden; }
.progress-fill {
  height: 100%; width: 30%; background: linear-gradient(90deg, #667eea, #764ba2);
  animation: progress 1.5s infinite;
}
@keyframes progress { 0% { width: 0; } 50% { width: 70%; } 100% { width: 100%; } }

.error-msg { color: #e74c3c; font-size: 13px; margin: 8px 0; }
.upload-result { background: #d5f5e3; padding: 10px; border-radius: 6px; font-size: 14px; margin: 8px 0; }
.upload-result p { margin: 2px 0; }

.dialog-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 16px; }
.cancel-btn {
  padding: 8px 20px; background: #eee; color: #666; border: none; border-radius: 6px; cursor: pointer;
}
.upload-btn {
  padding: 8px 20px; background: #667eea; color: white; border: none; border-radius: 6px;
  cursor: pointer; font-weight: 600;
}
.upload-btn:disabled { background: #ccc; cursor: not-allowed; }
</style>
