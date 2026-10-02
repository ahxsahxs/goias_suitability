# Travessia literatura ⇄ pesos AHP

Documento de referência da derivação dos pesos AHP do Capítulo 3. Registra, por segmento, de onde
vem cada julgamento par a par, qual critério da fonte corresponde a cada fator do modelo, e quais
critérios da literatura **não** têm correspondente aqui — e por quê.

A cadeia de derivação é:

```
julgamentos par a par (este documento, config/ahp_matrices.yaml)
      │  tools/derive_weights.py  → autovetor principal, λmax, CI, RI, RC
      ▼
   w_lit                       prior da literatura, por segmento
      │  × d^λ                 d = σ(μ) sobre a terra disponível em GO/DF;  λ = 0,5
      ▼
   w final                     escrito em config/segments.yaml
```

A direção importa. A ponderação **não** parte de pesos escolhidos e depois monta uma matriz que os
reproduza; parte dos julgamentos e chega aos pesos. A adaptação regional é um segundo estágio,
declarado e separável, não uma correção embutida no primeiro.

---

## 1. Protocolo anti-circularidade

Uma matriz de comparação par a par com *n* fatores tem n(n−1)/2 células livres. Se o autor puder
escolher todas elas tendo em mãos um vetor de pesos desejado, a "elicitação" é apenas uma maneira
mais elaborada de escrever o vetor que já se queria — e a razão de consistência resultante mede o
cuidado da reconstrução, não a coerência do julgamento. É exatamente o que acontecia na iteração
anterior deste trabalho, em que a matriz era gerada a partir dos pesos e a RC saía na ordem de
10⁻³.

A correção não é de intenção, é de **graus de liberdade**. O autor escolhe *n* valores ordinais por
segmento — não n(n−1)/2 reais — e cada célula `a_ij` é função determinística de entradas
declaradas, que o código recomputa e confere.

### R1 — Duas camadas de entrada

`config/ahp_matrices.yaml` traz, por segmento:

- **`anchors:`** — uma entrada por fator, com:
  - `band:` (1–4), a faixa ordinal de importância, **sempre** presente;
  - `r:`, `source:`, `locator:`, `block:` quando o fator corresponde a um critério publicado;
  - `rationale:` justificando a faixa.
- **`judgements:`** — uma entrada por par, com a regra (`A`/`B`/`C`) que a produziu.

Nenhum julgamento pode existir para fatores sem entrada em `anchors`.

### R2 — Escala admissível

`a_ij ∈ {1,…,9} ∪ {1/2,…,1/9}`. Somente a escala inteira de Saaty e seus recíprocos. Os passos
intermediários 1,25 / 1,75 / 2,5 / 3,5 usados na iteração anterior são rejeitados pelo validador:
o texto declara "escala 1–9" e a matriz precisa ser isso. Essa restrição sozinha impede a matriz de
reproduzir um vetor arbitrário.

### R3 — Classe A: ambos os fatores ancorados na mesma fonte e no mesmo bloco

`a_ij = snap(r_i / r_j)`, com `snap` levando ao ponto mais próximo da escala de R2 em espaço
logarítmico, truncado em 9. O código recomputa e falha se o valor armazenado divergir.

Não é circular: `r` é publicado, externo, e o autor não pode alterá-lo.

**Pares entre fontes distintas — ou entre blocos distintos da mesma fonte — não são classe A.**
Prioridades de conjuntos de critérios diferentes são normalizadas sobre conjuntos diferentes; sua
razão não tem significado. Radočaj, por exemplo, publica *duas* matrizes independentes (clima e
solo), então `soil_ph`×`clim_pr_annual` cai na regra R4, não na R3.

### R4 — Classes B e C: faixas ordinais

Quando apenas um fator está ancorado (**B**) ou nenhum (**C**):

```
Δ_ij = band_j − band_i          (faixa 1 = mais importante, 4 = menos)
Δ =  0 → a_ij = 1
Δ =  1 → a_ij = 3
Δ =  2 → a_ij = 5
Δ =  3 → a_ij = 7
Δ < 0  → recíproco
```

Consequências:

- os únicos parâmetros livres do autor por segmento são as *n* faixas, não as n(n−1)/2 células;
- a faixa de um fator ancorado é **restringida** pelo tercil de seu `r` dentro do conjunto de
  critérios da própria fonte: tercil superior → faixa 1–2, intermediário → 2–3, inferior → 3–4. O
  código confere;
- toda faixa de classe C exige `rationale` citando uma fonte não-AHP (ZARC, requisitos de cultura
  da FAO, planejamento sistemático de conservação, literatura de sítio fotovoltaico) **ou** a
  etiqueta literal `author judgement`, cuja contagem por segmento é reportada na tese.

### R5 — Ordem de preenchimento e congelamento

