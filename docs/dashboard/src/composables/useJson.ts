import { ref, shallowRef, toValue, watchEffect, type MaybeRefOrGetter, type Ref } from 'vue'

export interface AsyncData<T> {
  data: Ref<T | null>
  error: Ref<Error | null>
  loading: Ref<boolean>
  reload: () => Promise<void>
}

/**
 * Resolve a path relative to public/data/ into a URL that respects Vite's `base`
 * (e.g. 'json/hello.json' -> '/goias_suitability/data/json/hello.json').
 * Every data fetch in the app must go through this — never hard-code a leading '/'.
 */
export function dataUrl(path: string): string {
  return `${import.meta.env.BASE_URL}data/${path.replace(/^\/+/, '')}`
}

const jsonCache = new Map<string, unknown>()
const inFlight = new Map<string, Promise<unknown>>()

async function fetchJson(url: string): Promise<unknown> {
  const pending = inFlight.get(url)
  if (pending) return pending
  const promise = (async () => {
    const res = await fetch(url)
    if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${url}`)
    const parsed: unknown = await res.json()
    jsonCache.set(url, parsed)
    return parsed
  })().finally(() => inFlight.delete(url))
  inFlight.set(url, promise)
  return promise
}

/**
 * Typed fetch + module-level cache for a JSON file under public/data/. `path` may
 * be a plain string, a Ref, or a getter — when it resolves to a new value (e.g. a
 * path built from a selected segment), the fetch re-runs automatically.
 */
export function useJson<T>(path: MaybeRefOrGetter<string>): AsyncData<T> {
  // shallowRef, not ref: ref<T>() would apply UnwrapRef to an unconstrained generic,
  // which makes the returned type unassignable to Ref<T | null>.
  const data = shallowRef<T | null>(null)
  const error = ref<Error | null>(null)
  const loading = ref(false)
  let currentUrl = ''

  async function load(): Promise<void> {
    const url = dataUrl(toValue(path))
    currentUrl = url
    const cached = jsonCache.get(url)
    if (cached !== undefined) data.value = cached as T
    loading.value = cached === undefined
    error.value = null
    try {
      const result = (await fetchJson(url)) as T
      if (url === currentUrl) data.value = result
    } catch (e) {
      if (url === currentUrl) error.value = e instanceof Error ? e : new Error(String(e))
    } finally {
      if (url === currentUrl) loading.value = false
    }
  }

  watchEffect(load)
  return { data, error, loading, reload: load }
}
