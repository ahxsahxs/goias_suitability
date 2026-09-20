import { parse } from 'papaparse'
import { ref, shallowRef, toValue, watchEffect, type MaybeRefOrGetter } from 'vue'
import { dataUrl, type AsyncData } from './useJson'

export interface UseCsvOptions {
  /** Coerce numeric/boolean-looking cells (Papaparse `dynamicTyping`). Default true. */
  dynamicTyping?: boolean
}

const csvCache = new Map<string, unknown[]>()

/**
 * Typed fetch + Papaparse header-mode parse of a CSV under public/data/. `path`
 * may be a plain string, a Ref, or a getter (see useJson for the reactive case).
 */
export function useCsv<T extends object>(
  path: MaybeRefOrGetter<string>,
  options: UseCsvOptions = {},
): AsyncData<T[]> {
  const data = shallowRef<T[] | null>(null)
  const error = ref<Error | null>(null)
  const loading = ref(false)
  let currentUrl = ''

  async function load(): Promise<void> {
    const url = dataUrl(toValue(path))
    currentUrl = url
    const cached = csvCache.get(url)
    if (cached) data.value = cached as T[]
    loading.value = !cached
    error.value = null
    try {
      const res = await fetch(url)
      if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${url}`)
      const text = await res.text()
      const result = parse<T>(text, {
        header: true,
        skipEmptyLines: true,
        dynamicTyping: options.dynamicTyping ?? true,
      })
      if (result.errors.length > 0) {
        const first = result.errors[0]
        throw new Error(`CSV parse error in ${url}: ${first?.message ?? 'unknown'} (row ${first?.row ?? '?'})`)
      }
      csvCache.set(url, result.data)
      if (url === currentUrl) data.value = result.data
    } catch (e) {
      if (url === currentUrl) error.value = e instanceof Error ? e : new Error(String(e))
    } finally {
      if (url === currentUrl) loading.value = false
    }
  }

  watchEffect(load)
  return { data, error, loading, reload: load }
}
