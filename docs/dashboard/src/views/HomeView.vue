<script setup lang="ts">
import { computed } from 'vue'
import MapLegend from '../components/MapLegend.vue'
import MapPanel from '../components/MapPanel.vue'
import StatChip from '../components/StatChip.vue'
import { useJson } from '../composables/useJson'
import { useManifest } from '../composables/useManifest'
import { fmtInt, fmtKm2, fmtNum, fmtPct, fmtSigned, fmtRange } from '../format'
import { zoneLegend } from '../legends'
import type { HomeStats } from '../types/data'

const { data: stats, error, loading } = useJson<HomeStats>('json/home_stats.json')
const { manifest, zones, zoneName, zoneVocation, segmentLabel, scenarioLabel } = useManifest()

// No literal fallback: the zone count is whatever the manifest reports. A hardcoded
// default once rendered a legend for 10 zones long after the zoning moved to 4.
const legend = computed(() =>
  zones.value.length
    ? zoneLegend(zones.value.length, Object.fromEntries(zones.value.map((z) => [z.zone, zoneVocation(z.zone)])))
    : null,
)

const horizon = computed(() => {
  const w = manifest.value?.windows ?? []
  return w.length ? fmtRange(w[0]!.start, w[w.length - 1]!.end) : ''
})
</script>

<template>
  <section>
    <h1>Atlas de aptidão multissegmento e zoneamento agroambiental de GO e DF</h1>
    <p v-if="manifest" class="lede">
      Potencial biofísico e agroclimático de cada célula de {{ manifest.grid_m }}&nbsp;m de Goiás e do
      Distrito Federal ({{ fmtKm2(manifest.aoi.area_km2) }}, bioma Cerrado) para
      {{ manifest.segments.length }} segmentos de uso da terra. A aptidão é obtida por avaliação
      multicritério nos moldes da FAO (pertinência <em>fuzzy</em> e ponderação AHP); o território é
      particionado em {{ manifest.zones.length }} zonas agroambientais por agrupamento não
      supervisionado; e a mudança de aptidão é projetada para {{ horizon }} sob
      {{ manifest.ssps.length }} cenários CMIP6, com um conjunto de {{ manifest.gcms.length }} modelos
      climáticos globais. O atlas acompanha a dissertação e expande os seus resultados.
    </p>

    <nav class="rq-cards" aria-label="Questões de pesquisa">
      <RouterLink to="/zoning" class="rq-card">
        <strong>QP1</strong>
        <span>Aptidão e zoneamento agroambiental</span>
      </RouterLink>
      <RouterLink to="/realized-use" class="rq-card">
        <strong>QP2</strong>
        <span>Potencial <em>versus</em> uso atual da terra</span>
      </RouterLink>
      <RouterLink to="/cmip6" class="rq-card">
        <strong>QP3</strong>
        <span>Mudança projetada pelo clima</span>
      </RouterLink>
    </nav>

    <MapPanel raster-path="zones_present.pmtiles">
      <template #legend><MapLegend v-if="legend" :spec="legend" /></template>
    </MapPanel>

    <p v-if="loading">Carregando indicadores…</p>
    <p v-else-if="error" role="alert">Não foi possível carregar os indicadores: {{ error.message }}</p>
    <div v-else-if="stats" class="stat-row">
      <StatChip label="zonas agroambientais" :value="stats.n_zones" />
      <StatChip label="segmentos" :value="stats.n_segments" />
      <StatChip label="municípios (incl. DF)" :value="fmtInt(stats.n_municipalities)" />
      <StatChip
        label="aptidão média municipal — soja"
        :value="fmtNum(stats.mean_suit_soybean, 2)"
        hint="Média, entre os municípios, da aptidão média da soja (0–1)"
      />
      <StatChip
        :label="`maior zona: ${zoneName(stats.top_zone) || `Zona ${stats.top_zone}`}`"
        :value="`Zona ${stats.top_zone} · ${fmtPct(stats.top_zone_share_pct)}`"
        hint="Parcela da área de GO e DF (área de pixel, não contagem amostral)"
      />
      <StatChip
        v-if="stats.underused_soybean_pct !== null"
        label="terra apta à soja e sem soja"
        :value="fmtPct(stats.underused_soybean_pct)"
        hint="Classe S2 ou melhor para a soja, sem soja no uso atual (MapBiomas)"
      />
      <StatChip
        v-if="stats.auc_soybean !== null"
        label="AUC — soja (metade de validação)"
        :value="fmtNum(stats.auc_soybean, 3)"
      />
      <StatChip
        v-if="stats.kappa_soybean !== null"
        label="κ de Cohen — floresta aleatória × aptidão"
        :value="fmtNum(stats.kappa_soybean, 3)"
        hint="Verificação cruzada orientada por dados, soja, metade de validação"
      />
      <StatChip
        :label="`maior perda média de aptidão: ${segmentLabel(stats.worst_delta.segment)} (${scenarioLabel(stats.worst_delta.ssp, stats.worst_delta.window)})`"
        :value="`ΔS ${fmtSigned(stats.worst_delta.delta_s, 4)}`"
      />
    </div>
  </section>
</template>

<style scoped>
.lede {
  max-width: 80ch;
}

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

.stat-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin-block: var(--space-4);
}
</style>
