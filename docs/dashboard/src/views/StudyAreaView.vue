<script setup lang="ts">
import DataTable from '../components/DataTable.vue'
import type { DataTableColumn } from '../components/DataTable.vue'
import MapPanel from '../components/MapPanel.vue'
import { useJson } from '../composables/useJson'
import type { DatasetCatalogEntry } from '../types/data'

const { data: catalog } = useJson<DatasetCatalogEntry[]>('json/datasets_catalog.json')

const columns: DataTableColumn<DatasetCatalogEntry>[] = [
  { key: 'theme', label: 'Tema' },
  { key: 'source', label: 'Fonte' },
  { key: 'native_res', label: 'Resolução nativa' },
  { key: 'period', label: 'Período' },
]
</script>

<template>
  <section>
    <h1>Área de Estudo &amp; Fontes de Dados</h1>
    <p>
      Goiás + Distrito Federal (~340.000 km², bioma Cerrado), 247 municípios da
      Malha Municipal Digital 2025 oficial do IBGE — que substitui o GAUL tanto na
      dissolução da AOI quanto no relatório municipal (Parte 1 / Parte 12).
    </p>

    <MapPanel :outline="true">
      <template #legend>
        <div class="map-legend-text">Contorno da AOI (GO + DF). Passe o mouse sobre o mapa para ver os limites municipais.</div>
      </template>
    </MapPanel>

    <h2>Catálogo de conjuntos de dados</h2>
    <DataTable v-if="catalog" :columns="columns" :rows="catalog" />
  </section>
</template>

<style scoped>
.map-legend-text {
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
  font-size: 0.8rem;
}
</style>