Preencher e versionar classe A primeiro, depois B, depois C. As células de classe A ficam congeladas
pelo resto do processo. Em modo de derivação, `derive_weights.py` **não lê** os pesos de
`config/segments.yaml` (só `--check` lê) e **não imprime o vetor de prioridades** antes do fim do
laço. Não se converge para um alvo que não se pode ver.

### R6 — Laço de revisão limitado (RC > 0,10)

1. Calcular os desvios de Saaty `ε_ij = a_ij·w_j/w_i`; localizar o máximo |ln ε|.
2. Revisar a **faixa**, nunca a célula: deslocar exatamente um fator em exatamente ±1 faixa.
   Revisar a faixa move linha e coluna coerentemente, de modo que uma revisão não pode ser usada
   para ajustar uma célula isolada em direção a um alvo.
3. Elegíveis: fatores de classe C primeiro; classe B só se nenhuma revisão em C reduzir a RC;
   classe A nunca.
4. Teto rígido: **3 revisões por segmento**, imposto em código. Sem exceção.
5. A condição de parada é RC ≤ 0,10 — *nunca* proximidade a qualquer vetor de pesos.
6. Persistindo RC > 0,10 após 3 revisões, a ferramenta falha e o segmento precisa ser
   reestruturado (hierarquia de dois níveis), não revisado mais.
7. Cada revisão é registrada em `revisions:` — iteração, fator, faixa antes/depois, RC antes/depois,
   motivo. Esse registro **é** o método, e por isso pertence ao anexo da tese.

### R7 — Exceções (`override`)

Qualquer `a_ij` que se desvie de sua regra exige `override: {value, reason}`, é contado e impresso a
cada execução, e custa ao segmento o rótulo de "integralmente derivado por regra". Mais de 2 por
segmento faz a verificação falhar.

### R8 — Reporte honesto da RC

Onde um segmento é dominado por classe A, `w_lit` é, essencialmente, o vetor de prioridades
publicado da fonte, renormalizado — e sua RC mede apenas o arredondamento à escala de Saaty. Isso
precisa ser dito, não apresentado como evidência de coerência de elicitação.
`derive_weights.py` emite a **fração ancorada** = |A| / total de pares por segmento. Conservação e
piscicultura pontuam baixo; esse é o achado, não um defeito a esconder.

---

## 2. Regra de resolução de conflitos entre fontes

Aplicada uniformemente, a todo fator, e não caso a caso:

1. **Proximidade de contexto.** Prevalece a fonte cujo sistema produtivo e bioma estejam mais
   próximos de GO/DF — savana tropical, sequeiro, escala de propriedade comparável.
2. **Coerência amostral.** Permanecendo o conflito, adota-se o limiar compatível com a distribuição
   percentílica realmente observada em GO/DF (`thesis/Chapters/breakpoint_anchoring.csv`),
   preservando a forma funcional e a ordenação relativa.
3. **Sem médias.** Nunca se calcula a média de fontes conflitantes. O valor rejeitado e o motivo
   ficam registrados.

### Aplicação 1 — declive da piscicultura

Conflito de três vias, até aqui não reconhecido no texto da tese:

| Fonte | Diz |
|---|---|
| `francisco_classification_2019` (tab. 5, p. 9) | ≤2 % = 0,4113 · 2–5 % = 0,3800 · 5–10 % = 0,1475 · >10 % = 0,0611 |
| `assefa_gis_2018` | >8 % já inadequado |
| modelo (atual) | decrescente [2,86°, 5,71°] ≡ [5 %, 10 %] |

Pela regra 1, Francisco prevalece: Paraná, Brasil, viveiros escavados em solo — o mesmo sistema
produtivo modelado aqui. Assefa avalia piscicultura na Etiópia. Pela tab. 5 de Francisco a queda de
aptidão se dá entre 5 % e 10 %, que é exatamente o limiar adotado. **O limiar do modelo é o de
Francisco**; o 8 % de Assefa é o valor rejeitado, e fica registrado como tal.

### Aplicação 2 — ordenação do declive na piscicultura

Francisco (tab. 4) coloca o declive em **primeiro** lugar (0,4894); Ssegane (tab. 5) o coloca em
**penúltimo** (0,070), com a disponibilidade de água em primeiro (0,358). A contradição é real e
tem explicação: Francisco modela viveiros *escavados*, em que o movimento de terra domina o custo;
Ssegane modela viveiros abastecidos, em que a água manda.

Pela regra 1 nenhuma das duas domina claramente — Francisco é brasileira, Ssegane é do sistema mais
próximo do nosso (GO/DF tem água sazonal distante, mediana 2,3 km, e é isso que discrimina o
território). A resolução adotada, declarada aqui: **Ssegane é a âncora de prioridade**, por cobrir
4 dos 5 fatores do segmento numa única matriz internamente consistente (RC = 0,0308), e
**Francisco é a âncora dos limiares** de declive (tab. 5) e permanece registrada como divergência
de ordenação no Capítulo 5.


