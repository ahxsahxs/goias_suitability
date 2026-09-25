# Diagramas da Metodologia — Viabilidade Agrícola e Projeção Climática do Cerrado Goiano

> Material de apoio visual para reuniões de orientação e apresentações/pósteres.
> Os diagramas seguem a estrutura do Capítulo 3 (Metodologia) da dissertação e o pipeline
> efetivamente implementado no repositório (`notebooks/`, `src/`, `tools/`). Fonte de verdade
> textual: `../thesis/Chapters/03_methodology.tex` (racional completo) e `../CLAUDE.md` (estado de
> execução).

---

## 1. Visão geral (1 slide / poster)

Diagrama condensado — bom ponto de partida numa apresentação de 5–10 minutos ou num póster,
antes de entrar em detalhe.

```mermaid
flowchart TD
    A["Catálogo público GEE<br/>clima · terreno · solo · água · fenologia · acesso"] --> B["Grade comum 250 m<br/>EPSG:4326 — GO + DF (~340.000 km²)"]
    B --> C["Conjunto de 34 bandas<br/>(6 temas biofísicos, Tabela 3.1)"]

    C --> D["Viabilidade baseada em conhecimento<br/>pertinência fuzzy + pesos AHP<br/>7 segmentos → classes FAO S1/S2/S3/N"]
    C --> E["Zoneamento não supervisionado<br/>PCA descorrelacionada + k-means (k=10)"]

    D --> F["Projeção climática CMIP6<br/>fatores de mudança · 2031–50 e 2051–70"]
    F --> G["ΔViabilidade + concordância entre modelos"]

    D --> H["Validação (Fase B)<br/>MapBiomas · MOD17 · municípios (Malha IBGE)"]
    E --> H

    G --> I["Atlas de viabilidade multissegmento<br/>+ zoneamento<br/>+ ranking municipal"]
    H --> I

    classDef stage fill:#eef6ee,stroke:#4a7a4a,color:#1a1a1a;
    classDef output fill:#2f6f4f,stroke:#1a1a1a,color:#ffffff;
    class A,B,C,D,E,F,G,H stage;
    class I output;
```

**Leitura em uma frase:** dados públicos do catálogo GEE viram um cubo de 34 variáveis a 250 m;
esse cubo alimenta, em paralelo, (i) um motor de viabilidade por conhecimento especialista
(fuzzy + AHP) e (ii) um agrupamento não supervisionado em zonas; o motor de viabilidade é
reaplicado ao clima futuro do CMIP6 para projetar a mudança até meados do século; e tudo é
validado contra o uso real da terra e um indicador independente de produtividade.

---

## 2. Pipeline detalhado (para discussão com os orientadores)

Diagrama completo, organizado pelas secções do Capítulo 3. Fase A é o atlas de potencial
biofísico (auto-suficiente, só catálogo público); Fase B traz uso atual da terra e validação;
o bloco CMIP6 é a extensão temporal do motor de viabilidade da Fase A.

```mermaid
flowchart TD
    subgraph FaseA["FASE A — Atlas de potencial biofísico (GEE-only)"]
        direction TB
        A1["§3.1 Engenharia de atributos<br/>34 bandas @ 250 m<br/>clima(14) · terreno(6) · solo(6) · água(3) · fenologia(4) · acesso(1)"]
        A2["§3.2.1 Padronização fuzzy<br/>formas crescente / decrescente / intervalar por fator"]
        A5["§3.2.3 Pesos AHP<br/>matriz Saaty por segmento · RC ≤ 0,10<br/>sensibilidade ±20% por peso"]
        A3["§3.2.2 Agregação<br/>média geométrica ponderada (6 segmentos produtivos)<br/>média aritmética ponderada (conservação, compensatória)"]
        A4["Classes FAO<br/>N · S3 · S2 · S1 (limiares 0,25/0,50/0,75)"]

        A6["§3.3 Descorrelação<br/>34 bandas → 15 bandas curadas → peso por bloco temático → PCA (≥90% var.)"]
        A7["k-means offline (sklearn)<br/>k=2..20 avaliado por silhueta, Davies–Bouldin, gap → k=10"]
        A8["Classificação server-side<br/>centróide mais próximo no espaço de PCs"]
        A9["Perfis de zona<br/>melhor segmento comparativo (argmax do escore-z por segmento)"]

        A1 --> A2 --> A3 --> A4
        A5 --> A3
        A1 --> A6 --> A7 --> A8 --> A9
    end

    subgraph CMIP6["§3.4 Projeção climática — fatores de mudança (delta-change)"]
        direction TB
        C1["NASA NEX-GDDP-CMIP6<br/>5 GCMs × 2 SSPs (2-4.5 / 5-8.5) × 2 janelas (2031–50, 2051–70)"]
        C2["Fatores de mudança mensais<br/>precipitação = razão · temperatura = diferença aditiva"]
        C3["Clima futuro = normal 1991–2020 × fatores<br/>ETP futura por razão de Hargreaves"]
        C4["Reexecuta §3.2 (mesmas regras)<br/>terreno/solo/água/fenologia/acesso mantidos estáticos"]
        C5["ΔS = S_futuro − S_presente<br/>matrizes de transição de classe FAO"]
        C6["Concordância entre modelos<br/>fração de GCMs com o mesmo sinal de ΔS"]

        C1 --> C2 --> C3 --> C4 --> C5
        C4 --> C6
    end

    subgraph FaseB["FASE B — Uso atual da terra e validação"]
        direction TB
        B1["MapBiomas<br/>classe majoritária + frações de uso @ 250 m"]
        B2["Malha Municipal IBGE<br/>agregação municipal (sem upload)"]
        B3["MOD17<br/>NPP anual (contexto) · GPP sazonal por cultura (validador intra-cultura)"]
        B4["Potencial × realizado<br/>mapas de subutilização por município — QP2"]
        B5["AUC / índice de Boyce<br/>presença de lavoura vs. viabilidade — validação QP1"]
        B6["RF de verificação cruzada<br/>κ de Cohen vs. mapa de conhecimento"]
        B7["ANOVA do proxy entre zonas<br/>(as zonas capturam estrutura de produtividade?)"]

        B1 --> B4
        B2 --> B4
        B3 --> B5
        B3 --> B7
    end

    A4 --> B5
    A4 --> B6
    A4 --> C4
    A9 --> B4
    A9 --> B7

    C5 --> Out
    C6 --> Out
    B4 --> Out
    B5 --> Out
    B6 --> Out
    B7 --> Out

    Out["Atlas de viabilidade + zoneamento agroambiental<br/>+ projeção 2050 + ranking municipal<br/>→ responde QP1, QP2, QP3"]

    classDef faseA fill:#eef6ee,stroke:#4a7a4a,color:#1a1a1a;
    classDef cmip fill:#eaf1fb,stroke:#3a5f8a,color:#1a1a1a;
    classDef faseB fill:#fdf3e3,stroke:#9a6f2a,color:#1a1a1a;
    classDef output fill:#2f6f4f,stroke:#1a1a1a,color:#ffffff;
    class A1,A2,A3,A4,A5,A6,A7,A8,A9 faseA;
    class C1,C2,C3,C4,C5,C6 cmip;
    class B1,B2,B3,B4,B5,B6,B7 faseB;
    class Out output;
```

