<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
import { navSections } from './router'

const baseUrl = import.meta.env.BASE_URL
</script>

<template>
  <div class="app">
    <header class="app-header">
      <RouterLink to="/" class="brand">Atlas de Aptidão de Goiás</RouterLink>
      <nav class="app-nav" aria-label="Navegação principal">
        <div v-for="section in navSections" :key="section.title" class="nav-section">
          <span class="nav-section-title">{{ section.title }}</span>
          <ul>
            <li v-for="item in section.items" :key="item.path">
              <RouterLink v-if="item.enabled" :to="item.path" :title="item.part">
                {{ item.label }}
              </RouterLink>
              <span v-else class="nav-disabled" :title="`${item.part} — ainda não construído`">
                {{ item.label }}
              </span>
            </li>
          </ul>
        </div>
      </nav>
    </header>

    <main class="app-main">
      <RouterView />
    </main>

    <footer class="app-footer">
      <span>v2</span>
      <span>base: <code>{{ baseUrl }}</code></span>
      <a href="https://github.com/ahxsahxs/goias_suitability">Repositório</a>
    </footer>
  </div>
</template>
