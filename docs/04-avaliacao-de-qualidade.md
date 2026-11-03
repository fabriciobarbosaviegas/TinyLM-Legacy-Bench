# Avaliação de qualidade

## Conjuntos próprios

| Conjunto | Arquivo | Uso |
|---|---|---|
| Automático, 28 perguntas | `pipeline/questions_pt.jsonl` | etapa `eval` do pipeline (temperatura 0, seed 42, pontuação por regex) |
| Manual, 20 perguntas | `questions/avaliacao_manual_cli/` | leitura crítica das respostas no `llama-cli`, com rubrica e planilha |

Seis perguntas coincidem entre os dois (capital do Brasil, maior oceano, Dom Casmurro, Egito, Camaquã, "casa" ao contrário), o que permite comparar avaliação manual e automática.

### Rubrica do conjunto manual

Nota por pergunta: 2 = correta e direta; 1 = parcial; 0 = errada ou ausente (critério específico por pergunta no arquivo). Marcadores sim/não: **A** alucinação, **I** idioma, **F** formato, **R** repetição, **E** excesso. Máximo de 40 pontos.

### Cuidados

- A pontuação automática é por expressão regular na resposta normalizada (minúsculas, sem acentos): pode aceitar a palavra certa em contexto errado e recusar grafias válidas. Amostre `eval/eval.csv` à mão.
- Respostas corretas por memorização contam como corretas; o conjunto não distingue entendimento de memorização.

## Quantas perguntas

Resultados de uma conta normal (95% de confiança; poder de 80% quando aplicável).

**Um modelo:** margem de erro de ±20 pp exige 25 perguntas; ±10 pp, ~97; ±7 pp, ~196; ±5 pp, ~385; ±3 pp, ~1 068.

**Comparar dois modelos nas mesmas perguntas (pareado, com 30% de discordância):** detectar 20 pp pede ~57; 15 pp, ~103; 10 pp, ~233; 5 pp, ~939. A fração de discordância só é conhecida depois de um piloto.

**Equivalência pareada (margem ±δ, ψ = fração de perguntas em que as duas condições discordam):**

| Margem | ψ = 2% | ψ = 5% | ψ = 10% |
|---|---:|---:|---:|
| ±5 pp | 69 | 172 | 343 |
| ±3 pp | 191 | 476 | 952 |
| ±2 pp | 429 | 1 071 | 2 142 |
| ±1 pp | 1 713 | 4 283 | 8 565 |

Com 6 comparações entre modelos e correção de Bonferroni, as ~233 perguntas para 10 pp sobem para ~360.

Consequência prática: **20 a 28 perguntas servem para exploração** (diferenças grandes, tipos de falha). Para ranquear modelos parecidos, use 100 a 250 ou mais, rodadas no notebook i5 (o Mac mini leva 40 a 80 s por pergunta). Taxa de acerto de um `.gguf` não deveria depender da máquina, mas isso é exatamente a hipótese do estudo em `05-estudo-hardware-vs-qualidade.md`: confirme num subconjunto antes de assumir.

Velocidade e térmica precisam de poucas repetições (o desvio entre repetições internas do `llama-bench` foi ~0,3%); o desvio entre execuções separadas do pipeline ainda não foi medido.

## Benchmarks públicos (a avaliar)

Fontes consultadas nas buscas do projeto; **verifique disponibilidade, formato e licença antes de adotar**.

- `llama-perplexity` já traz modos para HellaSwag, Winogrande e tarefas de múltipla escolha (ARC, MMLU, TruthfulQA), com conjuntos de validação publicados no Hugging Face (`ikawrakow/validation-datasets-for-llama.cpp`). Confira as flags no `--help` da versão em uso.
- lm-evaluation-harness (EleutherAI): mais de 60 benchmarks, pensado para modelos PyTorch/Hugging Face; a praticidade com GGUF em 32 bits não foi avaliada.
- Português do Brasil: Open PT LLM Leaderboard (ENEM, BLUEX, OAB, ASSIN2 RTE/STS, FaQuAD NLI, HateBR, PT Hate Speech, tweetSentBR). Os resultados vistos eram de modelos ≥ 7B; para modelos de 0,5B as provas difíceis podem ficar perto do acaso (inferência, não testada).
- tinyBenchmarks: 100 exemplos curados estimam a nota completa com ~2% de erro médio (em inglês; não dá intervalo de confiança para comparar dois modelos).
- Perplexidade (já no pipeline) serve bem para comparar quantizações do mesmo modelo, mas não mede acerto de respostas.

Limitações gerais: contaminação de dados de treino; nota de múltipla escolha por probabilidade ≠ qualidade da resposta gerada em chat.
