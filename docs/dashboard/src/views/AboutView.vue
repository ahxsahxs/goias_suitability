<script setup lang="ts">
import { computed } from 'vue'
import { useManifest } from '../composables/useManifest'
import { fmtKm2, fmtRange } from '../format'

const { manifest } = useManifest()
const segmentList = computed(() => {
  const s = (manifest.value?.segments ?? []).map((x) => x.label.toLowerCase())
  return s.length > 1 ? `${s.slice(0, -1).join(', ')} e ${s[s.length - 1]}` : (s[0] ?? '')
})
const horizon = computed(() => {
  const w = manifest.value?.windows ?? []
  return w.length ? fmtRange(w[0]!.start, w[w.length - 1]!.end) : ''
})
</script>

<template>
  <section v-if="manifest" class="about">
    <h1>Sobre o atlas</h1>

    <h2>Objeto</h2>
    <p>
      Este atlas interativo acompanha a dissertação e expande os seus resultados. Ele mapeia o
      potencial biofísico e agroclimático de Goiás e do Distrito Federal
      ({{ fmtKm2(manifest.aoi.area_km2) }}, bioma Cerrado), em grade de {{ manifest.grid_m }}&nbsp;m,
      para {{ manifest.segments.length }} segmentos de uso da terra: {{ segmentList }}. A aptidão é
      obtida por avaliação multicritério nos moldes da FAO; o território é particionado em
      {{ manifest.zones.length }} zonas agroambientais; e a mudança de aptidão é projetada para
      {{ horizon }} sob {{ manifest.ssps.length }} cenários CMIP6, com {{ manifest.gcms.length }} modelos
      climáticos globais. Os resultados são confrontados com o uso atual da terra (MapBiomas) e com a
      produtividade observada pelo MODIS MOD17.
    </p>

    <h2>Limites de interpretação</h2>
    <p>
      A aptidão expressa apenas o potencial biofísico e agroclimático. O atlas não é um modelo de
      produtividade nem um modelo econômico: não considera preço da terra, crédito, situação
      fundiária ou logística, fatores que condicionam onde a terra é de fato convertida, e não
      substitui a avaliação em campo.
    </p>

    <h2>Salvaguardas metodológicas</h2>
    <ul>
      <li>
        <strong>A cobertura e o uso da terra nunca são variáveis de entrada</strong> da aptidão ou do
        agrupamento, apenas máscara, validação e descrição, pois usar o uso da terra para prever o uso
        da terra seria circular. A única exceção é a fração de vegetação nativa, que entra com peso
        reduzido no índice de conservação.
      </li>
      <li>
        <strong>A conservação é um índice de valor</strong> (distância a áreas protegidas,
        rugosidade, carbono da biomassa), agregado pela média aritmética ponderada (compensatória);
        os demais segmentos usam a média geométrica ponderada, em que um fator limitante não é
        compensado pelos demais.
      </li>
      <li>
        <strong>Os pesos são derivados, e não arbitrados:</strong> a prioridade da literatura (AHP) é
        ajustada pelo poder discriminante regional de cada fator, medido na metade de calibração da
        partição espacial. As métricas de validação são medidas na outra metade.
      </li>
      <li>
        <strong>O zoneamento é um dispositivo de partição.</strong> O <em>k</em>-médias opera sobre
        {{ manifest.stack.n_zoning_bands }} das {{ manifest.stack.total_bands }} bandas, ponderadas por
        tema e descorrelacionadas; as zonas são rotuladas pelo melhor segmento comparativo (aptidão
        padronizada por escore <em>z</em>), não pela aptidão absoluta.
      </li>
    </ul>

    <h2>Proveniência e reprodutibilidade</h2>
    <p>
      Todo o processamento é feito no Google Earth Engine a partir de conjuntos de dados públicos do
      catálogo; a única entrada local é a Malha Municipal Digital do IBGE, carregada em memória a cada
      execução. Os arquivos deste atlas são gerados pelo próprio <em>pipeline</em>
      (<code>tools/build_dashboard_assets.py</code>), e cada número exibido vem desses arquivos.
      O catálogo de dados está em <RouterLink to="/study-area">Área de estudo e dados</RouterLink>.
    </p>

    <h2>Código-fonte e dissertação</h2>
    <p>
      O código-fonte completo (configurações, módulos de análise, ferramentas de exportação e o texto
      da dissertação em LaTeX) está disponível no repositório
      <a href="https://github.com/ahxsahxs/goias_suitability"><code>goias_suitability</code></a>.
    </p>
  </section>
</template>

<style scoped>
.about {
  max-width: 80ch;
}
</style>
