<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { NAV_ICONS } from '../icons'
import { navSections } from '../router'

const MOBILE_BREAKPOINT = 720
const STORAGE_KEY = 'sidebar-collapsed'

const collapsed = ref(false)

onMounted(() => {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored !== null) {
      collapsed.value = stored === '1'
      return
    }
  } catch {
    // private mode / storage blocked — fall through to the viewport default
  }
  collapsed.value = window.innerWidth <= MOBILE_BREAKPOINT
})

watch(collapsed, (v) => {
  try {
    localStorage.setItem(STORAGE_KEY, v ? '1' : '0')
  } catch {
    // ignore — collapse state just won't persist this session
  }
})

function toggle(): void {
  collapsed.value = !collapsed.value
}

function closeOnMobile(): void {
  if (window.innerWidth <= MOBILE_BREAKPOINT) collapsed.value = true
}
</script>

<template>
  <aside class="app-sidebar" :class="{ collapsed }">
    <div class="sidebar-header">
      <button
        type="button"
        class="sidebar-toggle"
        :aria-label="collapsed ? 'Expandir navegação' : 'Recolher navegação'"
        :aria-expanded="!collapsed"
        @click="toggle"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" v-html="NAV_ICONS.toggle" />
      </button>
      <RouterLink to="/" class="brand" title="Início" @click="closeOnMobile">
        <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" v-html="NAV_ICONS.home" />
        <span class="brand-text">Atlas de Viabilidade<br/>de Goiás</span>
      </RouterLink>
    </div>

    <nav class="sidebar-nav" aria-label="Navegação principal">
      <div v-for="section in navSections" :key="section.title" class="nav-section">
        <span class="nav-section-title">{{ section.title }}</span>
        <ul>
          <li v-for="item in section.items" :key="item.path">
            <RouterLink
              v-if="item.enabled"
              :to="item.path"
              :title="`${item.label} — ${item.part}`"
              class="nav-link"
              @click="closeOnMobile"
            >
              <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" v-html="NAV_ICONS[item.path]" />
              <span class="nav-label">{{ item.label }}</span>
            </RouterLink>
            <span v-else class="nav-link nav-disabled" :title="`${item.label} — ${item.part} — ainda não construído`">
              <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" v-html="NAV_ICONS[item.path]" />
              <span class="nav-label">{{ item.label }}</span>
            </span>
          </li>
        </ul>
      </div>
    </nav>
  </aside>
  <div class="sidebar-backdrop" @click="collapsed = true" />
</template>

<style scoped>
.app-sidebar {
  display: flex;
  flex-direction: column;
  width: var(--sidebar-w);
  flex-shrink: 0;
  border-right: 1px solid var(--color-border);
  background: var(--color-surface);
  overflow-x: hidden;
  overflow-y: auto;
  transition: width 0.15s ease;
}

.app-sidebar.collapsed {
  width: var(--sidebar-w-collapsed);
}

.sidebar-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-2);
  border-bottom: 1px solid var(--color-border);
}

.sidebar-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  border: none;
  background: transparent;
  color: var(--color-text);
  cursor: pointer;
  border-radius: var(--radius);
}

.sidebar-toggle:hover {
  background: var(--color-border);
}

.sidebar-toggle svg {
  width: 20px;
  height: 20px;
}

.brand {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
  text-decoration: none;
  color: var(--color-text);
  font-weight: 700;
}

.brand-text {
  white-space: nowrap;
  overflow: hidden;
}

.collapsed .brand-text {
  display: none;
}

.sidebar-nav {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-2);
}

.nav-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

.nav-section-title {
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--color-muted);
  padding-inline: var(--space-2);
  white-space: nowrap;
}

.collapsed .nav-section-title {
  display: none;
}

.nav-section ul {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  margin: 0;
  padding: 0;
  list-style: none;
}

.nav-link {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius);
  text-decoration: none;
  color: var(--color-text);
  white-space: nowrap;
}

.nav-link:hover {
  background: var(--color-border);
}

.nav-link.router-link-active {
  background: var(--color-accent);
  color: #ffffff;
}

.nav-disabled {
  color: var(--color-muted);
  cursor: default;
}

.nav-disabled:hover {
  background: transparent;
}

.nav-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
}

.collapsed .nav-label {
  display: none;
}

.sidebar-backdrop {
  display: none;
}

@media (max-width: 720px) {
  .app-sidebar {
    position: fixed;
    inset: 0 auto 0 0;
    z-index: 50;
    height: 100%;
  }

  .app-sidebar:not(.collapsed) {
    box-shadow: 2px 0 12px rgba(0, 0, 0, 0.15);
  }

  .app-sidebar:not(.collapsed) ~ .sidebar-backdrop {
    display: block;
    position: fixed;
    inset: 0;
    z-index: 40;
    background: rgba(0, 0, 0, 0.3);
  }
}
</style>
