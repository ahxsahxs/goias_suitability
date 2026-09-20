import type { Map as MapLibreMap, RasterSourceSpecification } from 'maplibre-gl'
import { onUnmounted, watch, type Ref } from 'vue'
import { dataUrl } from './useJson'

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

  function add(): void {
    const m = map.value
    if (!m || !pmtilesPath.value) return
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
  }

  watch([map, pmtilesPath], add, { immediate: true })
  watch(opacity, (v) => {
    const m = map.value
    if (m && m.getLayer(layerId)) m.setPaintProperty(layerId, 'raster-opacity', v)
  })

  onUnmounted(remove)
}
