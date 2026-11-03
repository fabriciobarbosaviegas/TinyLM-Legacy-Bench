# slm-legacy-bench

Benchmark de **pequenos modelos de linguagem (SLMs)** com motores de inferência como o llama.cpp em **hardware legado**, começando por um Mac mini 1,1 (Core Duo T2300, 32 bits, 2 GB) e comparando com um notebook i5-1035G1. O repositório reúne o pipeline de medição (velocidade, térmica, memória, qualidade), os dados brutos, a metodologia, os relatórios e o planejamento dos próximos estudos, para que a equipe trabalhe de forma organizada e reprodutível.

## Estado atual

| Item | Estado |
|---|---|
| llama.cpp 32 bits (SSE3) rodando no Mac mini | **feito** (build em contêiner Debian 12; `docs/01`) |
| Bench térmico | **feito** |
| Linha de base do i5-1035G1 | **feito** (só o relatório; sem dados brutos arquivados) |
| Pipeline multi-modelo (`pipeline/`) | **escrito e testado com binários simulados**; **ainda não executado** |
| Conjuntos de perguntas (20 manual, 28 automático) | **feito**; amostra pequena (ver `docs/04`) |
| Estudo "hardware x qualidade das respostas" | **protocolo em rascunho** (`docs/05`); nenhum dado coletado |
| Integridade do `.gguf` no Mac mini | **em aberto** |
| Medida real de potência | **pendente** (TDP é só uma estimativa nominal; `docs/adr/0003`) |

## Resultados já obtidos (Mac mini 1,1, Qwen2.5 0.5B Q5_K_M, 2 threads)

- Vazão: ~1,64 t/s no prompt e ~1,28 t/s na geração (o i5 fica em ~129 e ~59 t/s com 4 threads; protocolos diferentes).
- Térmica (rodada v3, uma só): núcleos de ~46 °C a 82–84 °C em ~234 s de carga (crit = 100 °C); sem throttling; ventoinha em automático chegou a 1 697 rpm (máx. 5 500).
- Detalhes, limitações e ressalvas: `reports/`.

## Início rápido

```bash
git clone <url-do-repositorio> && cd slm-legacy-bench
make test                      # unitários + autoteste do pipeline + validação dos dados + lint
make help                      # demais atalhos
```

Rodar o pipeline de verdade (depois de instalar os binários 32 bits; ver `docs/01`):

```bash
python3 tools/make_pipeline_manifest.py --models-dir ~/models --status ativo -o models.csv
AMB=24 pipeline/pipeline.sh models.csv         # dentro do tmux
python3 tools/validate_run.py ~/runs/run_...   # antes de arquivar em data/raw/
```

## Estrutura de pastas

```
slm-legacy-bench/
├── README.md  CONTRIBUTING.md  CHANGELOG.md  CITATION.cff  LICENSE  LICENSE-DATA.md  Makefile
├── .github/                 CI (workflows/ci.yml), templates de issue/PR, CODEOWNERS
├── docs/                    metodologia, dicionário de dados, integridade, protocolo do estudo, glossário
│   └── adr/                 decisões de projeto (uma por arquivo)
├── hardware/                inventário: um YAML por máquina
├── build/                   build 32 bits em contêiner + verificação do binário
├── models/                  catálogo de modelos (sem pesos no Git)
├── pipeline/                pipeline de benchmark (bash + python, só biblioteca padrão)
├── tools/                   validação, figuras, novo experimento, conversor de manifesto
│   └── legacy/              scripts do bench térmico v1, v2 e v3
├── questions/               perguntas de avaliação manual
├── experiments/             um experimento por pasta (pré-registro, protocolo, resumo)
│   └── _template/
├── data/
│   ├── raw/<maquina>/...    execuções originais (imutáveis)
│   └── processed/           derivados reproduzíveis
├── reports/                 relatórios e figuras
└── tests/                   testes unitários (unittest)
```

## Como trabalhar aqui

1. **Quer propor algo?** Abra uma issue (`Proposta de experimento`).
2. **Vai coletar dados?** `tools/new_experiment.sh <slug> "Título"`, preencha o `PREREGISTRO.md` **antes** e faça commit.
3. **Coletou?** Valide (`tools/validate_run.py`), arquive em `data/raw/` (imutável), reagregue e escreva o relatório em `reports/`.
4. **Abra um PR** com o modelo do repositório (lista de verificação incluída). `main` fica sempre verde.

Regras e convenções completas: [`CONTRIBUTING.md`](CONTRIBUTING.md). Mapa da documentação: [`docs/README.md`](docs/README.md).

## Princípios de reprodutibilidade

- Dados brutos imutáveis; derivados regeneráveis por script.
- Todo resultado cita commit do repositório, commit do llama.cpp, build/flags, ambiente e sha256 do modelo.
- Parâmetros térmicos e de execução idênticos entre rodadas comparadas.
- Estimativas e hipóteses rotuladas como tal; limitações sempre declaradas.
- Modelos e logits (`.gguf`, `.kld`) nunca entram no Git.

## Requisitos

bash ≥ 5, python3 (biblioteca padrão; `matplotlib` só para figuras), Docker no PC de build. No Mac mini: `lm-sensors`, módulos `coretemp` e `applesmc`, `libgomp1`, `libatomic1`, e `python3` para a etapa de avaliação.

## Citação e licença

Veja `CITATION.cff` (autores a definir). Código sob MIT (`LICENSE`); licença de dados e documentação pendente (`LICENSE-DATA.md`). Cada modelo tem a sua licença.
