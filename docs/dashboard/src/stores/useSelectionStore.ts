import { defineStore } from 'pinia'
import { ref } from 'vue'

/**
 * The one piece of genuinely cross-route state (§2.1): a municipality selected in the
 * Municipal Explorer and carried into / out of a deep link. Per-route selector state
 * (segment, scenario, window) stays local to its view — do not grow this store into a
 * global bag.
 *
 * v0: defined and type-checked, consumed by nothing yet.
 */
export const useSelectionStore = defineStore('selection', () => {
  /** IBGE NM_MUN value, matching the municipal mesh join key (CLAUDE.md §7). */
  const selectedMunicipality = ref<string | null>(null)

  function select(name: string): void {
    selectedMunicipality.value = name
  }
  function clear(): void {
    selectedMunicipality.value = null
  }

  return { selectedMunicipality, select, clear }
})
