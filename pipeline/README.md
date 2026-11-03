# bench_pipeline: benchmark de modelos GGUF no Mac mini 1,1

Pipeline para medir, por modelo, **velocidade, térmica, memória e qualidade** com o llama.cpp 32 bits do Mac mini, de forma repetível e com resultados prontos para análise.

## 1. Conteúdo

| Arquivo | Função |
|---|---|
| `pipeline.sh` | Orquestrador: percorre os modelos do manifesto e executa as etapas. |
| `lib_termico.sh` | Sensores (coretemp + applesmc), espera por equilíbrio térmico, logger, vigia de temperatura, ventoinha opcional. |
| `eval_client.py` | Cliente de avaliação de qualidade (conjunto fixo, temperatura 0, seed 42). Só biblioteca padrão. |
| `aggregate.py` | Gera `resultados.csv`, `resumo.md` e gráficos (matplotlib opcional). Roda no Mac mini ou no PC. |
| `questions_pt.jsonl` | 28 perguntas em português, com padrões de resposta aceitos. |
| `models.csv.example` | Manifesto de exemplo. |
| `selftest.sh` | Autoteste com binários simulados (~1 min). |

## 2. Requisitos no Mac mini

- bash 5 (Debian 12 traz 5.2), `lm-sensors`, módulos `coretemp` e `applesmc` (`sudo modprobe coretemp applesmc`).
- Binários 32 bits do llama.cpp em `$BIN` (padrão `~/bin`): `llama-bench`, `llama-server`, e `llama-perplexity` se usar a etapa `ppl`.
- `python3` para as etapas `eval` e para o agregador (`sudo apt install python3`). O agregador também pode rodar no PC.
- Modelos `.gguf` já copiados para o Mac mini (o build não baixa modelos).

## 3. Uso rápido

```bash
# 1. Copie a pasta para o Mac mini e valide a lógica (opcional, ~1 min)
scp bench_pipeline.tar.gz gaia@IP_DO_MAC:~/ && ssh gaia@IP_DO_MAC
tar xzf bench_pipeline.tar.gz && cd bench_pipeline && ./selftest.sh

# 2. Prepare o manifesto
cp models.csv.example models.csv && nano models.csv

# 3. Rode (use tmux: a execução leva horas)
sudo -v                       # só se for usar FAN_RPM
tmux new -s bench
AMB=24 ./pipeline.sh models.csv
```

Exemplos de variações:

```bash
# só velocidade e térmica, 1 e 2 threads
STAGES="verify bench" THREADS="1 2" ./pipeline.sh models.csv

# teste rápido de qualidade (10 perguntas)
STAGES="verify eval" QLIMIT=10 ./pipeline.sh models.csv

# com perplexidade (forneça um texto em português; 2 blocos de 512 tokens)
STAGES="verify bench eval ppl" PPL_FILE=$HOME/texto_pt.txt CHUNKS=2 ./pipeline.sh models.csv

# retomar uma rodada interrompida (modelos com arquivo DONE são pulados)
RUN_DIR=$HOME/runs/run_20261006_200000 ./pipeline.sh models.csv
```

## 4. O que cada etapa faz

1. **`verify`:** calcula o sha256 duas vezes (opcionalmente uma terceira após limpar o cache, `DROPCACHE=1`). Registra se o hash é estável e se confere com a coluna `sha256` do manifesto (quando preenchida). Com `STRICT=1` (padrão), **o modelo é pulado** se o hash divergir do esperado ou for instável.
2. **`bench`:** para cada valor de `THREADS`: espera os núcleos ≤ `TARGET` (52 °C) e o `TC0H` ≤ `GATE_HS` (47,0 °C), faz 60 s de linha de base e roda `llama-bench -p 64 -n 32 -r 3`. Todo o bloco do modelo é registrado em `log.csv` (temperaturas, ventoinha, frequência, carga, throttling, memória livre, swap, RSS e pico de RSS do processo medido).
3. **`eval`:** sobe o `llama-server` (porta 8089, `-c 1024`) e envia as 28 perguntas com temperatura 0, seed 42, `cache_prompt: false` (a latência de cada pergunta é independente das anteriores). Pontua por expressão regular e registra tokens/s de cada resposta.
4. **`ppl`:** `llama-perplexity` sobre `PPL_FILE` (opcional).

Um vigia interrompe o `llama-bench`/`llama-server`/`llama-perplexity` se algum núcleo chegar a `ABORT_C` (95 °C; o limite crítico do chip é 100 °C) e marca o modelo como `ABORTADO_TERMICO`.

## 5. Saídas

```
runs/run_AAAAMMDD_HHMMSS/
  run_meta.txt  models.csv  sensors_inicio.txt  sensors_fim.txt
  resultados.csv  resumo.md  grafico_vazao.png  grafico_qualidade_vs_vazao.png
  <modelo>/
    meta.txt  status.txt  marcadores.csv  log.csv  DONE
    bench_t<N>.csv  bench_t<N>.err
    eval/eval.csv  eval/eval.jsonl  eval/eval_summary.json   eval.log  server.log
    ppl.txt
```

