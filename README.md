# Viabilidade Agrícola e Projeção Climática do Cerrado Goiano

Atlas de viabilidade agrícola multissegmento, zoneamento agroambiental e projeção
climática CMIP6 para **Goiás + Distrito Federal** (~340.000 km², bioma Cerrado), a 250 m,
construído **inteiramente no Google Earth Engine** (GEE). Não há GPU nem upload de dados,
e o custo é zero no tier não comercial.

Para cada célula de 250 m, o código mapeia o potencial de **sete segmentos**: soja, cana,
outras culturas anuais, piscicultura, pecuária, conservação e solar fotovoltaica.

- **Viabilidade:** lógica fuzzy + AHP, agregadas por média geométrica ponderada e
  classificadas em FAO S1/S2/S3/N.
- **Zoneamento:** o território é agrupado em zonas agroambientais por PCA + k-means.
- **Projeção:** o deslocamento do potencial é projetado para 2031–2070 com
  delta-change CMIP6 (SSP2-4.5/SSP5-8.5).
- **Validação:** contra o uso real da terra (MapBiomas) e a produtividade MODIS MOD17,
  num holdout espacial 50/50.

Este repositório é o material computacional da dissertação abaixo. O atlas interativo
está em <https://ahxsahxs.github.io/goias_suitability> (código em
[`docs/dashboard/`](docs/dashboard/)).

| | |
|---|---|
| **Título** | *Viabilidade Agrícola e Projeção Climática do Cerrado Goiano* |
| **Autor** | Antonio Henrique Xavier da Silva |
| **Orientador** | Prof. Roberto Henriques — NOVA Information Management School (NOVA IMS) |

## Estrutura

```
pipeline.py   # ponto de entrada único: `uv run python pipeline.py --help`
config/       # territory.yaml (O território), datasets, segmentos/AHP, classes MapBiomas
src/          # motor: atributos, viabilidade, zoneamento, CMIP6, validação
tools/        # scripts que o pipeline.py chama (um por etapa)
data/mart/    # malha municipal do território + blocos do holdout espacial
thesis/       # LaTeX da dissertação (template NOVAthesis); CSVs e tabelas geradas
docs/         # protocolo AHP, diagramas de metodologia, dashboard (Vue 3)
```

## Instalação

```bash
uv sync                               # cria .venv/ a partir do uv.lock
uv run earthengine authenticate       # uma vez, interativo
export EE_PROJECT=<seu-projeto-gee>   # projeto Cloud registrado no Earth Engine
```

Use sempre `uv run python ...`. O GDAL/geopandas do sistema só resolve corretamente pelo
ambiente do `uv`.

## Reproduzir a análise de Goiás + DF

Os assets do GEE são gravados em `projects/$EE_PROJECT/assets/goias/`. Cada etapa é
idempotente: pula o que já existe e retoma de onde parou.

Os pesos AHP derivados e os pontos de quebra (`config/segments.yaml`) estão versionados.
O holdout espacial (`data/mart/calib_val_blocks.csv`) também. Por isso, para Goiás, basta
reconstruir os assets:

```bash
P="uv run python pipeline.py"
$P build --until realized    # Partes 1–8 + uso real (MapBiomas)
$P split                     # exporta o holdout a partir do CSV versionado (sem sortear de novo)
$P horizon                   # cache do clima CMIP6 do horizonte (usado nas figuras)
$P build --k 4               # viabilidade, zonas (K=4), CMIP6, municípios
$P verify                    # CRS/escala/extensão de todos os assets (só metadados)
$P validate                  # Parte 14: AUC, Boyce, κ, Spearman (metade de validação)
$P diagnostics               # sensibilidade a λ + teste de eixos de zoneamento
$P report                    # CSVs -> tabelas e figuras da tese
$P dashboard                 # dados do atlas interativo
cd thesis && make            # PDF
```

`uv run python pipeline.py check` roda a verificação offline (sem GEE): os pesos estão em
sincronia com o protocolo AHP e as tabelas da tese são reproduzidas byte a byte.

## Adaptar a outro território (qualquer UF ou conjunto de UFs)

1. **Crie um branch ou fork.** Os passos de calibração reescrevem arquivos versionados:
   pesos e pontos de quebra em `config/segments.yaml`, `config/ahp_matrices.yaml`, o holdout
   e os CSVs/tabelas em `thesis/Chapters/`. Depois edite
   [`config/territory.yaml`](config/territory.yaml): `name`, `asset_subfolder` (uma pasta
   nova no seu projeto GEE), `ufs` e `municipal_asset`.
2. **Baixe a malha municipal do IBGE.** Coloque um `<UF>_Municipios_<ano>.zip` por UF em
   `data/input/ibge/` ([malhas territoriais](https://www.ibge.gov.br/geociencias/organizacao-do-territorio/malhas-territoriais/15774-malhas.html)).
3. **Rode a sequência abaixo.** Os passos marcados com ✋ pedem uma decisão sua.

```bash
P="uv run python pipeline.py"
$P mesh                              # zips IBGE -> malha do território (a AOI é a sua dissolução)
$P build --until realized            # Partes 1–8 + uso real (MapBiomas)
$P build --until suit                # viabilidade provisória (pesos de Goiás)
$P split --new                       # sorteia o holdout 50/50 por blocos; ✋ confira o alcance
                                     #   do variograma vs. o tamanho do bloco (split_n_side)
$P horizon                           # cache do clima CMIP6 do horizonte
$P calibrate breakpoints             # ✋ aplique à mão em config/segments.yaml as edições impressas
$P calibrate weights                 # σ(μ) na metade de calibração -> pesos AHP
$P build --until suit --force suit   # viabilidade com os pesos do território
$P build --until zones               # ✋ leia zoning_kselect.csv e escolha K (colunas *_val/ari_holdout)
$P build --k <K> --force zones       # zonas + CMIP6 + municípios
$P verify && $P validate && $P diagnostics && $P report
```

**O que exige julgamento humano.** Os limiares *agronômicos* em `config/segments.yaml`
(declividade, pH, temperatura…) e as âncoras de literatura em `config/ahp_matrices.yaml`
valem para o Cerrado. Revise-os para biomas muito diferentes, conforme o protocolo em
[`docs/ahp_literatura.md`](docs/ahp_literatura.md). Os limiares *percentílicos* e os pesos
são recalculados para o novo território pelos passos `calibrate`.

**Limitações.** MapBiomas e a malha do IBGE limitam o pipeline ao Brasil. Os textos e o
centro do mapa do dashboard (`docs/dashboard/`) são específicos de Goiás. As tabelas e
figuras da tese usam rótulos de Goiás e servem só para o documento.

## Documentação técnica

[`CLAUDE.md`](CLAUDE.md) traz as convenções, as salvaguardas metodológicas e o mapa
código ⇄ etapa. A justificativa metodológica completa está nos capítulos da tese
([`thesis/Chapters/`](thesis/Chapters/)).
