import type { Map as MapLibreMap, RasterSourceSpecification } from 'maplibre-gl'
import { onUnmounted, watch, type Ref } from 'vue'
import { dataUrl } from './useJson'
import { promoteMunicipalOverlay } from './useMunicipalOverlay'

/**
 * Add a raster PMTiles source+layer to a MapLibre map for the lifetime of the
 * calling component, reacting to `pmtilesPath`/`opacity` changes and removing
 * both cleanly on unmount. `map` may start `null` (MapPanel.vue's instance isn't
 * ready on the first tick) — the watcher re-attaches once it resolves.
 */
export function usePmtilesLayer(
  map: Ref<MapLibreMap | null>,
  layerId: string,
  pmtilesPath: Ref<string | null>,
  opacity: Ref<number>,
): void {
  function remove(): void {
    const m = map.value
    if (!m || !m.getStyle()) return
    if (m.getLayer(layerId)) m.removeLayer(layerId)
    if (m.getSource(layerId)) m.removeSource(layerId)
  }

  function addNow(m: MapLibreMap): void {
    remove()
    const source: RasterSourceSpecification = {
      type: 'raster',
      url: `pmtiles://${dataUrl(`pmtiles/${pmtilesPath.value}`)}`,
      tileSize: 256,
    }
    m.addSource(layerId, source)
    m.addLayer({
      id: layerId,
      type: 'raster',
      source: layerId,
      paint: { 'raster-opacity': opacity.value },
    })
    promoteMunicipalOverlay(m)
  }

  // A freshly-constructed maplibregl.Map's style loads asynchronously — calling
  // addSource/addLayer before it settles throws "Style is not done loading."
  // map.value is set (in MapPanel.vue's onMounted) well before that 'load' event
  // fires, so this watcher's first real (non-null) firing routinely races it.
  function add(): void {
    const m = map.value
    if (!m || !pmtilesPath.value) return
    if (m.isStyleLoaded()) {
      addNow(m)
    } else {
      m.once('load', () => addNow(m))
    }
  }

  watch([map, pmtilesPath], add, { immediate: true })
  watch(opacity, (v) => {
    const m = map.value
    if (m && m.getLayer(layerId)) m.setPaintProperty(layerId, 'raster-opacity', v)
  })

  onUnmounted(remove)
}
