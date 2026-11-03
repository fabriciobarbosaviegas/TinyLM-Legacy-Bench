# Comparativo: Mac mini 1,1 (Core Duo T2300) vs notebook i5-1035G1

Mesmo modelo (Qwen2.5 0.5B Instruct Q5_K_M, identificado pelo `llama-bench` como 630,17 M de parâmetros e 492,32 MiB nas duas máquinas) e mesmo commit do llama.cpp (`bed0a8566`). Fontes: relatório térmico v3 do Mac mini e `relatorio_experimento_llama_cpp_i5.md`.

**Esta é uma comparação de ordem de grandeza.** Os protocolos não são idênticos e a potência é estimada pelo TDP, não medida (seção 5).

Gráficos: `figures/comp_01_vazao.png`, `figures/comp_02_termico.png`, `figures/comp_03_eficiencia.png`, `figures/comp_04_custo.png`.

---

## 1. Plataformas

| Item | Mac mini 1,1 | Notebook Lenovo IdeaPad S145 |
|---|---|---|
| CPU | Core Duo T2300 (Yonah, 65 nm) | Core i5-1035G1 (Ice Lake, 10 nm) |
| Núcleos / threads | 2 / 2 | 4 / 8 |
| SIMD usado pelo build | até SSE3, 32 bits | AVX2 + FMA (`GGML_NATIVE=ON`), 64 bits |
| RAM | 2 GB DDR2-667 | 8 GB |
| Frequência sob carga | 1,667 GHz (constante) | ~3,3 GHz |
| TDP nominal (CPU) | 31 W | 15 W (configurável de ~13 W a 25 W pelo fabricante do notebook) |
| Tjunction | 100 °C | 100 °C |

Fontes dos TDPs: T2300, listagem de especificações em `product.statnano.com/product/2360/intel-core-duo-(yonah)-cpu` (também `technical.city/en/cpu/Core-Duo-T2300`); i5-1035G1, `en.wikichip.org/wiki/i5-1035g1`, `geektopia.es/es/product/intel/core-i5-1035g1/` (TDP-up 25 W, TDP-down 13 W, Tjunction 100 °C) e `notebookcheck.net` (TDP padrão de 15 W como limite de longo prazo, ajustável pelo fabricante).

## 2. Vazão (Figura 1)

| Configuração | Prompt (t/s) | Geração (t/s) |
|---|---:|---:|
| Mac mini, 1 thread | 0,83 | 0,65 |
| Mac mini, 2 threads | 1,64 | 1,28 |
| i5, 1 thread | 52,44 | 26,88 |
| i5, 2 threads | 100,82 | 45,14 |
| i5, 4 threads | 128,95 | 59,09 |
| i5, 8 threads | 125,72 | 59,56 |

Melhor configuração de cada máquina (Mac mini com 2 threads: pp 1,6416 e tg 1,2757 na rodada v3; i5 com 4 threads):

- **Prompt:** o i5 é ~**79×** mais rápido (128,95 ÷ 1,6416).
- **Geração:** o i5 é ~**46×** mais rápido (59,09 ÷ 1,2757).
- Gerar 1 000 tokens leva ~784 s (13 min) no Mac mini e ~17 s no i5.
- O Mac mini escala quase linearmente de 1 para 2 threads (2 núcleos físicos). O i5 satura em 4 threads (4 núcleos físicos); os 8 threads lógicos não trazem ganho relevante.

Diferenças de protocolo: Mac mini com `-p 64 -n 32 -r 3`; i5 com `-p 128 -n 256 -r 5`. As taxas de geração dependem pouco desses valores, mas isso não foi testado.

## 3. Térmica (Figura 2)

| Sensor | Mínimo (°C) | Média (°C) | Máximo (°C) |
|---|---:|---:|---:|
| Mac Core 0 | 52 | 75,3 | 82 |
| Mac Core 1 | 59 | 77,4 | 84 |
| i5 Package | 57 | 69 | 79 |
| i5 Core 0 / 1 / 2 / 3 (máx) | 44 / 40 / 57 / 42 | 61 / 58,7 / 68 / 59,7 | 72 / 72 / 76 / 71 |

- Os dois chips ficaram abaixo do limite de 100 °C: margem de ~16 °C no Mac mini (pico de 84 °C) e de ~21 °C no i5 (pico do package de 79 °C).
- Nas duas máquinas não há indício de limitação térmica: no Mac mini o contador de throttling ficou em 0; no i5 o contador ficou constante em 3580 (o relatório do i5 observa que o correto é comparar valor inicial e final).
- **Cuidado:** os protocolos térmicos diferem (Mac mini: 2 threads, 234 s de carga a partir de ~46 °C; i5: 4 threads, duração e estado inicial não informados). Os números mostram que ambos operam dentro da margem, mas não permitem dizer qual esquenta mais para a mesma carga. Os "mínimos" dependem de onde a janela de cada medição começa.

## 4. Eficiência e custo estimados a partir do TDP (Figuras 3 e 4)

