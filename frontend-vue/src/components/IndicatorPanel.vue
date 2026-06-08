<template>
  <div class="indicator-panel" v-if="indicators.length > 0">
    <div class="panel-header">
      <h3>检验指标 ({{ indicators.length }} 项)</h3>
      <div class="summary-tags">
        <span class="tag tag-abnormal" v-if="abnormal.length">异常 {{ abnormal.length }}</span>
        <span class="tag tag-normal" v-if="normal.length">正常 {{ normal.length }}</span>
        <span class="tag tag-critical" v-if="critical.length">危急 {{ critical.length }}</span>
      </div>
    </div>

    <!-- 危急指标 -->
    <div class="section" v-if="critical.length">
      <div class="section-title critical-title">危急指标</div>
      <IndicatorCard v-for="ind in critical" :key="ind.key" :indicator="ind" />
    </div>

    <!-- 异常指标 -->
    <div class="section" v-if="abnormal.length">
      <div class="section-title abnormal-title">异常指标</div>
      <IndicatorCard v-for="ind in abnormal" :key="ind.key" :indicator="ind" />
    </div>

    <!-- 正常指标 -->
    <div class="section" v-if="normal.length">
      <div class="section-title normal-title" @click="showNormal = !showNormal" style="cursor:pointer">
        正常指标 ({{ normal.length }}) {{ showNormal ? '▲' : '▼' }}
      </div>
      <div v-if="showNormal">
        <IndicatorCard v-for="ind in normal" :key="ind.key" :indicator="ind" />
      </div>
    </div>

    <div v-if="reportDate" class="report-date">
      检验日期：{{ reportDate }}
    </div>
  </div>
  <div v-else class="indicator-panel empty">
    <p>暂无检验指标数据</p>
    <p class="hint">上传化验单后自动展示</p>
  </div>
</template>

<script setup>
import { computed, ref } from "vue"
import IndicatorCard from "./IndicatorCard.vue"

const props = defineProps({
  indicators: { type: Array, default: () => [] },
  reportDate: { type: String, default: "" },
})

const showNormal = ref(false)

const critical = computed(() => props.indicators.filter(i => i.status.startsWith("critical")))
const abnormal = computed(() => props.indicators.filter(i => i.status === "high" || i.status === "low"))
const normal = computed(() => props.indicators.filter(i => i.status === "normal"))
</script>

<style scoped>
.indicator-panel {
  background: white; border-radius: 10px; padding: 16px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08); max-height: 100%; overflow-y: auto;
}
.indicator-panel.empty { text-align: center; color: #999; padding: 40px 16px; }
.indicator-panel.empty .hint { font-size: 13px; color: #bbb; }

.panel-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid #eee;
}
.panel-header h3 { margin: 0; font-size: 16px; color: #333; }

.summary-tags { display: flex; gap: 6px; }
.tag { font-size: 12px; padding: 2px 8px; border-radius: 10px; }
.tag-abnormal { background: #fdebd0; color: #e67e22; }
.tag-normal { background: #d5f5e3; color: #27ae60; }
.tag-critical { background: #fadbd8; color: #c0392b; font-weight: 600; }

.section { margin-bottom: 12px; }
.section-title {
  font-size: 13px; font-weight: 600; padding: 4px 8px; border-radius: 4px; margin-bottom: 6px;
}
.critical-title { background: #fadbd8; color: #c0392b; }
.abnormal-title { background: #fdebd0; color: #e67e22; }
.normal-title { background: #e8f8f0; color: #27ae60; }

.report-date { text-align: right; font-size: 12px; color: #999; margin-top: 8px; }
</style>
