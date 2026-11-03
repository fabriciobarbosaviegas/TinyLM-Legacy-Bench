# Estudo: o hardware influencia a qualidade das respostas?

Estado: **protocolo em rascunho** (nenhum dado coletado). Quando for executar, crie o experimento com `tools/new_experiment.sh` e preencha o pré-registro.

## Hipóteses

- **H0:** para o mesmo `.gguf`, mesmas entradas e decodificação determinística, a qualidade não depende do hardware.
- **H1a:** há diferença sistemática por instruções/kernels diferentes (SSE3 contra AVX2/FMA).
- **H1b:** há diferença por falha intermitente de hardware.

## Pré-condições

1. `.gguf` **idêntico** nas máquinas (sha256 igual; use `llama-gguf-hash` para comparar por tensor se divergirem). Ver `07-integridade-dos-modelos.md`: enquanto isso estiver em aberto, o estudo mediria corrupção de arquivo, não hardware.
2. `memtest86+` e SMART do disco no Mac mini.
3. Build reproduzível e ambiente registrado (`01-ambiente-e-build.md`).

## Células e contrastes

| Célula | Binário | Máquina | O que isola |
|---|---|---|---|
| A | SSE3, 32 bits | Mac mini | |
| B | o mesmo SSE3, 32 bits | i5 (chroot Debian 12 i386, mesma `glibc`) | **A contra B = hardware** (mesmas instruções) |
| C | AVX2/FMA nativo | i5 | **B contra C = instruções e kernels** |
| D | variações de threads e `-b` em A e B | | sensibilidade à configuração |

Controle **negativo**: mesma máquina e mesmo binário duas vezes (deve dar saída idêntica). Controle **positivo**: perturbação conhecida (outra quantização, ou cópia do arquivo com um byte alterado de propósito).

## Medidas

Probabilidades: `llama-perplexity --kl-divergence-base` e `--kl-divergence` (KLD, ΔPPL, "Same top p"); os arquivos de logits são enormes (11 GiB para LLaMA 2 e 37 GiB para LLaMA 3 com o Wikitext-2 completo): use `--chunks`. Texto: igualdade exata e ponto da primeira divergência. Acerto: pareado entre células. Determinismo: 30 a 300 repetições da mesma pergunta no Mac mini (frio e quente). Integridade: hash por tensor.

## Plano de análise (definir antes)

- Escala de referência: ruído de quantização (por exemplo Q8_0 contra Q5_K_M). Se A–B e B–C tiverem KLD ordens de grandeza menor, o efeito é irrelevante na prática.
- Acerto: intervalo de Wilson; McNemar exato; **equivalência (TOST)** com margem (ex.: ±3 pp: ~190 a ~480 perguntas conforme a discordância; tabela em `04-avaliacao-de-qualidade.md`); correção de Holm.
- Determinismo: com zero divergências em n repetições, limite superior de ~3/n (30 repetições ≈ 10%; 300 ≈ 1%).

| Resultado | Conclusão |
|---|---|
| A idêntico a B e B–C pequeno frente à quantização | H0 sustentada para estes modelos |
| A diferente de B, mas A estável run a run | efeito de hardware ou de ambiente; investigar |
| A instável run a run | H1b (falha intermitente) |
| B–C grande | H1a (instruções), sem culpar o equipamento |

## Ameaças à validade

Uma só unidade de cada máquina (um exemplar defeituoso confunde arquitetura com exemplar; ideal: segunda unidade); bibliotecas diferentes (usar o mesmo contêiner); não determinismo do software por threads (medir no i5); ordem e horário das execuções; generalização restrita a estes modelos, quantizações e ao backend de CPU.

## Literatura encontrada (verificar nos originais)

Leitura baseada em resumos e trechos; **não** substitui a leitura dos artigos. Nenhum estudo específico sobre CPU x86 antiga com llama.cpp foi encontrado nas buscas (ausência de evidência, não evidência de ausência).

| Trabalho | O que mostra | Limite para este projeto |
|---|---|---|
| Yuan et al., *Understanding and Mitigating Numerical Sources of Nondeterminism in LLM Inference* (arXiv 2506.09501; NeurIPS 2025, oral) | Em BF16 com decodificação gulosa, GPU, quantidade de GPUs e tamanho de lote mudam respostas; até 9% de variação de acurácia num modelo de raciocínio de 7B | GPU, BF16, respostas longas |
| Cooper et al., *Accelerating the Mitigation of LLM Inference Nondeterminism Across GPU Architectures* (arXiv 2609.25624) | Mesmo modelo/prompt/software dá saídas diferentes em GPUs diferentes; ordem de redução fixa dá resultado idêntico bit a bit | GPU NVIDIA |
| README do `llama-perplexity` (llama.cpp) | Ferramenta de KLD; exemplo CPU BF16 vs FP16 | diferença de formato, não de hardware |
| `v-code01/determinism` (GitHub, não revisado) | Repetições seriais idênticas em llama.cpp/GPU Apple; concorrência perturba logits | informal; fora de CPU |
| *Understanding Silent Data Corruption in LLM Training* (ACL); LLM-PRISM (arXiv 2604.10390) | Falhas silenciosas reais ou intermitentes (dependentes de temperatura/tensão) perturbam o treino | treinamento em GPU |
| Estudos de bit-flip (par.nsf.gov purl 10657531; BitFlipScope arXiv 2512.22174) | Bit-flips degradam acurácia; ataques direcionados derrubam modelos com poucos bits | direcionado vs aleatório |

Termos de busca sugeridos: `numerical reproducibility LLM inference CPU quantized llama.cpp`; `cross-platform reproducibility GGUF`; `floating point non-associativity LLM evaluation`; `silent data corruption LLM inference CPU`; `bit flip DRAM quantized LLM accuracy`; `ECC memory LLM inference`.

## Publicabilidade (avaliação do projeto, não métrica objetiva)

Relevância estimada 3/10 para ML em geral, 5/10 para o nicho de reprodutibilidade/inferência local, 6–7/10 se ampliar escopo (várias arquiteturas, modelos, unidades duplicadas, injeção de falhas, código e dados abertos). Formato realista hoje: *preprint* e *workshops*. Faça uma revisão sistemática antes de qualquer alegação de ineditismo.