## 2b. Regra de reancoragem de limiares

Um conjunto de limiares que caia **fora** da distribuição observada em GO/DF não avalia coisa
alguma: se todo o território fica acima do limiar superior, a pertinência satura em μ = 1; se fica
abaixo do inferior, veta tudo. Regra, aplicada uniformemente:

> Quando o intervalo P5–P95 observado sobre a terra disponível cai inteiramente fora dos limiares
> móveis de um fator, os limiares são reancorados a esse intervalo, **preservando a forma funcional
> e a direção**. Quando o intervalo observado cai inteiramente *dentro* de um platô ótimo, os
> limiares não se movem — o fator simplesmente não gradua, e passa a `role: gate` (§4).

A distinção importa. Saturar porque os limiares estão no lugar errado é um defeito; saturar porque
a região inteira está dentro da faixa agronomicamente ótima é um **achado**, e forçar discriminação
ali seria precisão espúria.

Três fatores foram reancorados por esta regra:

| Fator | Antes | Observado (P5–P95) | Depois | Efeito |
|---|---|---|---|---|
| `sugarcane.soil_awc` | crescente [5, 20] | 22,1–33,6 | crescente [22,1, 33,6] | σ(μ) 0,006 → **0,268**; saturação 99,3 % → 5,0 % |
| `conservation.terr_twi` | crescente [8,5, 11,2] | 9,19–12,06 (P10–P90 9,44–11,56) | crescente [9,44, 11,56] | σ(μ) 0,239 → 0,312 |
| `pisciculture.water_drain_density` | crescente [0,01, 0,08] | P50 = 0, P75 = 0,013, P90 = 0,093 | crescente [0,0, 0,093] | veto 74,3 % → 68,6 % |

O caso da CAD da cana era o mais grave: a faixa [5, 20] estava **inteiramente abaixo** da
distribuição real, de modo que 99,3 % da terra disponível recebia μ = 1 e o fator, apesar do peso
nominal de 0,22, não separava célula alguma. É exatamente o tipo de erro que o diagnóstico σ(μ)
existe para expor e que a razão `iqr/span` anterior não expunha.

A reancoragem do `terr_twi` tem um efeito lateral útil: ancorar o limiar na distribuição observada
torna desnecessário o deslocamento manual de +ln(Δx/250) que a correção da célula de captação do
HydroSHEDS havia exigido. Se a escala nominal mudar outra vez, basta reexecutar
`tools/anchor_breakpoints.py discrimination`; não há constante escrita à mão para acompanhar.

**Ressalva registrada, não resolvida:** mesmo reancorado, `water_drain_density` continua vetando
68,6 % da terra disponível na piscicultura, porque a banda é estruturalmente zero-inflada a 250 m —
um zero ali significa "nenhuma célula de curso d'água mapeada nesta resolução", não "sem água". Sob
a média geométrica o veto vira o piso ε. O dano ficou muito menor do que era (o peso derivado caiu
de 0,14 para 0,0525, de modo que o multiplicador nos pixels zerados passou de ×0,38 para ×0,70),
mas não é zero. As saídas honestas são duas: retirar o fator da piscicultura, por ser redundante
com `sit_water_dist_seas` — que é o critério nº 1 de Ssegane e já captura acesso à água — ou
mantê-lo e reportar o efeito. A decisão é do autor; nada foi retirado aqui.

---

## 3. Travessia por segmento

`r` é a prioridade publicada, verbatim. `r*` é a mesma prioridade renormalizada sobre o subconjunto
de critérios que têm correspondente aqui — é `r*` que entra em `a_ij = snap(r_i/r_j)`.

### 3.1 Soja — `radocaj_optimal_2020`

Duas matrizes independentes, logo **dois blocos**. Pares entre blocos são classe B.

| Fator | Critério da fonte | Localizador | r | r* | Bloco |
|---|---|---|---|---|---|
| `soil_ph` | pH | tab. 6, p. 14 | 0,254 | 0,4739 | solo |
| `terr_slope` | Slope | tab. 6, p. 14 | 0,178 | 0,3321 | solo |
| `soil_clay` | SoilTexture | tab. 6, p. 14 | 0,104 | 0,1940 | solo |
| `clim_pr_annual` | Precipitation | tab. 5, p. 13 | 0,261 | — | **porta** (§4) |
| `clim_twarm_q` | Tavg | tab. 5, p. 13 | 0,104 | — | **porta** (§4) |
| `clim_aridity` | — | — | — | — | (faixa) |

