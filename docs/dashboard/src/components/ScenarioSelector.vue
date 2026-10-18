<script setup lang="ts">
import { computed } from 'vue'
import { useManifest } from '../composables/useManifest'

export interface Scenario {
  ssp: string
  window: string
}

// Scenarios and windows are config/datasets.yaml's `cmip6` block, via manifest.json.
const { manifest, windowLabel } = useManifest()
const SSPS = computed(() => (manifest.value?.ssps ?? []).map((s) => ({ value: s.key, label: s.label })))
const WINDOWS = computed(() =>
  (manifest.value?.windows ?? []).map((w) => ({ value: w.key, label: windowLabel(w.key) })),
)

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
    <div class="scenario-group" role="tablist" aria-label="Cenário SSP">
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
    <div class="scenario-group" role="tablist" aria-label="Janela temporal">
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
