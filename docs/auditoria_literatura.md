# Checkpoint — bibliografia Zotero e auditoria de citações (26/09/2026)

Checkpoint da sessão de 26/09/2026, item **s0** do cronograma de revisão
(<https://claude.ai/artifact/HrMpse386bFykBeBsBeJN6>). Registra:

- a migração da bibliografia para o Zotero;
- a auditoria de todas as citações contra os PDFs;
- as correções aplicadas ao texto e ao código;
- o que ficou pendente para as próximas etapas.

Os registros completos por referência (49 arquivos, com trechos literais dos PDFs e a página de
cada evidência) estão em `thesis/Bibliography/zotero_auditoria_20260926/`. A pasta é **local e
gitignored** (`thesis/Bibliography/zotero*`), pela mesma regra de direitos de autor dos PDFs, e por
isso este documento traz apenas paráfrases e localizadores.

---

## 1. Bibliografia migrada para o Zotero

- O Zotero passou a ser a fonte de verdade. O export BibLaTeX fica em
  `thesis/Bibliography/zotero_bibliography.bib` (61 entradas) e os anexos em `zotero_storage/`;
  ambos são locais e gitignored.
- `tools/sync_zotero_bib.py` (novo) gera o `bibliography.bib` commitado:
  - remove `file`, `abstract`, `keywords`, `urldate` e `shorttitle`;
  - recusa-se a escrever se faltar alguma chave citada;
  - lista as entradas sem PDF local (só `da_silva_goias_suitability_2026`, o próprio repositório,
    e `noauthor_full_nodate`, um snapshot duplicado do Malczewski).
- As chaves antigas (`Abatzoglou2018`) foram migradas para o formato do Zotero
  (`abatzoglou_terraclimate_2018`): 57 `\cite` reescritos nos capítulos 01–05.
- Duas substituições deliberadas: `Saaty1980` → `saaty_analytic_1987`; `FAO1976` → GAEZ v4
  (`noauthor_global_2021`), com a frase de `03_methodology.tex` ajustada.
- Nova seção **§12 do CLAUDE.md**: o PDF é a fonte primária de toda citação. Antes de escrever,
  ler a passagem no PDF; dado específico leva localizador (`\citep[p.~X]{…}`); entrada sem PDF
  não sustenta afirmação nova; PDFs nunca saem da máquina.

## 2. Método da auditoria

Um agente por referência citada: **49 referências, 67 ocorrências**. Cada agente:

1. leu o PDF da entrada (via `zotero_storage/`) e o parágrafo em volta de cada ocorrência;
2. julgou se a obra sustenta a afirmação atribuída (coerência) e se é a fonte adequada (relevância);
3. conferiu cada dado factual (número, resolução, período, versão, limiar, afirmação sobre a área
   de estudo) contra o PDF e, quando o dado descreve um insumo deste projeto, também contra
   `config/*.yaml` e `src/*.py`;
4. conferiu a forma da citação (`\citet`/`\citep`, localizador) e os metadados da entrada.

## 3. Resultado

| Veredito | Ocorrências |
|---|---:|
| OK | 35 |
| Imprecisa | 24 |
| Incorreta | 7 |
| Fraca / tangencial | 1 |
| **Total** | **67** |

As 7 incorretas, todas corrigidas (§4):

| Onde | Problema |
|---|---|
| 02_materials (CHIRPS) | CHIRPS e WorldClim apresentados como insumos suplementares, mas nenhum dos dois está no pipeline |
| 02_materials e 03_methodology (Hengl 2026) | A tese citava o OpenLandMap-soildb a 30 m, que não tem teor de água; o projeto usa as camadas v0.2 a 250 m |
| 03_methodology (Hargreaves 1985) | A razão de ETP foi descrita como dependente "apenas da temperatura média"; na fonte e no código ela também depende da amplitude térmica |
| 03_methodology (Ikotun) | A estatística de gap foi atribuída a uma obra que não a trata; pela regra implementada, o gap aponta k=14, e não 10 |
| 03_methodology (Nisar Ahamed) | A obra foi citada para funções lineares por partes, mas usa pertinência por distância euclidiana inversa |
| 04_results (Cicchetti) | A citação estava presa a uma frase que o artigo não sustenta, e o raciocínio vizinho sobre p_e estava errado |

## 4. Correções aplicadas

### Decisões do autor

- **CHIRPS/WorldClim:** removidos de 02_materials e da tabela de fontes do anexo. A passagem da
  discussão que explica por que o TerraClimate foi mantido continua.
- **Seleção do k:** parágrafo reescrito (03_methodology e anexo) com os números reais de
  `zoning_kselect.csv`:
  - a silhueta vai de 0,161 a 0,187, com máximo em k=10;
  - o Davies–Bouldin fica plano de k=7 a 20, com mínimo em k=19;
  - o gap só se estabiliza em k=14;
  - entre k≥7, só k=9 (ARI 0,970) e k=10 (0,962) são estáveis;
  - k=2, 3 e 5 são estáveis, mas grossos demais.

  A escolha de k=10 se mantém, agora com a justificativa correta.
- **TWI:** corrigido no código e reexportado (ver abaixo).

### Correção do TWI

- `src/features.py` calculava a área de contribuição específica com o passo da grade de análise
  (250 m), e não com a célula do HydroSHEDS 15ACC (≈464 m), que é a unidade da contagem de
  acumulação. O efeito era uma constante de −ln(463,83/250) = −0,618 em todo o TWI.
- A correção é um deslocamento aditivo puro, que se anula no z-score. Por isso o stack
  padronizado, o zoneamento e o RF não mudam.
- Os limiares da conservação em `config/segments.yaml` foram deslocados pela mesma constante
  (8,5/11,2 → 9,118/11,818), de modo que a pertinência, a viabilidade e o CMIP6 também não mudam.
- Só dois assets foram reexportados: `feat_terrain` e `feature_stack_250m`. Ambos foram gravados
  como o backup mais o deslocamento exato. O backup está em `goias_backup_20260926_twi`.
- Verificação no GEE, amostra de 5.000 pixels a 250 m:
  - o deslocamento do TWI é 0,6180598 em todos os pixels;
  - as demais bandas são idênticas;
  - o z-score do TWI difere em ≤1e-13;
  - a pertinência da conservação difere em ≤2e-5 (arredondamento de 9,118);
  - a pegada (footprint) está OK (`verify_assets.py`).
- Números atualizados:
  - TWI por zona na tabela do anexo e em 04_results (Z4: 14,6 → 15,2);
  - limiares do TWI no anexo;
  - `zone_profiles.csv` (raiz e dashboard) e o `segments.json` do dashboard.
- A armadilha está registrada no CLAUDE.md, §11.

### Demais correções (texto)

| Arquivo | Correção |
|---|---|
| 01_introduction | Schneider restrito ao que o inventário global mostra (pp. 3–4, 10). Marengo passa a sustentar só as tendências observadas desde 1981; a projeção para meados do século passa a Souza 2026 (p. 11). |
| 02_materials | Yamada: correção de P, K, S e micronutrientes (p. 617). Corbellini: ensaios G×E em Mato Grosso (pp. 1–3). Souza: queda de 12,6–34,8% da área de soja em GO (p. 11). Aparecido: faixas "partem do" zoneamento e foram recalibradas (p. 782). Piscicultura: explicita a temperatura do ar como aproximação. Vieira: 28% (p. 1219). Rane: fatores reais do estudo (tab. 2). Gorelick: reescrito, e "licenla" → "licença". TerraClimate a 1/24°. `\citealp` soltos trocados por `\citep`. |
| 03_methodology | Ding & He: equivalência aproximada (Teor. 3.1). McMaster: Método 1 sobre médias mensais (p. 292). Beven (p. 48, eq. 8). LeVine: aplicação a savanas, estendida com termo semianual. Solo: v0.2 a 250 m, média de 0/10/30 cm. Pekel: limiar do projeto (>80%) e drenagem do HydroSHEDS. Pertinência linear sem Nisar Ahamed; referência a Yaghmaeian (pp. 80–83). AHP: aproximação por colunas normalizadas (Frish, pp. 4–5); RI/RC em Saaty (p. 171); parêntese duplo corrigido. Delta-change: Ramirez-Villegas (p. 3) e Hay reescrito (pp. 387, 396). Hargreaves: razão com amplitude térmica (Hargreaves & Allen, p. 55, eq. 8). RF: amostra balanceada. κ: mapas binarizados (Cohen, p. 40). |
| 04_results | Marengo: observacional (p. 4). Turner: sem viés global, subestima lavouras (pp. 286, 288–289). He: produção por condado (r=0,96) vs. rendimento no talhão (r≈0,44), em Montana (p. 16). κ: o teto imposto pelas marginais, κ_M ≈ 0,40 (Cohen, pp. 42–43), no lugar de "p_e cresce". Cicchetti: p_pos ≈ 0,49 e p_neg ≈ 0,70 (pp. 551, 557). |
| 05_discussion | SRTM v3 com vazios preenchidos: especificação de 16 m e erro realizado de 6,2 m na América do Sul (Farr, p. 3; tab. 1, p. 21). Spera: 2003–2016 (p. 2), degradação (p. 4), calagem (p. 5), 40% dos *pequenos* produtores, citando Lapola 2014 (p. 4), e >80% da área de GO em propriedades >100 ha (p. 2). Caballero sem "câmbio" (pp. 10, 12). Schuler: restauração × agricultura, sem clima. |
| 06_annex | GDD com N_m = 30,4 dias. Fórmula do TWI com a célula do HydroSHEDS. Tabela de fontes sem CHIRPS/WorldClim. Limiares e médias do TWI atualizados. Parágrafo de seleção do k. |

### Verificação

- `make` compila sem erros e sem citações indefinidas.
- `sync_zotero_bib.py --check` sai com 0.
- A lista de referências tem **47 obras**: Funk (CHIRPS) e Nisar Ahamed deixaram de ser citados,
  mas continuam no Zotero.

---

## 5. Pendências

### 5.1 Fontes a incluir no Zotero, com PDF

Cada ponto tem um `% TODO(Zotero)` no `.tex`; até a inclusão, a frase fica sem citação.

- **Hengl (2018)**, camadas OpenLandMap SOL v02 a 250 m (argila, areia, SOC, pH, densidade
  aparente; teor de água a 33 kPa de Hengl & Gupta, 2019). Entra em `02_materials.tex` e
  `03_methodology.tex`.
- **Tibshirani, Walther & Hastie (2001)**, estatística de gap. Entra em `03_methodology.tex`.
- Opcional: uma referência metodológica clássica de regressão harmônica da fenologia (por exemplo
  Jakubauskas et al., 2001), já que LeVine & Crews é um estudo de caso com um único harmônico.

### 5.2 Correções de metadados no Zotero

Depois de corrigir, reexportar e rodar `uv run python tools/sync_zotero_bib.py`. Se alguma chave
mudar, usar `--rewrite-keys`.

- **GAEZ v4** (`noauthor_global_2021`):
  - autores Fischer, Nachtergaele, van Velthuizen, Chiozza, Franceschini, Henry, Muchoney &
    Tramberend (2021);
  - título "Global Agro-Ecological Zones v4 – Model documentation";
  - local Roma.

  A chave vai mudar.
- **Hargreaves & Samani (1985):** o PDF anexado é o ASAE Paper 85-2517 (conferência, sem revisão
  por pares), e não o artigo da *Applied Engineering in Agriculture* 1(2):96–99 descrito na
  entrada. Trocar o anexo ou a entrada.
- **Aparecido et al. (2021):** o 5º autor é "Cicero Teixeira Silva e Costa".
- **Números de fascículo/artigo:** Farr (2007) é `RG2004`, Turner (2006) é `3--4`, Saaty (1987) é
  `3--5`.
- **Malczewski (2006):** triplicado (`malczewski_gisbased_2006`, `-1`, `noauthor_full_nodate`);
  mesclar num só.
- **Maiúsculas e nomes:** título do ZEE-GO (`queiroz_o_2022`) todo em maiúsculas; nomes de
  autores de Souza (2020) mal formatados.
- **Saaty (1987):** o PDF confirma o autor R. W. Saaty; o artigo credita a T. L. Saaty o
  desenvolvimento do AHP (p. 161).

### 5.3 Etapas seguintes do cronograma

- **Landis & Koch (1977)** já está no Zotero, mas não é citado: há um `%% TODO` em
  `04_results.tex` e a escala é mencionada em `05_discussion`. É o passo q3.
- **Spawn et al. (2020)** está no Zotero, mas o carbono de biomassa aparece sem `\cite` em
  `02_materials.tex` e no anexo, assim como Accessibility to Cities, HydroSHEDS e WDPA (há um
  `%% TODO` no início da seção de dados).
- **Localizadores nas citações já OK:** a maioria ainda não tem página/eq./tab. (regra §12). As
  páginas sugeridas estão nos registros locais.

---

## 6. Comentários finais

**Problema de integridade no AHP. Precisa de decisão do autor antes do checkpoint com o
orientador.** O cabeçalho de `tools/build_ahp.py` diz que as matrizes de comparação par a par
foram reconstruídas a partir dos pesos já definidos em `segments.yaml`, arredondadas à escala de
Saaty "para parecer uma elicitação genuína". A tese, porém, diz que as matrizes foram elicitadas
e que os pesos "se apoiam, assim, em uma elicitação auditável… e não em mera afirmação". Por
construção, o RC ≈ 0,0015 também sai quase nulo, e as matrizes usam passos intermediários (1,25;
1,75; 3,5) que o texto não declara quando diz "escala 1–9". Não alterei nada disso. É o escopo da
etapa de reescrita do AHP no cronograma. Há duas saídas honestas:

- declarar que as matrizes documentam a consistência dos pesos definidos por especialista (e não
  uma elicitação independente);
- fazer uma elicitação real.

**Outras observações:**

- **Referências fora do escopo geográfico.** Várias fontes cobrem só parte da área de estudo ou
  outra região: Souza 2026 (só o Arco Norte, ao norte de 16°S), Corbellini (Mato Grosso), He
  (Montana), Turner (nenhum sítio no Cerrado) e Marengo (MATOPIBA). O texto agora explicita esses
  recortes. Vale evitar generalizar a partir delas nas próximas reescritas.
- **Divergências entre texto e código ainda não resolvidas:**
  - o GDD sobre médias mensais subestima meses próximos da base; a limitação está documentada no
    anexo, mas não foi corrigida;
  - na piscicultura, o limiar de declive do projeto (~5–10%) é mais permissivo que o de Assefa
    (>8% já inadequado);
  - no RF, o "fundo" é o restante do território sem soja (pseudo-ausência), e não uma amostra de
    fundo de toda a paisagem como em Valavi.
- **Nota de configuração:** a unidade da banda NPP em `config/datasets.yaml` parece estar em g,
  quando deveria ser kg (apontado na auditoria de Zhao 2005); convém conferir.
- `notebooks/zone_profiles.csv` é uma cópia antiga, que não foi atualizada.
- **Build:** a primeira compilação desta sessão falhou porque o `template.pdf` foi removido
  durante o `latexmk`, provavelmente por estar aberto ou sendo copiado no Windows. Recompilar
  resolveu.
