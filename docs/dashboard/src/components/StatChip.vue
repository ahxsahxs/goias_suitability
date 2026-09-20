<script setup lang="ts">
defineProps<{
  label: string
  value: string | number
  hint?: string
}>()
</script>

<template>
  <div class="stat-chip" :title="hint">
    <span class="stat-chip-value">{{ value }}</span>
    <span class="stat-chip-label">{{ label }}</span>
  </div>
</template>

<style scoped>
.stat-chip {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
  min-width: 120px;
}

.stat-chip-value {
  font-size: 1.5rem;
  font-weight: 700;
}

.stat-chip-label {
  font-size: 0.8rem;
  color: var(--color-muted);
}
</style>
