# EXP-2026-001: linha de base térmica do Mac mini 1,1 com Qwen2.5 0.5B Q5_K_M

- **Data:** 2026-10-03
- **Status:** `em análise` (rodada única da v3; falta repetir)
- **Pergunta:** qual é o comportamento térmico e de desempenho do Mac mini 1,1 (Core Duo T2300) durante a inferência de um SLM de 0,5B com o llama.cpp em 32 bits?
- **Observação metodológica:** este experimento **não foi pré-registrado** (foi exploratório; o método evoluiu entre as rodadas). Os próximos devem usar `experiments/_template/`.

## Resumo dos resultados

Detalhes e números em `reports/2026-10-04_relatorio-termico-v3-macmini.md`.

- Núcleos: de ~46 °C (ocioso) a 82 °C (Core 0) e 84 °C (Core 1) em ~234 s de carga com 2 threads; limite crítico informado pelo driver: 100 °C.
- `throttle_count` = 0 (contador disponível), frequência sob carga constante em ~1 666,5 MHz.
- Ventoinha em controle automático: máximo de 1 697 rpm (limite do equipamento: 5 500 rpm).
- Resfriamento: núcleos ≤ 60 °C em 40 s; dissipador (`TC0H`) levou 282 s para voltar a ≤ 47,0 °C.
- Desempenho (v3): 1,6416 t/s no prompt e 1,2757 t/s na geração.

## Dados

| Máquina | Pasta | Script | Observações |
|---|---|---|---|
| macmini-1-1 | `data/raw/macmini-1-1/termico/20261003_145137_v1_qwen2.5-0.5b-q5km` | bench_termico v1 | logger com mais custo de CPU (intervalo de amostragem ~1,09 s); sem sensores applesmc |
| macmini-1-1 | `data/raw/macmini-1-1/termico/20261003_191125_v1_qwen2.5-0.5b-q5km` | bench_termico v1 | idem |
| macmini-1-1 | `data/raw/macmini-1-1/termico/20261003_200114_v3_qwen2.5-0.5b-q5km` | bench_termico v3 | espera por equilíbrio térmico, sensores applesmc, throttle confiável |

Uma rodada da v2 foi executada, mas seus arquivos **não foram arquivados**; só restam os números citados no histórico de conversas do projeto (não use como dado primário).

## Desvios, limitações e pendências

- Rodada única da v3: sem estimativa de variabilidade entre execuções.
- O sha256 do arquivo do modelo registrado nas três rodadas **não é o mesmo** e não confere com o hash publicado. Ver `docs/07-integridade-dos-modelos.md`. A velocidade (t/s) provavelmente não depende dos valores dos pesos, mas isso precisa ser resolvido antes de qualquer análise de qualidade.
- [ ] Repetir a v3 pelo menos 3 vezes com os mesmos parâmetros.
- [ ] Rodar o `llama-bench` sem registro (3 vezes) para quantificar o efeito do logger.
- [ ] Repetir com `GATE_HS` mais baixo (por exemplo 46,0 °C).
- [ ] Inverter a ordem pp/tg para separar tempo de tipo de carga.
- [ ] Medir potência com medidor de tomada.
