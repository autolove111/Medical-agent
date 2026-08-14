<template>
  <div class="indicator-card" :class="'status-' + indicator.status">
    <div class="indicator-header">
      <span class="indicator-name">{{ indicator.name }}</span>
      <span class="indicator-key">{{ indicator.key }}</span>
      <span class="status-badge">{{ statusLabel }}</span>
    </div>
    <div class="indicator-value">
      <span class="value">{{ indicator.value }}</span>
      <span class="unit">{{ indicator.unit }}</span>
    </div>
    <div class="indicator-ref" v-if="indicator.ref_range">
      参考：{{ indicator.ref_range }}
    </div>
    <div class="indicator-desc" v-if="indicator.description">
      {{ indicator.description }}
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue"

const props = defineProps({
  indicator: { type: Object, required: true },
})

const statusLabels = {
  normal: "正常",
  high: "偏高 ↑",
  low: "偏低 ↓",
  critical_high: "危急 ↑↑",
  critical_low: "危急 ↓↓",
}

const statusLabel = computed(() => statusLabels[props.indicator.status] || props.indicator.status)
</script>

<style scoped>
.indicator-card {
  padding: 10px 14px;
  border-radius: 8px;
  margin-bottom: 6px;
  border-left: 4px solid #ccc;
  background: #fafafa;
  transition: background 0.2s;
}
.indicator-card:hover { background: #f0f0f0; }

.status-high { border-left-color: #e67e22; background: #fff8f0; }
.status-low { border-left-color: #3498db; background: #f0f7ff; }
.status-critical_high, .status-critical_low {
  border-left-color: #e74c3c; background: #fff0f0; animation: pulse 2s infinite;
}
.status-normal { border-left-color: #27ae60; }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.85; }
}

.indicator-header {
  display: flex; align-items: center; gap: 8px; margin-bottom: 4px;
}
.indicator-name { font-weight: 600; font-size: 14px; color: #333; }
.indicator-key { font-size: 11px; color: #999; font-family: monospace; }
.status-badge {
  margin-left: auto; font-size: 12px; padding: 2px 8px; border-radius: 10px;
  background: #eee; color: #666;
}
.status-high .status-badge { background: #fdebd0; color: #e67e22; }
.status-low .status-badge { background: #d4e6f1; color: #2980b9; }
.status-critical_high .status-badge,
.status-critical_low .status-badge { background: #fadbd8; color: #c0392b; font-weight: 600; }
.status-normal .status-badge { background: #d5f5e3; color: #27ae60; }

.indicator-value { margin: 4px 0; }
.indicator-value .value { font-size: 22px; font-weight: 700; color: #222; }
.indicator-value .unit { font-size: 13px; color: #888; margin-left: 4px; }

.indicator-ref { font-size: 12px; color: #999; }
.indicator-desc { font-size: 12px; color: #666; margin-top: 4px; line-height: 1.4; }
</style>
