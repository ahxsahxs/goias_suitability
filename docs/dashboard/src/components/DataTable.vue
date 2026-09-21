<script setup lang="ts" generic="T extends object">
export interface DataTableColumn<T> {
  key: keyof T & string
  label: string
  /** Format a cell value for display; defaults to String(value). */
  format?: (row: T) => string
}

defineProps<{
  columns: DataTableColumn<T>[]
  rows: T[]
}>()
</script>

<template>
  <div class="data-table-wrap">
    <table class="data-table">
      <thead>
        <tr>
          <th v-for="col in columns" :key="col.key">{{ col.label }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, i) in rows" :key="i">
          <td v-for="col in columns" :key="col.key">
            {{ col.format ? col.format(row) : String(row[col.key] ?? '') }}
          </td>
        </tr>
      </tbody>
    </table>
    <p v-if="rows.length === 0" class="empty-hint">Sem dados.</p>
  </div>
</template>

<style scoped>
.data-table-wrap {
  overflow-x: auto;
  margin-block: var(--space-3);
}

.data-table {
  font-size: 0.9rem;
}

.empty-hint {
  color: var(--color-muted);
}
</style>
