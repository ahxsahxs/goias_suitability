<script setup lang="ts">
import DataTable from '../components/DataTable.vue'
import type { DataTableColumn } from '../components/DataTable.vue'
import MapPanel from '../components/MapPanel.vue'
import { useJson } from '../composables/useJson'
import { useManifest } from '../composables/useManifest'
import { fmtInt, fmtKm2 } from '../format'
import type { DatasetCatalogEntry } from '../types/data'

const { data: catalog } = useJson<DatasetCatalogEntry[]>('json/datasets_catalog.json')
const { manifest } = useManifest()

const columns: DataTableColumn<DatasetCatalogEntry>[] = [
  { key: 'theme', label: 'Tema' },
  { key: 'source', label: 'Fonte' },
  { key: 'native_res', label: 'Resolução nativa' },
  { key: 'period', label: 'Período' },
]
</script>

<template>
  <section>
    <h1>Área de estudo e fontes de dados</h1>
    <p v-if="manifest">
      A área de interesse é o conjunto de Goiás e do Distrito Federal
      ({{ fmtKm2(manifest.aoi.area_km2) }}, bioma Cerrado), delimitado pela Malha Municipal Digital
      do IBGE: {{ fmtInt(manifest.aoi.n_municipalities) }} unidades municipais
      (<template v-for="(n, uf, i) in manifest.aoi.municipalities_by_uf" :key="uf"
        ><template v-if="i > 0"> e </template>{{ n }} em {{ uf }}</template
      >). Todos os produtos são harmonizados numa grade de {{ manifest.grid_m }}&nbsp;m (EPSG:4326),
      e as áreas são calculadas pela área de cada pixel.
    </p>

    <!-- Framed on all of Brazil so the AOI's national context is visible first. -->
    <MapPanel :outline="true" :satellite="true" :center="[-53, -15]" :zoom="3.2">
      <template #legend>
        <div class="map-legend-text">
          Área de estudo (GO e DF) em vermelho. Aproxime o mapa para ver os limites municipais.
        </div>
      </template>
    </MapPanel>

    <h2>Catálogo de dados</h2>
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
