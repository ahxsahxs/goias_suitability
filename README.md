# Viabilidade Agrícola e Projeção Climática do Cerrado Goiano

Atlas de viabilidade agro-mercado multi-segmento + zoneamento agroambiental + projeção
climática CMIP6 para **Goiás + Distrito Federal** (~340.000 km², bioma Cerrado), a 250 m,
construído **inteiramente dentro do Google Earth Engine** (sem GPU, sem upload de dados
grandes, sem custo de nuvem além do tier gratuito/não-comercial do GEE).

O código mapeia o potencial biofísico/agroclimático de cada célula de 250 m para **sete
segmentos de uso da terra** — soja · cana-de-açúcar · outras culturas anuais (milho/algodão/
sorgo) · piscicultura · pecuária (pastagem cultivada) · conservação florestal/Cerrado ·
geração solar fotovoltaica —, agrupa o território em zonas agroambientais e projeta como
esse potencial se desloca até 2031–2070 sob os cenários CMIP6 SSP2-4.5/SSP5-8.5. É depois
validado contra o uso real da terra (MapBiomas) e um proxy de produtividade MODIS (MOD17).

Este repositório é o material de suporte computacional da dissertação de mestrado abaixo —
se chegaste aqui a partir do PDF da tese, é este o código, os dados e as figuras por trás
dos resultados.

## A dissertação

| | |
|---|---|
| **Título (PT)** | *Viabilidade Agrícola e Projeção Climática do Cerrado Goiano* |
| **Título (EN)** | *Agricultural Suitability and Climatic Projection of Cerrado Goiano* |
| **Autor** | Antonio Henrique Xavier da Silva |
| **Orientador** | Prof. Roberto Henriques, Professor Catedrático, Universidade NOVA de Lisboa |
| **Instituição** | NOVA Information Management School (NOVA IMS) |

O código-fonte LaTeX da tese vive em [`thesis/`](thesis/) (template NOVAthesis/NOVA IMS). O
PDF compilado **não é versionado** (ver [`.gitignore`](.gitignore)); para o gerar:

```bash
cd thesis
make            # latexmk + pdfLaTeX, produz template.pdf
```

## Estrutura do repositório

```
config/       # YAML: datasets GEE, parâmetros de suitability/AHP, classes MapBiomas
src/          # motor da análise (feature engineering, suitability, zoneamento, CMIP6, validação)
tools/        # scripts de execução: build, verificação, figuras, recalibração
notebooks/    # 19 notebooks finos, gerados a partir de tools/gen_notebooks.py — um por Part (1-15)
docs/         # notas de apoio (termos de pesquisa, diagrama de metodologia)
thesis/       # código-fonte LaTeX da dissertação (template NOVAthesis / NOVA IMS)
gee_js/       # script do Earth Engine App (atlas interativo, Part 15)
```

Ver [`CLAUDE.md`](CLAUDE.md) para a documentação técnica completa: metodologia, convenções de
dados, mapa notebook⇄Part⇄código, como editar a tese e como correr/reproduzir cada etapa.

## Estado do projeto

As **Fases A (potencial biofísico) e B (uso realizado + validação)** estão construídas e
verificadas — **Parts 1–14** de um total de 15, com todos os assets do Earth Engine
confirmados em CRS/escala/footprint corretos. As três perguntas de investigação da tese
(zoneamento, potencial vs. realizado, projeção CMIP6) estão respondidas e escritas nos
capítulos 01–05.

Falta apenas publicar o **atlas interativo (Part 15)**: o script já está pronto em
[`gee_js/atlas_app.js`](gee_js/atlas_app.js), só falta o passo manual de publicação no GEE
Code Editor.

## Reprodução rápida

```bash
# ambiente (uv gere o venv em .venv/ na raiz do repo)
uv sync
source .venv/bin/activate

# autenticação Earth Engine (uma vez, interativo)
earthengine authenticate

# projeto GEE usado em todo o pipeline
export EE_PROJECT=probformer

# verificação de fumo: confirma que os assets já construídos estão corretos
# (só lê metadados — funciona mesmo com quota de computação restrita)
python tools/verify_assets.py
```

Instruções completas de ambiente, execução da Fase A, regeneração de notebooks e todos os
comandos de manutenção estão no [`CLAUDE.md`](CLAUDE.md).
