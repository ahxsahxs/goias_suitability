<script setup lang="ts">
import { RouterView } from 'vue-router'
import AppSidebar from './components/AppSidebar.vue'

const baseUrl = import.meta.env.BASE_URL
</script>

<template>
  <div class="app">
    <AppSidebar />

    <div class="app-content">
      <main class="app-main">
        <RouterView />
      </main>

      <footer class="app-footer">
        <span>v2</span>
        <span>base: <code>{{ baseUrl }}</code></span>
        <a href="https://github.com/ahxsahxs/goias_suitability">Repositório</a>
      </footer>
    </div>
  </div>
</template>