---

## 3. Da metodologia às questões de pesquisa

Diagrama curto para fechar a apresentação — liga cada bloco metodológico à pergunta de
investigação que ele responde.

```mermaid
flowchart LR
    M1["Atlas de viabilidade (7 segmentos)<br/>+ zoneamento agroambiental (k=10)"] --> Q1["QP1 — Como o território se<br/>partição em zonas e qual o<br/>perfil de cada uma?"]
    M2["Potencial × uso realizado<br/>(MapBiomas) + validação (MOD17)"] --> Q2["QP2 — Onde a terra está<br/>subutilizada ou desalinhada<br/>com seu melhor uso?"]
    M3["Projeção CMIP6<br/>(fatores de mudança, 2 SSPs, 2 janelas)"] --> Q3["QP3 — Como a viabilidade<br/>e o zoneamento mudam<br/>até 2050?"]

    classDef method fill:#eef6ee,stroke:#4a7a4a,color:#1a1a1a;
    classDef rq fill:#2f6f4f,stroke:#1a1a1a,color:#ffffff;
    class M1,M2,M3 method;
    class Q1,Q2,Q3 rq;
```

---

## 4. Rastreabilidade — diagrama ⇄ secção da tese ⇄ código

Tabela de apoio para quando um orientador perguntar "isso está implementado onde?".

| Bloco do diagrama | Secção da tese | Notebook | Módulo `src/` |
|---|---|---|---|
| Engenharia de atributos (34 bandas) | §3.1 | `01`–`08` | `src/features.py`, `src/utils.py` |
| Viabilidade fuzzy + AHP | §3.2 | `09_suitability_fuzzy_ahp.ipynb` | `src/membership.py`, `config/segments.yaml`, `config/ahp_matrices.yaml` |
| Zoneamento (PCA + k-means) | §3.3 | `10_zoning_kmeans.ipynb` | `src/zoning.py` (`tools/rezone.py`) |
| Projeção CMIP6 (fatores de mudança) | §3.4 | `11_cmip6_shift.ipynb` | `src/cmip6.py` |
| Uso atual da terra / municípios | §3.5 | `12_municipal_gaul.ipynb`, `13_mapbiomas.ipynb` | `src/external.py` |
| Validação (AUC, Boyce, κ, ANOVA, GPP sazonal) | §3.5 | `14_validation_proxy_rf.ipynb` | `src/external.py`, `src/metrics.py` |
| Atlas final / figuras / ranking municipal | Cap. 4 | `15_atlas_app.ipynb` | `tools/make_figures.py`, `gee_js/atlas_app.js` |

---

### Notas de uso

- Os três primeiros diagramas são independentes — use o **§1** para a abertura de uma
  apresentação/póster, o **§2** para a discussão técnica em reunião de orientação, e o **§3**
  para fechar ligando método → resultado → pergunta de pesquisa.
- Cores seguem uma convenção simples: **verde** = Fase A (potencial biofísico), **azul** =
  bloco climático/CMIP6, **laranja** = Fase B (uso real + validação), **verde-escuro** = saída
  final.
- Para exportar como imagem (PNG/SVG) para o póster, renderize este ficheiro num visualizador
  Mermaid (ex.: [mermaid.live](https://mermaid.live)) ou na extensão Mermaid do editor/IDE.
