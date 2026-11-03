# Metodologia térmica

Resumo do método implementado em `pipeline/lib_termico.sh` (e, antes, em `tools/legacy/bench_termico_v3.sh`). O relatório completo de uma rodada é `reports/2026-10-04_relatorio-termico-v3-macmini.md`.

## Instrumentação

| Grandeza | Fonte | Observações |
|---|---|---|
| Núcleos | `coretemp` (hwmon) | resolução de 1 °C; `crit` = 100 °C |
| Placa | `applesmc`: `TA0P`, `TC0D`, `TC0H`, `TC0P`, `TC1P`, `TN0P`, `TN1P` | posição física **não confirmada**; interpretações são provisórias |
| Ventoinha | `applesmc` (`Master`) | controle automático do SMC |
| Frequência | `scaling_cur_freq` | valor do kernel, não medição independente |
| Throttling | `thermal_throttle/core_throttle_count` | coluna vazia se o contador não existir (nunca "0" falso) |
| Memória | `/proc/meminfo`, `/proc/<pid>/status` (pipeline) | pico de RSS = `VmHWM`, amostrado a ~1 s |

O applesmc expõe os arquivos em `/sys/devices/platform/applesmc.*`, não em `/sys/class/hwmon/hwmonN/`; o script procura nos dois lugares.

## Protocolo de uma janela de medição

1. **Espera por equilíbrio:** núcleos ≤ `TARGET` (52 °C) **e** `TC0H` ≤ `GATE_HS` (47,0 °C), com limite `MAXWAIT` (1200 s).
2. **Linha de base:** 60 s ocioso.
3. **Carga:** `llama-bench -t N -p 64 -n 32 -r 3`.
4. **Janelas de análise:** baseline = 10 s após o início da linha de base até o início da carga; carga = `bench_inicio` a `bench_fim`; fases pp e tg pelos `test_time` do `bench.csv`.

Proteção: se algum núcleo atingir `ABORT_C` (95 °C), o benchmark é encerrado e a execução fica marcada como parcial.

## Por que o critério usa o dissipador

Os núcleos (sensor do próprio chip, pouca massa térmica) voltam a ~50 °C em segundos, mas o dissipador e a placa levam minutos. Esperar só pelos núcleos faz a rodada seguinte começar mais quente do que parece. Ver [ADR 0002](adr/0002-gate-termico-no-dissipador.md).

## Cuidados de interpretação

- Uma rodada não estima variabilidade; repita.
- O Core 1 aparece ~2 °C acima do Core 0 de modo consistente: pode ser diferença de sensor, não de calor real.
- A primeira amostra do log costuma estar mais quente (a CPU ainda estava em frequência máxima por atividade anterior ao registro): descarte os primeiros 10 s da linha de base.
- Em repouso o kernel informa ~1,0–1,2 GHz mesmo com governor `performance`; sob carga, 1 666,5 MHz constantes. A linha de base térmica corresponde ao estado de baixa frequência.
- O pico de temperatura dos sensores da placa pode ocorrer **depois** do fim da carga (atraso térmico).
- A ventoinha reage com atraso de dezenas de segundos; o pico de rpm ocorreu após o fim da carga.

## Potência e energia

Não há medida de potência: o Core Duo não tem RAPL e o equipamento não oferece outra leitura. Estimativas usam o TDP (31 W, especificação) e são **limites nominais**, não consumo. Ver [ADR 0003](adr/0003-tdp-como-estimativa-de-potencia.md).

## Histórico das versões do script

| Versão | Mudança | Motivo |
|---|---|---|
| v1 | `coretemp` + frequência + load, resfriamento fixo de 120 s | primeira versão |
| v2 | sensores e ventoinha do applesmc, espera por núcleos ≤ `TARGET`, throttle vazio quando indisponível, laço com comandos internos do bash | v1 custava ~2% de desempenho (processos por segundo) e não via o applesmc |
| v3 | espera pelo dissipador, hash depois do teste, ventoinha fixa opcional, vigia de temperatura | núcleos esfriam rápido demais para servir de critério único |
| pipeline | v3 generalizado para vários modelos + memória/RSS + avaliação | ver `docs/03-pipeline.md` |
