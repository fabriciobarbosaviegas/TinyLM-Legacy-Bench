# Glossário

| Termo | Significado |
|---|---|
| SLM | *Small Language Model*: modelo de linguagem pequeno (aqui, ≲ 1B de parâmetros). |
| GGUF | Formato de arquivo de modelos do llama.cpp. |
| Quantização (Q4_0, Q5_K_M, Q8_0...) | Representação dos pesos com menos bits; reduz tamanho e muda a qualidade. |
| pp / tg | Processamento de prompt / geração de tokens (nomes dos testes do `llama-bench`). |
| t/s | Tokens por segundo. |
| TDP | Potência térmica de projeto; **não** é consumo medido. |
| RAPL | Contador interno de energia de CPUs mais novas; o Yonah não tem. |
| Tjunction / `crit` | Temperatura máxima de junção (100 °C para o T2300 e o i5-1035G1). |
| Throttling | Redução de frequência por temperatura ou potência. |
| SMC / applesmc | Controlador de sistema do Mac e seu driver no Linux (temperaturas, ventoinha). |
| Gate térmico | Espera por equilíbrio térmico antes de iniciar uma medição. |
| KLD | Divergência de Kullback-Leibler entre as distribuições de saída de duas execuções. |
| "Same top p" | % de tokens em que as duas execuções escolhem o mesmo token mais provável. |
| McNemar / TOST | Teste pareado de diferença / teste de equivalência (duas desigualdades unilaterais). |
| ψ (psi) | Fração de perguntas em que duas condições discordam. |
| ADR | *Architecture Decision Record*: registro curto de uma decisão e seu motivo. |
