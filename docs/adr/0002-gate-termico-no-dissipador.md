# ADR 0002: critério de equilíbrio térmico baseado também no dissipador

- **Data:** 2026-10-03
- **Status:** aceita

## Contexto

Na rodada v2, esperar só os núcleos ≤ 52 °C encerrou a espera com o dissipador (`TC0H`) 3,7 °C acima do início. O sensor dos núcleos responde em segundos; a placa em minutos.

## Decisão

Uma janela só começa (e o resfriamento só termina) quando núcleos ≤ `TARGET` **e** `TC0H` ≤ `GATE_HS` (padrão 47,0 °C), com limite `MAXWAIT`. Os valores devem ser os mesmos em todas as rodadas comparadas.

## Consequências

- Esperas mais longas (na rodada v3, 282 s após o teste).
- Estado inicial mais repetível, mas ainda aproximado: `GATE_HS=47.0` é mais frouxo que o estado observado no início da rodada v3 (44,5 °C). Avaliar `GATE_HS=46.0`.
- Depende de o sensor `applesmc:TC0H` existir; sem ele o script usa só os núcleos e avisa.

## Alternativas consideradas

Tempo fixo de resfriamento (não garante equilíbrio); critério só nos núcleos (insuficiente); gate no ar interno (`TA0P`, não avaliado).
