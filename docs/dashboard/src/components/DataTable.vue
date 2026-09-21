<script setup lang="ts" generic="T extends object">
import { computed, ref, watch } from 'vue'

export interface DataTableColumn<T> {
  key: keyof T & string
  label: string
  /** Format a cell value for display; defaults to String(value). */
  format?: (row: T) => string
}

const props = defineProps<{
  columns: DataTableColumn<T>[]
  rows: T[]
  /** Field identifying a row, e.g. 'NM_MUN' — required for selection highlight and row-click. */
  rowKey?: keyof T & string
  /** Current selection; rows whose `rowKey` field matches get a `.selected` class. */
  selectedValue?: unknown
  /** Enable click-to-sort column headers. Sort state is internal to this component. */
  sortable?: boolean
  initialSortKey?: keyof T & string
  initialSortDir?: 'asc' | 'desc'
}>()

const emit = defineEmits<{ rowClick: [row: T] }>()

const sortKey = ref<(keyof T & string) | null>(props.initialSortKey ?? null)
const sortDir = ref<'asc' | 'desc'>(props.initialSortDir ?? 'desc')

watch(
  () => props.initialSortKey,
  (v) => {
    if (v) sortKey.value = v
  },
)

function onHeaderClick(col: DataTableColumn<T>): void {
  if (!props.sortable) return
  if (sortKey.value === col.key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = col.key
    sortDir.value = props.initialSortDir ?? 'desc'
  }
}

const sortedRows = computed(() => {
  const key = sortKey.value
  if (!props.sortable || !key) return props.rows
  const dir = sortDir.value === 'asc' ? 1 : -1
  return [...props.rows].sort((a, b) => {
    const av = a[key as keyof T]
    const bv = b[key as keyof T]
    if (av === bv) return 0
    return (av < bv ? -1 : 1) * dir
  })
})

function rowValue(row: T): unknown {
  return props.rowKey ? row[props.rowKey] : undefined
}

function onRowClick(row: T): void {
  if (props.rowKey) emit('rowClick', row)
}
</script>

<template>
  <div class="data-table-wrap">
    <table class="data-table">
      <thead>
        <tr>
          <th
            v-for="col in columns"
            :key="col.key"
            :class="{ sortable }"
            @click="onHeaderClick(col)"
          >
            {{ col.label }}
            <span v-if="sortable && sortKey === col.key" class="sort-indicator">{{ sortDir === 'asc' ? '▲' : '▼' }}</span>
          </th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="(row, i) in sortedRows"
          :key="i"
          :class="{ clickable: !!rowKey, selected: rowKey && rowValue(row) === selectedValue }"
          @click="onRowClick(row)"
        >
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
  width: 100%;
}

th.sortable {
  cursor: pointer;
  user-select: none;
}

.sort-indicator {
  font-size: 0.7em;
  color: var(--color-accent);
}

tr.clickable {
  cursor: pointer;
}

tr.clickable:hover {
  background: var(--color-surface);
}

tr.selected {
  background: var(--color-accent);
  color: #ffffff;
}

.empty-hint {
  color: var(--color-muted);
}
</style>
