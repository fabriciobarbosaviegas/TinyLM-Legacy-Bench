# ADR 0003: usar o TDP como estimativa nominal de potência

- **Data:** 2026-10-05
- **Status:** aceita (provisória)

## Contexto

O Core Duo T2300 não tem RAPL e não há medidor de potência. Para comparar eficiência (tokens por joule, custo) foi usado o TDP.

## Decisão

Estimativas de energia usam o TDP do processador (31 W para o T2300; 15 W, com variação de ~13 a 25 W, para o i5-1035G1) e são rotuladas como **limite nominal, não consumo**. A tarifa de energia é hipotética (R$ 0,80 a 1,20/kWh) até haver valor da fatura.

## Consequências

- O TDP não inclui memória, chipset, disco, tela nem perdas da fonte; razões entre máquinas são ordens de grandeza.
- Substituir por medida real: RAPL (`/sys/class/powercap/intel-rapl:0/energy_uj`) no i5 e medidor de tomada no Mac mini; `aggregate.py --watts <W> --watts-origem medido`.

## Alternativas consideradas

Não estimar energia (perde a comparação); estimar por frequência e carga (sem modelo calibrado).
