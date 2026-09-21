<script setup lang="ts">
import * as maplibregl from 'maplibre-gl'
import type { LngLatLike, MapGeoJSONFeature, MapLayerMouseEvent } from 'maplibre-gl'
import { computed, onMounted, onUnmounted, ref, shallowRef, watch } from 'vue'
import { dataUrl } from '../composables/useJson'
import { usePmtilesLayer } from '../composables/useMapLayer'
import { promoteMunicipalOverlay, useMunicipalOverlay } from '../composables/useMunicipalOverlay'

export interface ChoroplethLayer {
  /** Path under public/data/geojson/, e.g. 'municipal_ranking.geojson'. */
  path: string
  /** GeoJSON property to color by. */
  property: string
  /** [value, color] stops for a MapLibre `interpolate`/`step` fill expression. */
  stops: [number, string][]
}

const props = withDefaults(
  defineProps<{
    /** PMTiles filename under public/data/pmtiles/, without the directory. */
    rasterPath?: string | null
    rasterOpacity?: number
    choropleth?: ChoroplethLayer | null
    /** Show the AOI boundary as a thin outline for context. */
    outline?: boolean
    /** NM_MUN of a municipality to draw thicker/accented on the boundary overlay. */
    highlightMunicipality?: string | null
    center?: LngLatLike
    zoom?: number
  }>(),
  {
    rasterPath: null,
    rasterOpacity: 0.85,
    choropleth: null,
    outline: true,
    highlightMunicipality: null,
    // AOI centroid + a zoom that fits ~340,000 km2 of Goias/DF in a ~4:3 panel.
    center: () => [-49.6, -15.95] as LngLatLike,
    zoom: 5.4,
  },
)

const emit = defineEmits<{ 'feature-click': [properties: Record<string, unknown>] }>()

const container = ref<HTMLDivElement | null>(null)
const map = shallowRef<maplibregl.Map | null>(null)
let resizeObserver: ResizeObserver | null = null

const rasterPathRef = ref(props.rasterPath)
const opacityRef = ref(props.rasterOpacity)
watch(() => props.rasterPath, (v) => (rasterPathRef.value = v))
watch(() => props.rasterOpacity, (v) => (opacityRef.value = v))
usePmtilesLayer(map, 'hero-raster', rasterPathRef, opacityRef)
useMunicipalOverlay(map, computed(() => props.highlightMunicipality))

const CHOROPLETH_SOURCE = 'choropleth'
const OUTLINE_SOURCE = 'aoi-outline'

function buildFillExpression(layer: ChoroplethLayer): maplibregl.ExpressionSpecification {
  const expr: unknown[] = ['interpolate', ['linear'], ['get', layer.property]]
  for (const [value, color] of layer.stops) expr.push(value, color)
  return expr as maplibregl.ExpressionSpecification
}

function addChoropleth(): void {
  const m = map.value
  if (!m || !m.getStyle() || !props.choropleth) return
  if (m.getLayer(CHOROPLETH_SOURCE)) m.removeLayer(CHOROPLETH_SOURCE)
  if (m.getLayer(`${CHOROPLETH_SOURCE}-line`)) m.removeLayer(`${CHOROPLETH_SOURCE}-line`)
  if (m.getSource(CHOROPLETH_SOURCE)) m.removeSource(CHOROPLETH_SOURCE)

  m.addSource(CHOROPLETH_SOURCE, { type: 'geojson', data: dataUrl(`geojson/${props.choropleth.path}`) })
  m.addLayer({
    id: CHOROPLETH_SOURCE,
    type: 'fill',
    source: CHOROPLETH_SOURCE,
    paint: { 'fill-color': buildFillExpression(props.choropleth), 'fill-opacity': 0.85 },
  })
  m.addLayer({
    id: `${CHOROPLETH_SOURCE}-line`,
    type: 'line',
    source: CHOROPLETH_SOURCE,
    paint: { 'line-color': '#ffffff', 'line-width': 0.4 },
  })
  promoteMunicipalOverlay(m)
}

function addOutline(): void {
  const m = map.value
  console.log('DEBUG addOutline', !!m, !!m?.getStyle(), props.outline)
  if (!m || !m.getStyle() || !props.outline) return
  if (m.getLayer(OUTLINE_SOURCE)) m.removeLayer(OUTLINE_SOURCE)
  if (m.getSource(OUTLINE_SOURCE)) m.removeSource(OUTLINE_SOURCE)
  try {
    console.log('DEBUG addSource url', dataUrl('geojson/aoi.geojson'))
    m.addSource(OUTLINE_SOURCE, { type: 'geojson', data: dataUrl('geojson/aoi.geojson') })
    m.addLayer({
      id: OUTLINE_SOURCE,
      type: 'line',
      source: OUTLINE_SOURCE,
      paint: { 'line-color': '#1b1f1a', 'line-width': 1.2 },
    })
    console.log('DEBUG addOutline done', m.getSource(OUTLINE_SOURCE))
    promoteMunicipalOverlay(m)
  } catch (e) {
    console.log('DEBUG addOutline threw', e)
  }
}

onMounted(() => {
  if (!container.value) return
  const m = new maplibregl.Map({
    container: container.value,
    style: {
      version: 8,
      sources: {},
      layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#eef1ec' } }],
    },
    center: props.center,
    zoom: props.zoom,
  })
  m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
  m.on('error', (e) => console.log('DEBUG map error', e.error?.message ?? e))
  m.on('sourcedata', (e) => {
    if (e.sourceId === OUTLINE_SOURCE) console.log('DEBUG sourcedata aoi-outline', e.isSourceLoaded, e.sourceDataType)
  })
  m.on('load', () => {
    console.log('DEBUG load fired', props.outline, props.choropleth)
    addOutline()
    addChoropleth()
  })
  m.on('click', CHOROPLETH_SOURCE, (e: MapLayerMouseEvent) => {
    const feature = e.features?.[0] as MapGeoJSONFeature | undefined
    if (feature?.properties) emit('feature-click', feature.properties)
  })
  m.on('mouseenter', CHOROPLETH_SOURCE, () => (m.getCanvas().style.cursor = 'pointer'))
  m.on('mouseleave', CHOROPLETH_SOURCE, () => (m.getCanvas().style.cursor = ''))
  map.value = m

  // The sidebar's collapse/expand animates .app-main's width without a window
  // resize event firing — MapLibre only auto-resizes on the latter, so without
  // this the canvas keeps its stale size (and a stale center point) after a toggle.
  resizeObserver = new ResizeObserver(() => m.resize())
  resizeObserver.observe(container.value)
})

watch(() => props.choropleth, addChoropleth)

onUnmounted(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
  map.value?.remove()
  map.value = null
})
</script>

<template>
  <div class="map-panel-wrap">
    <div class="map-panel">
      <div ref="container" class="map-panel-canvas" />
    </div>
    <div v-if="$slots.legend" class="map-panel-legend">
      <slot name="legend" />
    </div>
  </div>
</template>

<style scoped>
.map-panel-wrap {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.map-panel {
  position: relative;
  width: 100%;
  height: 420px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  overflow: hidden;
}

.map-panel-canvas {
  width: 100%;
  height: 100%;
}

/* The legend lives outside the map canvas (not overlaid on it) so it never
   obscures the choropleth/raster it describes, per the dashboard's map-reading
   requirement — it renders below the map, full width. */
.map-panel-legend {
  width: 100%;
}
</style>
