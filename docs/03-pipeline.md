# Pipeline: fluxo de trabalho

O código está em `pipeline/` (documentação de uso em [`pipeline/README.md`](../pipeline/README.md)). Esta página descreve o fluxo da equipe.

> **Status de validação:** testado de ponta a ponta com binários e sensores **simulados** (`pipeline/selftest.sh`) e em cenários de falha. **Ainda não foi executado no Mac mini real.** A primeira execução real deve ser registrada como experimento (ver `experiments/`).

## Fluxo

```
models/manifest.csv (catálogo)
        │  tools/make_pipeline_manifest.py --models-dir ~/models
        ▼
models.csv (manifesto do pipeline)
        │  pipeline/pipeline.sh models.csv        (no Mac mini, dentro do tmux)
        ▼
~/runs/run_AAAAMMDD_HHMMSS/        (resultados brutos + resumo)
        │  scp para o PC
        ▼
data/raw/<maquina>/pipeline/<run>/ (imutável) ──► tools/validate_run.py ──► commit
        │  pipeline/aggregate.py (reagregar, se necessário)
        ▼
data/processed/ + reports/ + experiments/<EXP>/README.md
```

## Passo a passo

1. **Crie o experimento** e preencha o pré-registro: `tools/new_experiment.sh <slug> "Título"`.
2. **Prepare o catálogo** (`models/manifest.csv`): hash e tamanho publicados quando existirem.
3. **Gere o manifesto**: `python3 tools/make_pipeline_manifest.py --models-dir /home/gaia/models --status ativo -o models.csv`.
4. **Valide a lógica** (opcional): `pipeline/selftest.sh`.
5. **Execute no Mac mini** (tmux): `AMB=24 pipeline/pipeline.sh models.csv`. Use os mesmos `TARGET`, `GATE_HS` e demais parâmetros em todas as rodadas comparadas.
6. **Traga os resultados** para o PC e **valide**: `python3 tools/validate_run.py <pasta>`. Qualquer `FAIL` impede o commit; `WARN` deve ser comentado no README do experimento.
7. **Arquive**: mova a pasta para `data/raw/<maquina>/pipeline/<AAAAMMDD_HHMMSS>_<descricao>/` e **não edite mais** os arquivos dela.
8. **Reagregue e analise** (`pipeline/aggregate.py`, `tools/plot_thermal.py`), gere o relatório em `reports/` e atualize o README do experimento.

## Convenção de nomes (dados brutos)

`data/raw/<maquina>/<tipo>/<AAAAMMDD_HHMMSS>_<script>_<modelo>/` onde `<maquina>` é o id em `hardware/` (ex.: `macmini-1-1`) e `<tipo>` é `termico` (rodadas do bench térmico legado) ou `pipeline`.

## Limitações conhecidas

- Uma janela de benchmark = uma rodada (sem variabilidade entre execuções).
- O conjunto automático de 28 perguntas é pequeno (±18 pontos percentuais de incerteza em acerto ~50%). Ver `docs/04-avaliacao-de-qualidade.md`.
- Flags do `llama-server` e do `llama-perplexity` mudam entre versões do llama.cpp: erros aparecem em `server.log` / `ppl.txt`; use `SERVER_EXTRA` / `PPL_EXTRA`.
- O controle manual da ventoinha (`FAN_RPM`) não foi verificado no Mac mini 1,1.
