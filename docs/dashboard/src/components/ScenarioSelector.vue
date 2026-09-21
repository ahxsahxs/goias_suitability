<script setup lang="ts">
export interface Scenario {
  ssp: string
  window: string
}

const SSPS = [
  { value: 'ssp245', label: 'SSP2-4.5' },
  { value: 'ssp585', label: 'SSP5-8.5' },
]
const WINDOWS = [
  { value: '2031_2050', label: '2031-2050' },
  { value: '2051_2070', label: '2051-2070' },
]

const props = defineProps<{ modelValue: Scenario }>()
const emit = defineEmits<{ 'update:modelValue': [scenario: Scenario] }>()

function setSsp(ssp: string): void {
  emit('update:modelValue', { ssp, window: props.modelValue.window })
}
function setWindow(window: string): void {
  emit('update:modelValue', { ssp: props.modelValue.ssp, window })
}
</script>

<template>
  <div class="scenario-selector">
    <div class="scenario-group" role="tablist" aria-label="Cenário">
      <button
        v-for="s in SSPS"
        :key="s.value"
        type="button"
        role="tab"
        :aria-selected="s.value === modelValue.ssp"
        :class="['scenario-btn', { active: s.value === modelValue.ssp }]"
        @click="setSsp(s.value)"
      >
        {{ s.label }}
      </button>
    </div>
    <div class="scenario-group" role="tablist" aria-label="Janela">
      <button
        v-for="w in WINDOWS"
        :key="w.value"
        type="button"
        role="tab"
        :aria-selected="w.value === modelValue.window"
        :class="['scenario-btn', { active: w.value === modelValue.window }]"
        @click="setWindow(w.value)"
      >
        {{ w.label }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.scenario-selector {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-4);
  margin-block: var(--space-3);
}

.scenario-group {
  display: flex;
  gap: var(--space-2);
}

.scenario-btn {
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  color: var(--color-text);
  padding: var(--space-1) var(--space-3);
  border-radius: var(--radius);
  cursor: pointer;
  font: inherit;
}

.scenario-btn.active {
  background: var(--color-accent);
  border-color: var(--color-accent);
  color: white;
}
</style>
