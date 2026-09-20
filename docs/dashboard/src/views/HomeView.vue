<script setup lang="ts">
import MapPanel from '../components/MapPanel.vue'
import StatChip from '../components/StatChip.vue'
import { useJson } from '../composables/useJson'

interface HomeStats {
  n_zones: number
  n_segments: number
  n_municipalities: number
  mean_suit_soybean: number
  top_zone: number
  top_zone_share_pct: number
}

const { data: stats, error, loading } = useJson<HomeStats>('json/home_stats.json')
</script>

<template>
  <section>
    <h1>Goiás Agro-Market Suitability &amp; CMIP6 Zoning</h1>
    <p>
      A 250 m atlas of biophysical potential for seven land-use segments across
      Goiás + DF (~340,000 km²), clustered into agro-environmental zones. FAO-style
      fuzzy membership + AHP weights &rarr; suitability; unsupervised clustering &rarr;
      zoning; delta-change CMIP6 &rarr; the future shift.
    </p>

    <nav class="rq-cards">
      <RouterLink to="/zoning" class="rq-card">
        <strong>RQ1</strong>
        <span>Zoning &amp; segmentation</span>
      </RouterLink>
      <RouterLink to="/municipal" class="rq-card">
        <strong>RQ2</strong>
        <span>Potential vs. realized</span>
      </RouterLink>
      <span class="rq-card disabled" title="CMIP6 forecast is being recomputed — not yet published here">
        <strong>RQ3</strong>
        <span>Forecast (coming soon)</span>
      </span>
    </nav>

    <MapPanel raster-path="zones_present.pmtiles">
      <template #legend>Agro-environmental zones (present)</template>
    </MapPanel>

    <p v-if="loading">loading stats…</p>
    <p v-else-if="error" role="alert">FAILED: {{ error.message }}</p>
    <div v-else-if="stats" class="stat-row">
      <StatChip label="zones" :value="stats.n_zones" />
      <StatChip label="segments" :value="stats.n_segments" />
      <StatChip label="municipalities" :value="stats.n_municipalities" />
      <StatChip label="mean soybean suitability" :value="stats.mean_suit_soybean.toFixed(2)" />
      <StatChip
        label="largest zone"
        :value="`Z${stats.top_zone} (${stats.top_zone_share_pct}%)`"
      />
    </div>
  </section>
</template>

<style scoped>
.rq-cards {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin-block: var(--space-4);
}

.rq-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
  text-decoration: none;
  color: var(--color-text);
  min-width: 160px;
}

.rq-card.disabled {
  color: var(--color-muted);
  cursor: default;
}

.stat-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin-block: var(--space-4);
}
</style>
