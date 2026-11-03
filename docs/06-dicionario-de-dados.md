# Dicionário de dados

## Pasta de execução do bench térmico legado (`data/raw/<maquina>/termico/<id>/`)

| Arquivo | Conteúdo |
|---|---|
| `meta.txt` | `chave: valor` por linha: data, kernel, cpu, governor, modelo, threads, temperatura ambiente, parâmetros do script; v3 acrescenta `script`, `modelo_stat`, `target_*`, `gate_*`, `inicio_*`, `fim_*`, `sha256_leitura1/2`, `hash_estavel`; v1 tem `sha256_modelo` |
| `marcadores.csv` | `nome,epoch` (instante de cada fase) |
| `log.csv` | série temporal, uma linha por ~1 s (colunas abaixo) |
| `bench.csv` | saída do `llama-bench -o csv` |
| `bench.err` | stderr do `llama-bench` (vazio = sem erros) |
| `resumo_bench.txt` | mínimo, média e máximo de cada coluna do log na janela do benchmark |
| `sensors_inicio.txt`, `sensors_fim.txt` | saída do `sensors` (só v3), inclui limites `crit` |

### Marcadores

| v1 | v3 / pipeline |
|---|---|
| `baseline_inicio`, `bench_inicio`, `bench_fim`, `fim` | `espera_inicio`, `espera_fim`, `baseline_inicio`, `bench_inicio`, `bench_fim`, `fim`. No pipeline os nomes ganham sufixo por janela (`bench_t2_inicio`, `bench_t2_fim`, ...) e há `verify_*`, `eval_*`, `ppl_*`. |

### Colunas de `log.csv`

| Coluna | Unidade | Origem |
|---|---|---|
| `epoch` | s (Unix, fracionário) | `$EPOCHREALTIME` |
| `coretemp:Core_0_C`, `coretemp:Core_1_C` | °C (inteiro) | driver `coretemp` |
| `applesmc:TA0P_C`, `TC0D_C`, `TC0H_C`, `TC0P_C`, `TC1P_C`, `TN0P_C`, `TN1P_C` | °C (0,1) | `applesmc` (nomes seguem o SMC; posição física não confirmada) |
| `applesmc:Master__rpm` | rpm | ventoinha |
| `freq_cpu0_kHz`, `freq_cpu1_kHz` | kHz | `scaling_cur_freq` |
| `load1` | adimensional | `/proc/loadavg` (média de 1 min; defasada) |
| `throttle_count` | contagem | soma de `core_throttle_count`; **vazio** se o contador não existir |
| `mem_avail_kB`, `swap_used_kB` | kB | `/proc/meminfo` (só pipeline) |
| `proc_rss_kB`, `proc_hwm_kB` | kB | `VmRSS`/`VmHWM` do processo medido (só pipeline) |

Valores vazios significam "não disponível", nunca zero.

### `bench.csv` (campos usados)

`model_type`, `model_size` (bytes dos tensores, **não** o tamanho do arquivo), `model_n_params`, `n_threads`, `n_prompt` e `n_gen` (linha de prompt: `n_gen = 0`; linha de geração: `n_prompt = 0`), `avg_ts` e `stddev_ts` (tokens/s entre as repetições), `test_time` (UTC, **início** de cada teste), `build_commit`.

## Rodada do pipeline (`data/raw/<maquina>/pipeline/<run>/`)

| Item | Conteúdo |
|---|---|
| `run_meta.txt` | parâmetros e ambiente da rodada (um `chave: valor` por linha) |
| `models.csv`, `sensors_inicio.txt`, `sensors_fim.txt` | manifesto usado e snapshots do `sensors` |
| `resultados.csv`, `resumo.md`, `grafico_*.png` | saídas do `aggregate.py` (derivadas; reproduzíveis) |
| `<modelo>/meta.txt`, `status.txt`, `marcadores.csv`, `log.csv`, `DONE` | por modelo |
| `<modelo>/bench_t<N>.csv`, `.err` | `llama-bench` por número de threads |
| `<modelo>/eval/eval.csv`, `eval.jsonl`, `eval_summary.json` | avaliação de qualidade |
| `<modelo>/ppl.txt`, `eval.log`, `server.log` | perplexidade e logs |

### `status.txt`

`ok`, ou combinações de: `SKIP_INTEGRIDADE`, `ABORTADO_TERMICO`, `bench_t<N>_falhou`, `eval_falhou`, `ppl_falhou`, `ERRO_ARQUIVO`.

### `resultados.csv`

Uma linha por modelo e número de threads: `modelo, quant, params_B, threads, model_type, model_size_MiB, status, hash_estavel, hash_confere_manifesto, pp_tps, pp_desvio, tg_tps, tg_desvio, n_prompt, n_gen, core_temp_media_C` (média do núcleo mais quente), `core_temp_max_C, tc0h_max_C, fan_max_rpm, throttle_delta, freq_media_MHz, pico_rss_MB, mem_avail_min_MB, swap_max_MB, gate_ok, inicio_gate_C, acuracia, acertos, eval_pred_tps_medio, ppl, ppl_erro, J_por_token, tokens_por_J, R$_por_milhao_tokens, build_commit`. As três últimas de energia usam o TDP informado (`--watts`) e **não** são consumo medido.

## Catálogo de modelos (`models/manifest.csv`)

`nome, arquivo, quant, params_b, tamanho_bytes, sha256_publicado, fonte, licenca, status (ativo|candidato|descartado), chat (chat|completion), observacoes`.