`resultados.csv` tem uma linha por modelo e número de threads: vazão (pp e tg com desvio), pico de RAM, temperatura máxima dos núcleos, `TC0H` máximo, ventoinha máxima, variação do contador de throttling, acertos, perplexidade, e uma **estimativa** de energia (`WATTS`, padrão 31 W, é o TDP; **não é consumo medido**; `TARIFA` é hipotética).

Para reagregar depois (inclusive no PC, com gráficos):

```bash
python3 aggregate.py runs/run_AAAAMMDD_HHMMSS --watts 31 --tarifa 1.00
# se tiver medido a potência com um medidor de tomada:
python3 aggregate.py runs/run_... --watts 38.5 --watts-origem medido
```

## 6. Manifesto (`models.csv`)

```
name,file,quant,params_b,sha256,chat
qwen2.5-0.5b-q5km,/home/gaia/qwen2.5-0.5b-instruct-q5_k_m.gguf,Q5_K_M,0.5,,chat
```

- `sha256` vazio: só verifica a estabilidade entre leituras. Preenchido com o hash publicado: o arquivo precisa conferir, senão é pulado (`STRICT=1`) ou segue com aviso (`STRICT=0`).
- `chat` vazio ou `chat`: usa `/v1/chat/completions`. `completion`: usa `/completion` (modelos sem template de chat).
- Linhas iniciadas por `#` são ignoradas.

## 7. Variáveis úteis

| Variável | Padrão | Significado |
|---|---|---|
| `BIN`, `RUNS`, `RUN_DIR` | `~/bin`, `~/runs`, novo | Binários, pasta de rodadas, retomada. |
| `THREADS` | `2` | Lista; cada valor é uma janela de benchmark (ex.: `"1 2"`). |
| `PP`, `TG`, `REPS` | `64`, `32`, `3` | Parâmetros do `llama-bench`. |
| `BASE` | `60` | Segundos de linha de base antes de cada janela. |
| `TARGET`, `GATE_HS`, `GATE_LABEL` | `52`, `47.0`, `applesmc:TC0H` | Critério de equilíbrio térmico. Use os mesmos valores em todas as rodadas comparadas. |
| `MAXWAIT`, `ABORT_C` | `1200`, `95` | Limite da espera (s) e temperatura de aborto. |
| `CTX`, `MAXTOK`, `QLIMIT`, `PORT` | `1024`, `64`, todas, `8089` | Parâmetros da etapa `eval`. |
| `STRICT`, `DROPCACHE` | `1`, `0` | Integridade (ver seção 4). |
| `FAN_RPM` | vazio | Fixa a rotação da ventoinha |
| `SERVER_EXTRA`, `BENCH_EXTRA`, `PPL_EXTRA` | vazio | Flags adicionais (ex.: `-lm none` se o `llama-server` aceitar). |

## 8. Estimativa de tempo (grosseira)

Baseada nas velocidades já medidas (≈1,6 t/s de prompt e ≈1,3 t/s de geração para o Qwen2.5 0.5B Q5_K_M com 2 threads): por modelo desse porte, `bench` ≈ 10 min por valor de `THREADS` (mais a espera térmica), `eval` ≈ 20 a 40 min para 28 perguntas, `ppl` ≈ 11 min com 2 blocos de 512 tokens. Modelos maiores levam proporcionalmente mais. Use `QLIMIT` e `CHUNKS` para encurtar testes exploratórios.

## 9. Como interpretar com cuidado

- **28 perguntas é um conjunto pequeno.** Com 28 itens, a incerteza de um acerto de ~50% é de cerca de ±18 pontos percentuais (95%). Diferenças de uma ou duas perguntas entre modelos **não são significativas**; use o conjunto para comparar ordens de grandeza e para detectar degradação grande entre quantizações.
- A pontuação é por expressão regular na resposta normalizada: pode aceitar respostas que contenham a palavra certa em contexto errado e rejeitar respostas corretas com outra grafia. Confira `eval/eval.csv` por amostragem.
- `tg` com `MAXTOK` curto mede a velocidade de geração em respostas curtas; o cache KV cresce pouco nesse protocolo.
- Cada janela de bench é **uma rodada**: sem repetição do pipeline não há estimativa de variabilidade entre execuções.
- A espera térmica usa o `TC0H` como critério de equilíbrio; os demais sensores da placa podem continuar acima do estado inicial após a espera (ver relatório térmico v3).
- Pico de RAM é o `VmHWM` do processo, amostrado a cada ~1 s; picos mais curtos que isso podem escapar.
- O tamanho do arquivo e o nome do modelo não bastam como identificação; o `meta.txt` registra tamanho, data e sha256 de cada arquivo usado.