Os dois fatores climáticos saíram da matriz: sua pertinência é constante em GO/DF (§4), de modo que
o bloco climático de Radočaj deixa de ter representante ponderado na soja. Restam os três fatores de
solo, todos do mesmo bloco — o segmento fica com n = 4 e fração ancorada 0,50.

Matriz de solo: n = 6, CI = 0,093, RI = 1,240, RC = 0,075. Matriz de clima: n = 6, CI = 0,050,
RI = 1,240, RC = 0,040.

**Sem correspondente aqui:** SoilType 0,383 (o maior peso da fonte — não há carta de classes de solo
a 250 m em GO/DF; o modelo usa textura, SOC, pH e CAD contínuos no lugar), C/N 0,073 (não há N
disponível), TWI 0,039 (existe como `terr_twi`, mas é fator de conservação, não de soja),
Tmin 0,388 (o maior peso climático da fonte — risco de geada, inexistente no Cerrado),
Tmax 0,082, AirHumidity 0,042.

### 3.2 Cana-de-açúcar — `alburo_application_2019` + `haile_assessment_2026`

Nenhuma das duas cobre o segmento inteiro: Alburo não tem critério climático algum, Haile é um
esquema **irrigado**, em que a prioridade climática não se transfere para o regime de sequeiro sem
ressalva. Divisão declarada: **Alburo para solo/terreno, Haile para clima**; são blocos distintos.

| Fator | Critério da fonte | Localizador | r | r* | Bloco |
|---|---|---|---|---|---|
| `soil_awc` | Water Holding Capacity | Alburo tab. 2, p. 154 | 19,4 % | 0,3880 | solo |
| `terr_slope` | Slope | Alburo tab. 2, p. 154 | 16,5 % | 0,3300 | solo |
| `soil_clay` | Soil Texture | Alburo tab. 2, p. 154 | 14,1 % | 0,2820 | solo |
| `clim_twarm_q` | Temperature | Haile tab. 4, p. 316 | 43,58 % | 0,6546 | clima |
| `clim_pr_annual` | Rainfall | Haile tab. 4, p. 316 | 22,99 % | — | **porta** (§4) |
| `clim_dry_months` | — | — | — | — | **porta** (§4) |

Alburo: elicitação com 5 especialistas e 10 produtores; RC 1,6 % (combinado) / 2,5 % (produtores) /
5,2 % (especialistas); validada contra produtividade real (tab. 3–4, p. 155). Haile: λmax 6,378,
CI 0,0756, RCI 1,24, RC 0,061.

