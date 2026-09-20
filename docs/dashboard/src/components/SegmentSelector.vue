<script setup lang="ts">
const props = defineProps<{
  segments: string[]
  labels?: Record<string, string>
  modelValue: string
}>()

const emit = defineEmits<{ 'update:modelValue': [segment: string] }>()

function label(seg: string): string {
  return props.labels?.[seg] ?? seg
}
</script>

<template>
  <div class="segment-selector" role="tablist">
    <button
      v-for="seg in segments"
      :key="seg"
      type="button"
      role="tab"
      :aria-selected="seg === modelValue"
      :class="['segment-btn', { active: seg === modelValue }]"
      @click="emit('update:modelValue', seg)"
    >
      {{ label(seg) }}
    </button>
  </div>
</template>

<style scoped>
.segment-selector {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-block: var(--space-3);
}

.segment-btn {
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  color: var(--color-text);
  padding: var(--space-1) var(--space-3);
  border-radius: var(--radius);
  cursor: pointer;
  font: inherit;
}

.segment-btn.active {
  background: var(--color-accent);
  border-color: var(--color-accent);
  color: white;
}
</style>
