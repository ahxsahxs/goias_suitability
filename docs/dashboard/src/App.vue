<script setup lang="ts">
import { RouterView } from 'vue-router'
import AppSidebar from './components/AppSidebar.vue'
import { useManifest } from './composables/useManifest'

// Build provenance: when the data files were generated and from which commit.
const { manifest } = useManifest()
</script>

<template>
  <div class="app">
    <AppSidebar />

    <div class="app-content">
      <main class="app-main">
        <RouterView />
      </main>

      <footer class="app-footer">
        <span v-if="manifest">
          Dados gerados em {{ new Date(`${manifest.generated_at}T12:00`).toLocaleDateString('pt-BR')
          }}<template v-if="manifest.git_sha"> (commit <code>{{ manifest.git_sha }}</code>)</template>
        </span>
        <a href="https://github.com/ahxsahxs/goias_suitability">Repositório <code>goias_suitability</code></a>
      </footer>
    </div>
  </div>
</template>