### 4.1 Premissas

- Potência usada = **TDP do processador**: 31 W (Mac mini) e 15 W (i5). Como o fabricante do notebook pode configurar o limite de 12–25 W, mostrei também o i5 com 25 W.
- Vazão de geração: 1,2757 t/s (Mac mini) e 59,09 t/s (i5, 4 threads).
- Tarifa de energia **hipotética**: R$ 0,80, 1,00 e 1,20 por kWh. Procurei a tarifa vigente no Rio Grande do Sul, mas as fontes que encontrei trazem só percentuais de reajuste, não o valor em R$/kWh; confirme na sua fatura e substitua.

### 4.2 Fórmulas

```
tokens por joule        = (tokens/s) ÷ W
joules por token        = W ÷ (tokens/s)
kWh por 1 milhão tokens = (J/token × 10⁶) ÷ 3,6×10⁶
custo por 1 milhão      = kWh por 1 milhão × tarifa (R$/kWh)
custo de 1 W contínuo   = 0,72 kWh/mês × tarifa   (24 h × 30 dias ÷ 1000)
```

### 4.3 Resultados (geração)

| Métrica | Mac mini (31 W) | i5 (15 W) | i5 (25 W) |
|---|---:|---:|---:|
| W por token/s | 24,3 | 0,254 | 0,423 |
| Joules por token | 24,3 | 0,254 | 0,423 |
| Tokens por joule | 0,0412 | 3,94 | 2,36 |
| Energia por 1 000 tokens (Wh) | 6,75 | 0,0705 | 0,1175 |
| Energia por 1 milhão de tokens (kWh) | 6,75 | 0,0705 | 0,1175 |
| **Custo por 1 milhão de tokens a R$ 0,80/kWh** | **R$ 5,40** | R$ 0,056 | R$ 0,094 |
| **a R$ 1,00/kWh** | **R$ 6,75** | R$ 0,071 | R$ 0,118 |
| **a R$ 1,20/kWh** | **R$ 8,10** | R$ 0,085 | R$ 0,141 |

Para o prompt (tokens processados por joule): Mac mini 0,053; i5 8,60 (15 W) ou 5,16 (25 W).

**Razão de eficiência (geração):** o i5 gera ~**96×** mais tokens por joule que o Mac mini com TDP de 15 W, e ~**57×** com TDP de 25 W.

### 4.4 "Custo por watt" em termos de operação contínua

Cada watt mantido ligado por um mês consome 0,72 kWh, ou R$ 0,58 / 0,72 / 0,86 nas três tarifas. Funcionando continuamente ao TDP:

| | kWh/mês | R$/mês (R$ 1,00/kWh) |
|---|---:|---:|
| Mac mini (31 W) | 22,3 | 22,32 |
| i5 (15 W) | 10,8 | 10,80 |
| i5 (25 W) | 18,0 | 18,00 |

Esse valor é o custo do processador ligado, independente de produzir tokens. A vantagem do i5 está em produzir muito mais tokens por esse mesmo gasto.

## 5. Limitações das estimativas

1. **TDP não é consumo.** É uma especificação térmica de projeto. O consumo real sob esta carga pode ser bem diferente (maior ou menor) nas duas máquinas. A razão de ~57× a ~96× é nominal, e é razoável esperar variação relevante.
2. **Só o processador.** O TDP não inclui memória, chipset, disco, ventoinha, tela, GPU integrada nem perdas da fonte. O consumo da máquina inteira é maior nas duas, e a razão entre elas pode mudar.
3. **Limites de potência do notebook.** Não se sabe qual limite (PL1/PL2) o IdeaPad S145 usa. O i5 sustentou ~3,3 GHz em todos os núcleos, o que sugere que não ficou travado em 15 W durante o teste, mas isso é uma inferência.
4. **Protocolos diferentes** (comprimento de prompt e geração, repetições, número de threads, build 32 bits vs 64 bits com AVX2) e térmico não equivalente (seção 3).
5. **Tarifa hipotética.** Os valores em reais escalam linearmente com a tarifa.
6. **Qualidade do modelo fora do escopo:** tokens/s e custo por token não dizem nada sobre a qualidade das respostas.

## 6. Como trocar a estimativa por medição

- **i5:** o relatório do i5 já prevê leitura de RAPL. Em Linux, a energia do package fica em `/sys/class/powercap/intel-rapl:0/energy_uj` (contador em microjoules) e o limite de longo prazo em `constraint_0_power_limit_uw`. Ler o contador antes e depois do benchmark dá os joules, e dividindo pelos tokens gerados obtém-se J/token real do processador. Pode exigir `sudo` para leitura, conforme a configuração do kernel.
- **Mac mini:** o Yonah não tem RAPL; só um medidor de tomada permite medir. Idealmente use o mesmo medidor nas duas máquinas, medindo a máquina inteira em repouso e sob carga.
- Com os dois valores medidos, as fórmulas da seção 4.2 se aplicam sem mudança, trocando o TDP pela potência média medida.