**Sem correspondente aqui:** em Alburo, profundidade do solo 26,7 % (o maior peso da fonte;
indisponível a 250 m em GO/DF — e a própria fonte a descarta, p. 155: *"soil depth data obtained
from the sample farms have similar values, hence, may not be considered a variable in the locality
and need not be included in the evaluation"*), orientação de encosta 11,7 % e elevação 11,6 %; em
Haile, cobertura do solo 4,90 % (vetada pela salvaguarda de cobertura da terra), textura 13,93 % e
declive 10,19 % (já ancorados em Alburo, bloco de solo), pH 4,42 % (a cana não usa `soil_ph`).

> A frase de Alburo sobre a profundidade do solo é **precedente publicado para a regra de
> adaptação λ**: um fator importante na literatura que não varia na localidade e que, por isso, não
> deve pesar. É citada em `\S`sec:ahp, não apenas aqui.

**Ressalva de leitura da RC (R8), registrada.** Depois que `clim_twarm_q` passou a porta (§4), a
cana ficou com três fatores, todos do bloco de solo de Alburo, cujas prioridades publicadas são
próximas: r* = 0,3880 / 0,3300 / 0,2820, de modo que **todos os três quocientes arredondam para 1**
na escala inteira de Saaty. A matriz resultante é a matriz unitária 3×3, com w_lit = (1/3, 1/3, 1/3)
e RC = 0,0000. Essa RC **não é evidência de elicitação coerente** — é uma propriedade de construção
de uma matriz uniforme, exatamente o tipo de número que a R8 existe para impedir que seja lido como
mérito. O que ela diz é que, no nível de resolução da escala 1–9, Alburo não separa CAD, declive e
textura. A diferenciação entre os três vem **inteiramente da etapa regional**: d = 0,2422 / 0,2682 /
0,3826 leva os pesos finais a 0,3022 / 0,3180 / 0,3798. A cana é, portanto, o segmento em que a
etapa λ carrega o maior peso explicativo, e isso precisa ser dito junto com a RC.

### 3.3 Outras culturas anuais — `tadesse_land_2020`

Matriz única de 14 critérios, RC = 0,063. É o segmento mais bem ancorado: **um só bloco**, logo
todos os pares entre fatores correspondidos são de classe A.

| Fator | Critério da fonte | Localizador | r | r* |
|---|---|---|---|---|
| `soil_soc` | Organic Matter | tab. 7, p. 10 | 0,142 | 0,4189 |
| `clim_gdd` | Temperature | tab. 7, p. 10 | 0,058 | 0,1711 |
| `soil_ph` | Soil pH | tab. 7, p. 10 | 0,054 | 0,1593 |
| `clim_pr_annual` | Rainfall | tab. 7, p. 10 | 0,054 | — **porta** (§4) |
| `terr_slope` | Slope | tab. 7, p. 10 | 0,031 | 0,0914 |
| `clim_pr_cv` | — | — | — | — (faixa) |

**Sem correspondente aqui:** TN 0,162 (o maior peso da fonte), Av. P 0,117, CEC 0,093, Mg 0,064,
Ca 0,060, K 0,054, EC 0,037, Na 0,028 — química de solo indisponível a 250 m em GO/DF (o SoilGrids
fornece argila, areia, SOC, pH, densidade e CAD, não N/P/K/Ca/Mg/CEC/EC); e Soil Depth 0,045.

> Esta é a divergência mais nítida do trabalho: Tadesse dá ao declive o **menor** peso dos 14
> critérios (0,031, logo r* = 0,0914) e à matéria orgânica o maior dos correspondidos
> (0,142, r* = 0,4189). O estágio λ não inverte essa ordem — mantém `soil_soc` no topo e o
> reforça (0,4629 → **0,5378**) —, mas desloca peso do clima para o solo e o relevo: `clim_gdd`
> cai de 0,1978 para 0,1374 e `clim_pr_cv` de 0,0695 para 0,0376 (d = 0,077 e 0,047), enquanto o
> declive **sobe** de 0,0874 para 0,1223, o maior ganho relativo do segmento (d = 0,3136, o maior
> do segmento). Não é erro de travessia — é a uniformidade agroclimática de GO/DF, que retira
> poder discriminante dos fatores climáticos e o redistribui para os que variam. É precisamente o
> que o estágio λ existe para expressar, e de forma auditável.

### 3.4 Piscicultura — `ssegane_geospatial_2012` (prioridade) + `francisco_classification_2019` (limiares)

Ver §2, aplicação 2, para a resolução do conflito de ordenação.

| Fator | Critério da fonte | Localizador | r | r* |
|---|---|---|---|---|
| `sit_water_dist_seas` | Water requirement | Ssegane tab. 5, p. 160 | 0,358 | 0,4625 |
| `clim_twarm_q` | Water Temperature | Ssegane tab. 5, p. 160 | 0,235 | 0,3036 |
| `soil_clay` | Soil texture | Ssegane tab. 5, p. 160 | 0,111 | 0,1434 |
| `terr_slope` | Slope | Ssegane tab. 5, p. 160 | 0,070 | 0,0904 |
| `water_drain_density` | — | — | — | — (faixa) |

Ssegane: RC = 0,0308. Francisco: λmax 4,0192, CI 0,0064, RI 0,90, RC 0,007 (tab. 4, p. 9).

**Sem correspondente aqui:** em Ssegane, Farm inputs 0,143, Farm gate sales 0,049, Access to markets
0,034 — critérios socioeconômicos fora do escopo biofísico deste atlas; em Francisco, Altitude
0,1623 (sem fator de elevação no segmento) e Soil use and occupation 0,0604 (vetado pela
salvaguarda de cobertura da terra).

### 3.5 Pecuária — `balew_identification_2022`

Coluna do gado, tab. 2, p. 10. RC = 0,05. Bloco único.

| Fator | Critério da fonte | Localizador | r | r* |
|---|---|---|---|---|
| `clim_pr_annual` | Rainfall | tab. 2, p. 10 | 0,3375 | — | **porta** (§4) |
| `terr_slope` | Slope | tab. 2, p. 10 | 0,1049 | 0,6620 |
| `soil_soc` | Soil type | tab. 2, p. 10 | 0,0536 | 0,3380 |
| `clim_soil_moist` | — | — | — | (faixa) |
| `clim_dry_months` | — | — | — | **porta** (§4) |

**Sem correspondente aqui:** LULC 0,3375 — empatado em primeiro na fonte, **vetado pela salvaguarda
de cobertura da terra** (CLAUDE.md §7: uso da terra é máscara, contexto e validação, nunca entrada
de viabilidade — usá-lo seria prever uso da terra com uso da terra); e Water accessibility 0,1665,
sem fator correspondente no segmento (a pecuária do modelo não carrega distância à água).

> Segunda divergência de destaque, e a mais forte do trabalho: a chuva é o critério de **primeiro
> lugar** em Balew (0,3375, empatada com o LULC) e, em GO/DF, não recebe peso nenhum — não porque se
> tenha decidido rebaixá-la, mas porque sua pertinência é **constante** em todo o território
> (§4). O critério mais importante da literatura para a pecuária não consegue, aqui, distinguir uma
> célula da outra. Ele permanece no modelo como porta de viabilidade e como alavanca CMIP6, mas sai
> da matriz de ponderação. É a mesma explicação da §3.3, em outro segmento, o que dá ao argumento
> sobre a uniformidade climática de GO/DF caráter **repetido e consistente entre segmentos**, em vez
> de justificação *ad hoc* por fator.

### 3.6 Conservação — `morandi_delimitation_2020`

AHP no Cerrado (corredores ecológicos), tab. 4, p. 6. RC = 0,08. Os pesos publicados somam ≈ *n*
(1,060 + 1,715 + 0,224 = 2,999), isto é, são o autovetor escalado por *n*; `r*` renormaliza para 1.

| Fator | Critério da fonte | Localizador | r | r* |
|---|---|---|---|---|
| `cv_pa_dist` | PPA (área de preservação permanente) | tab. 4, p. 6 | 1,715 | 0,5719 |
| `rl_native_frac` | Land use/occupation | tab. 4, p. 6 | 1,060 | 0,3535 |
| `terr_slope` | Terrain Slope | tab. 4, p. 6 | 0,224 | 0,0747 |
| `cv_carbon`, `cv_ruggedness`, `terr_twi`, `clim_aridity`, `clim_twarm_q`, `water_drain_density` | — | — | — | — (faixas) |

É o segmento **menos ancorado**: 3 de 36 pares em classe A (fração ancorada 0,083). A razão é
material, não de esforço — não existe, na literatura GIS-AHP consultada, um estudo que pondere
simultaneamente conectividade, heterogeneidade de habitat, serviço de carbono e exposição climática
como critérios de um mesmo índice de valor de conservação. Os seis fatores restantes são faixas de
classe C, com justificativa em planejamento sistemático de conservação (`schuler_spatial_2022`) e o
rótulo `author judgement` onde não há fonte. A fração ancorada vai para a tabela do anexo
exatamente por isso.

Observação de coerência direcional: Morandi põe a proximidade de APP em primeiro e o declive em
último, o que reproduz a ordenação do modelo (`cv_pa_dist` é o maior peso do segmento; `terr_slope`
está entre os menores). A âncora é estreita, mas não contraditória.

### 3.7 Geração fotovoltaica — `elboshy_suitability_2022`

Matriz única de 10 critérios, tab. 2, p. 5. Bloco único.

| Fator | Critério da fonte | Localizador | r | r* |
|---|---|---|---|---|
| `clim_srad` | Solar radiation | tab. 2, p. 5 | 27,0 % | 0,3919 |
| `clim_twarm_q` | Annual Average Temperature | tab. 2, p. 5 | 14,9 % | 0,2163 |
| `sit_clearness` | Average annual cloudy days | tab. 2, p. 5 | 10,4 % | 0,1509 |
| `access_logtt` | Distance from Urban | tab. 2, p. 5 | 10,1 % | 0,1466 |
| `terr_slope` | Slope | tab. 2, p. 5 | 6,5 % | 0,0943 |
| `terr_northing` | — | — | — | — (faixa) |

**Sem correspondente aqui:** Distance from power transmission lines 10,8 % (não há camada de linhas
de transmissão para GO/DF no catálogo do Earth Engine — limitação registrada no Capítulo 5),
Lightning strike flash rate 7,3 %, Elevation 5,1 %, Distance from major roads 4,4 % (parcialmente
capturado por `access_logtt`, que é tempo de viagem e não distância a estradas), Soil texture 3,5 %.

`terr_northing` (orientação de encosta) não aparece em Elboshy nem em `rane_gis-based_2024`; é faixa
de classe C, justificada pela geometria solar do hemisfério sul.

---

## 4. Fatores-porta (`role: gate`)

Um fator cuja **pertinência** é constante sobre GO/DF tem σ(μ) = 0: ele não distingue célula alguma,
por mais importante que seja na literatura. Mantê-lo na média ponderada com μ constante < 1 não o
torna discriminante — apenas multiplica a superfície inteira por esse valor, deslocando as fatias de
classe da FAO, cujos cortes (0,25 / 0,50 / 0,75) são absolutos.

Tratamento adotado: `role: gate` — o fator sai da matriz AHP e do vetor de pesos e é aplicado como
**porta multiplicativa**, com os limiares ancorados de modo que o valor presente dê μ = 1. Isso
remove o deflator oculto e **preserva a alavanca CMIP6**: se a variável sair do platô sob
aquecimento, a porta morde. É o mesmo raciocínio que Alburo aplica à profundidade do solo (§3.2).

Critério de decisão, medido e não arbitrado, sobre a terra disponível
(`thesis/Chapters/factor_discrimination.csv`):

> **σ(μ) < 0,05 E média(μ) > 0,95** — as duas condições, conjuntamente.

As duas são necessárias. σ(μ) sozinho mede apenas *ausência de variação*, e uma segunda família de
fatores também a exibe: os que são quase uniformes num μ **baixo**. `other_crops.clim_pr_cv` é o
caso — σ(μ) = 0,047, mas média(μ) = 0,694 e nenhuma saturação. Não é um platô: é uma penalização
real, aplicada de modo homogêneo a todo o estado porque o coeficiente de variação da chuva é de fato
alto em toda parte. Reancorá-lo a μ = 1, como a doutrina de porta exige, converteria uma penalização
legítima num no-op e **elevaria** toda a superfície de outras culturas. A segunda condição é o que
separa "não gradua porque tudo está no ótimo" de "não gradua porque tudo está igualmente ruim" — só
a primeira é uma porta.

O limiar σ(μ) < 0,02 da iteração anterior era estreito demais: deixava
`sugarcane.clim_twarm_q` (σ = 0,039, média(μ) = 0,988, 85 % saturado) como fator ponderado e, pior,
com o **maior peso do segmento** (0,3024), enquanto sua contribuição para a média geométrica era de
≈0,996 — peso sem poder discriminante, diluindo declive, CAD e argila, que discriminam.

| Segmento | Fator-porta | σ(μ) | μ presente | Por que é constante |
|---|---|---|---|---|
| Soja | `clim_twarm_q` | 0,000 | 1,000 | 23,6–27,6 °C observados, dentro do platô [22, 30] |
| Soja | `clim_pr_annual` | 0,000 | 1,000 | 1375–1637 mm observados, dentro do platô [1100, 1800] |
| Cana | `clim_pr_annual` | 0,014 | 0,998 | 1375–1637 mm, dentro do platô [1300, 2000] |
| Cana | `clim_dry_months` | 0,014 | 1,000 | meses secos = 5 em todo o estado |
| Outras culturas | `clim_pr_annual` | 0,000 | 1,000 | 1375–1637 mm, dentro do platô [1000, 1700] |
| Pecuária | `clim_pr_annual` | 0,000 | 1,000 | 1375–1637 mm, dentro do platô [1000, 2000] |
| Pecuária | `clim_dry_months` | 0,000 | 1,000 | meses secos = 5 em todo o estado |

Duas observações que o resultado impõe:

1. **Todas as sete portas são climáticas.** Nenhum fator de solo, relevo, água ou acesso satura. É a
   forma mais direta do achado central: em GO/DF o clima **habilita**, e são o relevo e o solo que
   **graduam**. Não é uma escolha de ponderação, é uma medida.
2. **O `clim_dry_months` era modelado de duas formas diferentes para o mesmo valor constante** —
   intervalar [1, 2, 5, 7] na cana e decrescente [4, 8] na pecuária, esta última dando μ ≡ 0,75 e,
   portanto, um deflator silencioso de ×0,977 sobre toda a superfície de pecuária. As duas passam a
   ser portas com μ = 1 no presente, cada uma conservando a direção agronomicamente correta: na cana
   a forma é intervalar (poucos meses secos demais suprimem a janela de maturação, muitos impõem
   estresse hídrico), na pecuária é monótona decrescente (mais meses secos, menos forragem).

## 5. Tabela de faixas

Faixa 1 = mais importante, 4 = menos. Para fatores ancorados a faixa é restringida pelo tercil de
`r` dentro do conjunto de critérios da fonte (R4) e o código confere. Os valores vivem em
`config/ahp_matrices.yaml`; esta tabela é a leitura humana deles.

Apenas os fatores que entram na matriz. Os fatores-porta da §4 não recebem faixa, porque não
participam de comparação alguma.

| Segmento | Fator | Faixa | Classe | Justificativa da faixa |
|---|---|---|---|---|
| soja | `soil_ph` | 2 | A (solo) | tercil superior de Radočaj tab. 6 |
| soja | `terr_slope` | 2 | A (solo) | tercil intermediário de Radočaj tab. 6 |
| soja | `soil_clay` | 3 | A (solo) | tercil intermediário de Radočaj tab. 6 |
| soja | `clim_aridity` | 3 | C | P/PET é verificação secundária de balanço hídrico, redundante com a precipitação num regime de chuvas de verão — `author judgement` |
| cana | `soil_awc` | 2 | A (solo) | tercil superior de Alburo tab. 2 |
| cana | `terr_slope` | 2 | A (solo) | tercil intermediário de Alburo tab. 2 |
| cana | `soil_clay` | 3 | A (solo) | tercil intermediário de Alburo tab. 2 |
| cana | `clim_twarm_q` | 1 | A (clima) | tercil superior de Haile tab. 4 |
| outras | `soil_soc` | 1 | A | tercil superior de Tadesse tab. 7 |
| outras | `clim_gdd` | 3 | A | tercil intermediário de Tadesse tab. 7 |
| outras | `soil_ph` | 3 | A | tercil intermediário de Tadesse tab. 7 |
| outras | `terr_slope` | 4 | A | tercil inferior de Tadesse tab. 7 |
| outras | `clim_pr_cv` | 4 | C | confiabilidade da chuva para a safrinha; ZARC trata a variabilidade como risco de segunda ordem frente ao total sazonal — `amaral_metodologia_2023` |
| piscicultura | `sit_water_dist_seas` | 1 | A | tercil superior de Ssegane tab. 5 |
| piscicultura | `clim_twarm_q` | 2 | A | tercil superior de Ssegane tab. 5 |
| piscicultura | `soil_clay` | 3 | A | tercil intermediário de Ssegane tab. 5 |
| piscicultura | `terr_slope` | 3 | A | tercil intermediário de Ssegane tab. 5 |
| piscicultura | `water_drain_density` | 4 | C | disponibilidade hídrica local complementar à distância sazonal, com a qual é parcialmente redundante — `author judgement` |
| pecuária | `terr_slope` | 3 | A | tercil intermediário de Balew tab. 2 |
| pecuária | `soil_soc` | 4 | A | tercil inferior de Balew tab. 2 |
| pecuária | `clim_soil_moist` | 2 | C | umidade do solo é o determinante direto de produtividade forrageira; Balew usa a chuva como seu *proxy* e não dispõe da variável — `molossi_improve_2020` |
| conservação | `cv_pa_dist` | 1 | A | tercil superior de Morandi tab. 4 |
| conservação | `rl_native_frac` | 3 | A | tercil intermediário de Morandi tab. 4, rebaixado pela descircularização |
| conservação | `terr_slope` | 4 | A | tercil inferior de Morandi tab. 4 |
| conservação | `cv_ruggedness` | 2 | C | heterogeneidade de habitat e baixa aptidão agrícola — `schuler_spatial_2022` |
| conservação | `cv_carbon` | 2 | C | serviço de estoque de carbono; mantido abaixo do que a variância sugeriria por conta da circularidade branda (biomassa ~ floresta) — `schuler_spatial_2022` |
| conservação | `terr_twi` | 3 | C | serviço hídrico ripário e de recarga — `author judgement` |
| conservação | `clim_aridity` | 3 | C | viabilidade de balanço hídrico, alavanca CMIP6 do segmento — `author judgement` |
| conservação | `clim_twarm_q` | 3 | C | estresse térmico e de fogo, segunda alavanca CMIP6 — `author judgement` |
| conservação | `water_drain_density` | 4 | C | serviço hídrico, parcialmente redundante com `terr_twi` — `author judgement` |
| fotovoltaica | `clim_srad` | 1 | A | tercil superior de Elboshy tab. 2 |
| fotovoltaica | `clim_twarm_q` | 2 | A | tercil superior de Elboshy tab. 2 |
| fotovoltaica | `sit_clearness` | 3 | A | tercil intermediário de Elboshy tab. 2 |
| fotovoltaica | `access_logtt` | 3 | A | tercil intermediário de Elboshy tab. 2 |
| fotovoltaica | `terr_slope` | 4 | A | tercil inferior de Elboshy tab. 2 |
| fotovoltaica | `terr_northing` | 4 | C | geometria solar do hemisfério sul favorece encostas voltadas ao norte; ausente em Elboshy e em Rane — `author judgement` |

---

## 6. Fontes por segmento

| Segmento | Prioridade (âncora AHP) | Apoio (limiares, faixas, contexto) |
|---|---|---|
| Soja | `radocaj_optimal_2020` | `corbellini_geographical_2024` |
| Cana | `alburo_application_2019` (solo) · `haile_assessment_2026` (clima) | `aparecido_climate_2021` |
| Outras culturas | `tadesse_land_2020` | `amaral_metodologia_2023` (ZARC-milho) |
| Piscicultura | `ssegane_geospatial_2012` | `francisco_classification_2019` (limiares) · `assefa_gis_2018` |
| Pecuária | `balew_identification_2022` | `vieira_classification_2022` · `molossi_improve_2020` |
| Conservação | `morandi_delimitation_2020` | `schuler_spatial_2022` |
| Fotovoltaica | `elboshy_suitability_2022` | `rane_gis-based_2024` |

Índice aleatório (RI): `saaty_analytic_1987`, p. 171. Reimpresso por `francisco_classification_2019`
(tab. 3, n ≤ 10) e `elboshy_suitability_2022` (tab. 1, n ≤ 10); estendido até n = 15 por
`haile_assessment_2026` (tab. 2, p. 316), que é a fonte do trecho da tabela acima de n = 10 usado em
`src/membership.py`.
