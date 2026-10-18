<script setup lang="ts">
import type { Data as PlotlyDatum } from 'plotly.js'
import { computed } from 'vue'
import { useManifest } from '../composables/useManifest'
import { fmtNum, fmtPct, fmtShare } from '../format'
import type { ZoneProfileRow } from '../types/data'
import PlotlyChart from './PlotlyChart.vue'

const props = defineProps<{ profile: ZoneProfileRow }>()

// Name, vocation, area share and the pair rule all come from manifest.json:
//  - the area share is a pixelArea() group reduce (zone_area.csv), NOT profile.n,
//    which counts rows of a stratified sample (CLAUDE.md §9);
//  - `paired` applies ZONE_PAIR_MARGIN from tools/palettes.py, the same constant
//    fig_4_3's legend uses, so atlas and thesis read a zone the same way.
const { manifest, zone, zoneName, segmentKeys, segmentLabel, segmentShort } = useManifest()
const meta = computed(() => zone(props.profile.zone))

const vocation = computed(() => {
  const m = meta.value
  if (!m) return ''
  return m.paired
    ? `${segmentShort(m.comparative_segment)} / ${segmentShort(m.comparative_segment_2)}`
    : segmentShort(m.comparative_segment)
})

const barData = computed<PlotlyDatum[]>(() => {
  const keys = segmentKeys.value
  return [
    {
      type: 'bar',
      orientation: 'h',
      x: keys.map((s) => Number(props.profile[`suit_${s}`] ?? 0)),
      y: keys.map(segmentLabel),
      text: keys.map((s) => fmtNum(Number(props.profile[`suit_${s}`] ?? 0), 2)),
      textposition: 'outside',
      cliponaxis: false,
      hoverinfo: 'y+text',
    },
  ]
})

// rl_<role>_frac columns present in zone_profiles.csv, labelled from manifest.realized_bands
const realizedFracs = computed(() =>
  Object.entries(manifest.value?.realized_bands ?? {})
    .filter(([band]) => band in props.profile)
    .map(([band, label]) => ({ band, label, frac: Number(props.profile[band] ?? 0) }))
    .filter((r) => r.frac > 0)
    .sort((a, b) => b.frac - a.frac),
)
</script>

<template>
  <div class="zone-card">
    <h3>Zona {{ profile.zone }}<template v-if="zoneName(profile.zone)"> — {{ zoneName(profile.zone) }}</template></h3>
    <p v-if="meta" class="zone-meta">
      Vocação comparativa: <strong>{{ vocation }}</strong>
      (margem z = {{ fmtNum(meta.comparative_margin, 2) }})
      &middot; {{ fmtPct(meta.share_pct) }} do território
      &middot; elevação média {{ fmtNum(meta.mean_elev_m, 0) }} m
    </p>
    <p v-if="meta?.paired" class="zone-note">
      A margem entre os dois primeiros segmentos é inferior a
      {{ fmtNum(manifest?.zone_pair_margin, 2) }}: a zona deve ser lida como um par de usos, e
      não por um rótulo único.
    </p>
    <PlotlyChart
      :data="barData"
      :layout="{
        height: 320,
        margin: { l: 160 },
        yaxis: { dtick: 1 },
        xaxis: { title: { text: 'aptidão média na zona (0–1)' }, range: [0, 1] },
      }"
    />
    <p class="zone-realized">
      Uso atual da terra:
      <span v-for="(r, i) in realizedFracs" :key="r.band">
        {{ r.label.toLowerCase() }} {{ fmtShare(r.frac) }}<template v-if="i < realizedFracs.length - 1">; </template>
      </span>
    </p>
  </div>
</template>

<style scoped>
.zone-card {
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  padding: var(--space-3);
  background: var(--color-surface);
}

.zone-meta {
  color: var(--color-muted);
  font-size: 0.875rem;
}

.zone-realized {
  font-size: 0.8rem;
  color: var(--color-muted);
}

.zone-note {
  font-size: 0.8rem;
  color: var(--color-muted);
  font-style: italic;
}
</style>
