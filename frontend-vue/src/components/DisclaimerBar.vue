<template>
  <div class="disclaimer-bar">
    <span class="disclaimer-icon">⚠️</span>
    <span class="disclaimer-text">本建议仅供临床参考，不构成诊断。最终诊断与治疗方案请以主治医生医嘱为准。</span>
  </div>
</template>

<style scoped>
.disclaimer-bar {
  display: flex; align-items: center; justify-content: center; gap: 8px;
  padding: 6px 16px; background: linear-gradient(135deg, #fff3cd, #ffe69c);
  border-top: 1px solid #ffc107; font-size: 12px; color: #856404;
  text-align: center; flex-shrink: 0; z-index: 10;
}
.disclaimer-icon { font-size: 14px; }
.disclaimer-text { line-height: 1.4; }
</style>
