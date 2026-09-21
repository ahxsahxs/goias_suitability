<script setup lang="ts"></script>

<template>
  <section>
    <h1>Sobre este Atlas</h1>

    <h2>O que é</h2>
    <p>
      Um atlas de aptidão territorial multicritério nos moldes da FAO, totalmente
      executado no Google Earth Engine, com zoneamento agroambiental de Goiás +
      Distrito Federal (~340.000 km², bioma Cerrado), para sete segmentos de uso da
      terra: soja, cana-de-açúcar, outras culturas anuais, piscicultura, pecuária,
      conservação de floresta &amp; Cerrado, e geração fotovoltaica. Cada célula de
      250 m recebe um escore de aptidão por pertinência fuzzy + pesos AHP, o
      território é agrupado em zonas agroambientais, e toda a superfície é projetada
      para 2031-2070 sob dois cenários CMIP6 (método dos fatores de mudança, conjunto
      de 5 GCMs). Validado contra o uso realizado da terra (MapBiomas) e um indicador
      de produtividade MODIS MOD17.
    </p>

    <h2>O que não é</h2>
    <p>
      Não é um modelo de produtividade, não é um modelo econômico, e não substitui a
      diligência prévia em campo. A aptidão reflete apenas o potencial
      biofísico/agroclimático — não precifica terra, acesso a crédito, posse
      fundiária ou logística, fatores que moldam onde a terra é de fato convertida.
    </p>

    <h2>Guardrails</h2>
    <ul>
      <li>
        <strong>Cobertura da terra é apenas máscara/contexto, nunca uma entrada de
        aptidão ou de agrupamento.</strong> Usar o uso realizado da terra para prever
        o uso da terra seria circular; a única exceção sancionada é uma fração
        rebaixada de cobertura nativa dentro do segmento de conservação.
      </li>
      <li>
        <strong>Conservação agrega pela média aritmética ponderada
        (compensatória)</strong>, não pela média geométrica ponderada usada pelos
        outros seis segmentos — é um índice de valor/prioridade (distância a UCs,
        rugosidade, carbono), não uma aptidão de fator limitante.
      </li>
      <li>
        <strong>Zonas são rotuladas por <code>comparative_segment</code></strong>
        &mdash; o argmax da aptidão z-normalizada de cada segmento &mdash; não pela
        dominância bruta, já que a pecuária deixou de vencer o argmax absoluto em
        toda parte após a recalibração de forragem.
      </li>
      <li>
        <strong>O zoneamento roda KMeans do sklearn offline</strong> sobre uma
        entrada PCA descorrelacionada, classificado no servidor por matemática de
        banda do centróide mais próximo; o agrupamento bruto de 34 bandas colapsa
        para poucas zonas de baixa expressividade.
      </li>
      <li>
        <strong>O clima é mais grosseiro que tudo o mais</strong> (~4,6 km do
        TerraClimate vs. 250 m de relevo/solo) &mdash; ver Pilha de Atributos e a
        análise de descompasso de escala da dissertação; a variabilidade local de
        relevo+solo é de 42x a 320x a do clima mesmo na escala nativa do próprio
        TerraClimate.
      </li>
    </ul>

    <h2>Proveniência dos dados &amp; citação</h2>
    <p>
      Construído inteiramente no lado do servidor no Google Earth Engine (nível de
      pesquisa) a partir de conjuntos de dados públicos do catálogo, além da Malha
      Municipal Digital 2025 oficial do IBGE (a única entrada local, fora do EE,
      carregada no lado do cliente a cada execução &mdash; nunca enviada como um
      asset persistente). Ver Área de Estudo para o catálogo completo de dados.
    </p>

    <h2>Dissertação completa &amp; código-fonte</h2>
    <p>
      <a href="https://github.com/ahxsahxs/goias_suitability">Repositório</a>
      (inclui o código-fonte completo da dissertação em LaTeX em <code>thesis/</code>).
    </p>
  </section>
</template>
