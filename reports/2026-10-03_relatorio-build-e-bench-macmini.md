# llama.cpp em um Mac mini 1,1 (Core Duo, 32 bits, 2 GB): processo, erros e resultados

## 1. Objetivo e hardware

Executar inferência de modelos de linguagem pequenos (SLMs) com o llama.cpp em hardware legado, como base para experimentos de pesquisa.

| Item | Valor |
|---|---|
| Modelo | Mac mini 1,1 (A1176 / EMC 2108) |
| CPU | Intel Core Duo T2300 (Yonah), 1,66 GHz, 2 núcleos, sem hyperthreading |
| Extensões SIMD | até SSE3 (sem SSSE3, SSE4, AVX, FMA, F16C) |
| Arquitetura | 32 bits (sem Intel 64) |
| RAM | 2 GB DDR2-667 (teto da plataforma) |
| Disco | HDD 2,5", SATA I, 5400 rpm |
| Sistema | Debian 12 (i386), sem ambiente gráfico |

Versão do software usada:

- llama.cpp 0.5.0-dev, ggml 0.25.3
- Commit: `bed0a8566` (registrado no PC de build; o binário final mostra `build: unknown`, ver seção 4.8)
- Compilador do binário final: GCC 12.2 em contêiner `debian:bookworm` (amd64, multilib, `-m32`)

---

## 2. Resumo

- Compilar **dentro do Mac mini falhou** (erros internos do GCC).
- A solução foi **compilar em um PC 64 bits, dentro de um contêiner Debian 12**, gerando binário 32 bits compatível com a glibc 2.36 do Mac mini.
- O binário roda sem `illegal instruction` e conversa com o modelo Qwen2.5 0.5B Instruct (Q5_K_M).
- Desempenho: **~1,3 t/s na geração e ~1,6 t/s no processamento do prompt** com 2 threads.
- As respostas do modelo são rápidas de ler, mas de qualidade limitada (alucinações em fatos locais e atuais).

---

## 3. Caminho que funcionou (receita final)

### 3.1 No PC de build (64 bits, com Docker)

```bash
cd ~/llama.cpp          # clone via git, não zip
git rev-parse HEAD > commit.txt

sudo docker run --rm -v "$PWD":/src -w /src debian:bookworm bash -c '
set -e
apt-get update
apt-get install -y build-essential gcc-multilib g++-multilib cmake ninja-build git
git config --global --add safe.directory /src   # embute o commit no binário
rm -rf build32-bk
cmake -S . -B build32-bk -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_FLAGS="-m32 -O3 -msse3 -mfpmath=sse" \
  -DCMAKE_CXX_FLAGS="-m32 -O3 -msse3 -mfpmath=sse" \
  -DCMAKE_EXE_LINKER_FLAGS="-m32" \
  -DCMAKE_SHARED_LINKER_FLAGS="-m32" \
  -DGGML_NATIVE=OFF \
  -DGGML_SSSE3=OFF -DGGML_SSE42=OFF -DGGML_BMI2=OFF \
  -DGGML_AVX=OFF -DGGML_AVX2=OFF -DGGML_AVX_VNNI=OFF \
  -DGGML_FMA=OFF -DGGML_F16C=OFF \
  -DGGML_AVX512=OFF -DGGML_AMX_TILE=OFF \
  -DGGML_OPENMP=ON -DGGML_BLAS=OFF \
  -DLLAMA_OPENSSL=OFF -DLLAMA_CURL=OFF
cmake --build build32-bk --target llama-cli llama-bench llama-perplexity llama-server -j$(nproc)
'
sudo chown -R "$USER": build32-bk
```

Nota: a linha do `safe.directory` foi acrescentada depois, como correção do problema da seção 4.8. O build que gerou o binário testado **não** a tinha.

### 3.2 Verificações antes de enviar

```bash
# Arquitetura
file build32-bk/bin/llama-cli          # deve dizer: ELF 32-bit ... Intel 80386

# Versões mínimas de bibliotecas exigidas (devem caber no Debian 12)
objdump -T build32-bk/bin/*.so build32-bk/bin/llama-cli 2>/dev/null \
  | grep -o -E 'GLIBC_[0-9.]+|GLIBCXX_[0-9.]+|CXXABI_[0-9.]+' | sort -uV | tail

# Instruções acima de SSE3 (esperado: 0 em cada biblioteca)
for f in build32-bk/bin/*.so; do
  echo "$f: $(objdump -d "$f" | grep -c -E 'pshufb|pblendvb|pmaddubsw|phaddw|vfmadd|vpadd')"
done
```

Resultados obtidos neste build:

- `llama-cli`: ELF 32-bit, Intel 80386.
- Maior `GLIBC_` exigido: 2.34 (Debian 12 tem 2.36).
- Maior `GLIBCXX_`: 3.4.30; maior `CXXABI_`: 1.3.13 (o limite do GCC 12).
- As 10 bibliotecas `.so` deram contagem 0 para as instruções pesquisadas.

Limitação da checagem: o `grep` cobre só os padrões listados; o teste definitivo é executar no Mac mini.

### 3.3 Empacotar e enviar

```bash
echo "gcc 12.2 (debian:bookworm container, amd64 multilib), -m32 -O3 -msse3" > toolchain.txt
tar czf llama32-bk.tar.gz -C build32-bk bin
sha256sum llama32-bk.tar.gz > llama32-bk.sha256
scp llama32-bk.tar.gz llama32-bk.sha256 commit.txt toolchain.txt gaia@IP_DO_MAC:~/
```

### 3.4 No Mac mini

```bash
rm -rf ~/bin                       # evita misturar bibliotecas de builds antigos
sha256sum -c llama32-bk.sha256
tar xzf llama32-bk.tar.gz
sudo apt install libgomp1 libatomic1
cd bin
LD_LIBRARY_PATH=. ./llama-cli --version
```

O `LD_LIBRARY_PATH=.` é necessário porque os `libggml*.so` e `libllama*.so` ficam na mesma pasta do executável.

### 3.5 Rodar o chat

```bash
cd ~/bin
LD_LIBRARY_PATH=. ./llama-cli -m ~/qwen2.5-0.5b-instruct-q5_k_m.gguf \
  -t 2 -c 1024 -b 128 -lm none \
  -sys "Você é um assistente que responde em português, de forma curta." \
  --temp 0.3 -n 128
```

Diferenças desta versão do `llama-cli` em relação a versões antigas (descobertas por tentativa e erro):

- `-cnv` não existe: o modo conversa já é o padrão.
- `--no-mmap` não existe: a opção virou `-lm` / `--load-mode` (`auto`, `none`, `mmap`, `mlock`, `mmap+mlock`, `dio`). Usei `-lm none` como equivalente do antigo `--no-mmap`; essa equivalência é interpretação minha da descrição do help, não confirmada na documentação.
- Comandos dentro do chat: `/exit`, `/regen`, `/clear`, `/read <arquivo>`, `/glob <padrão>`.

---

## 4. O que deu errado (em ordem cronológica)

### 4.1 `-ffast-math` quebrou a compilação

- **Sintoma:** `#error "some routines in ggml.c require non-finite math arithmetics -- pass -fno-finite-math-only"`.
- **Causa:** o `-ffast-math` inclui `-ffinite-math-only`, e o ggml usa infinitos.
- **Correção:** remover `-ffast-math`. (Erro da orientação inicial.)

### 4.2 Extensões SSE4.2 e BMI2 ligadas mesmo com `GGML_NATIVE=OFF`

- **Sintoma:** o log mostrou `Adding CPU backend variant ggml-cpu: -msse4.2;-mbmi2`.
- **Causa:** com `GGML_NATIVE=OFF`, o ggml liga um conjunto padrão de extensões que o Yonah não tem. O binário daria `illegal instruction`.
- **Correção:** desligar explicitamente `GGML_SSSE3`, `GGML_SSE42`, `GGML_BMI2`, AVX*, FMA, F16C etc. Depois disso a linha `Adding CPU backend variant ggml-cpu:` ficou vazia, como esperado.

### 4.3 Erros internos do GCC (ICE) ao compilar no Mac mini

Duas tentativas, dois arquivos diferentes:

1. `Unity/unity_2_cxx.cxx` (segfault do `cc1plus` na expansão de templates).
2. `llama-kv-cache.cpp` (segfault no coletor de lixo do GCC), depois de adicionar `--param ggc-min-expand=20 --param ggc-min-heapsize=32768` e `-O2 -g0`.

- O `unity_2_cxx.cxx`, que falhou na primeira tentativa, compilou na segunda. Isso sugere falha não determinística.
- **Causa provável (não confirmada):** pouca memória/pilha do GCC de 32 bits com unidades de compilação grandes. Os parâmetros `--param ggc-*` sugeridos podem ter piorado o caso 2. Hardware (RAM ou superaquecimento) também ficou como suspeita; memtest e `dmesg` não foram executados.
- `-DCMAKE_UNITY_BUILD=OFF` não teve efeito: os arquivos `Unity/unity_*.cxx` continuaram aparecendo.
- **Decisão:** abandonar a compilação nativa e compilar em outra máquina.

### 4.4 GCC 15.2 no PC de build: `unknown pseudo-op: .base64`

- **Sintoma:** erros do assembler em vários arquivos (`ggml.c`, `ggml-quants.c`, `ggml-opt.cpp`...).
- **Causa:** o GCC 15 emite a diretiva `.base64`, que o `as` (binutils) instalado não reconhecia. Não cheguei a rodar `as --version` para confirmar a versão exata; a hipótese é binutils anterior à 2.44.
- **Correção aplicada:** usar `gcc-14`/`g++-14` (que compilou sem esse erro).

### 4.5 Erro `unrecognized command-line option '-G'`

- **Causa:** o comando foi montado a partir de uma versão abreviada (`...(mesmas flags de antes)...`) e o `-G Ninja` foi parar na linha do compilador.
- **Correção:** comando completo, com `-S . -B build32 -G Ninja` e compiladores definidos por `-DCMAKE_C_COMPILER` / `-DCMAKE_CXX_COMPILER`.

### 4.6 Binário do GCC 14 não rodou no Debian 12

- **Sintoma no Mac mini:** `GLIBC_2.38`, `GLIBC_2.43` e `GLIBCXX_3.4.32` / `CXXABI_1.3.15` não encontrados.
- **Causa:** o PC de build usa bibliotecas mais novas que as do Debian 12 (glibc 2.36, libstdc++ do GCC 12). Linkar `libstdc++` estaticamente não resolveria a glibc.
- **Correção:** compilar em um contêiner `debian:bookworm` com multilib. Isso também eliminou o problema do `.base64`, pois o GCC 12 não usa essa diretiva.

### 4.7 Opções de linha de comando inexistentes no `llama-cli`

- `--no-mmap` e `-cnv` foram rejeitados (`invalid argument`).
- Foi preciso consultar `./llama-cli --help` para achar `-lm` / `--load-mode`.
- Lição: as flags do llama.cpp mudam entre versões; sempre conferir o `--help` do binário em uso.

### 4.8 Commit desconhecido no binário

- No contêiner, o git recusou o diretório (`detected dubious ownership`), então o build mostra `ggml commit: unknown` / `build: unknown (0)`.
- Não afeta a execução. O commit real (`bed0a8566`) está registrado em `commit.txt`.
- Correção para o próximo build: `git config --global --add safe.directory /src` antes do `cmake` (já incluído na receita 3.1).

### 4.9 Primeira tentativa de build no Mac mini sem git

- O código foi baixado como zip, então não havia commit registrado. Para pesquisa, usar `git clone` e anotar o hash.

---

## 5. Avisos de compilação conhecidos (não impediram a execução)

| Aviso | Significado |
|---|---|
| `ggml_thread_apply_affinity`: cast de ponteiro para inteiro | Só afeta a mensagem de erro de afinidade de threads em 32 bits. Inofensivo. |
| `LLAMA_QUANT_MAX_BUF_SIZE` (8 GiB) vira 0 | Está no caminho de quantização (`llama-quantize`, que não foi compilado). Quantizar modelos apenas no PC 64 bits. |
| `auto_min_size` (4 GiB) vira 0 em `llama-model-loader.cpp` | Está no carregador de modelos. O efeito exato não foi investigado; o carregamento funcionou nos testes. Registrar como limitação do build 32 bits. |

---

## 6. Resultados

### 6.1 Benchmark (`llama-bench`)

Modelo: Qwen2.5 0.5B Instruct, **Q5_K_M** (492,32 MiB, 630,17 M de parâmetros contando embeddings). Modo de carregamento padrão (`auto`, ou seja, mmap).

| Threads | Teste | Tokens/s |
|---:|---|---:|
| 1 | pp64 (prompt) | 0,83 ± 0,00 |
| 1 | tg32 (geração) | 0,65 ± 0,00 |
| 2 | pp64 | 1,64 ± 0,00 |
| 2 | tg32 | 1,28 ± 0,00 |

Observações:

- O escalonamento de 1 para 2 threads é quase perfeito (≈1,97× na geração, ≈1,98× no prompt). Isso sugere gargalo de **cálculo**, não de banda de memória.
- O processamento do prompt é quase tão lento quanto a geração, o que não é típico de CPUs com SIMD moderno. Hipótese (não verificada com profiler): o ggml está usando caminhos genéricos, sem kernels vetorizados para este chip.
- Foi testado Q5_K_M, não Q4_0/Q8_0. Comparação entre quantizações **ainda não foi feita**.

### 6.2 Chat interativo (`llama-cli`, `-lm none`)

- Velocidade na sessão: prompt de 1,6 para 1,4 t/s e geração de 1,3 para 1,1 t/s ao longo de ~12 turnos. A queda é compatível com o crescimento do contexto.
- Qualidade das respostas (observação qualitativa, 12 perguntas, sem avaliação sistemática):
  - Corretas: capital do Brasil, 2+2, divisão por zero.
  - Erradas ou inventadas: localização de Camaquã, número de "clones" de uma figura pública, presidente atual do Brasil (respondeu com um nome desatualizado), definições de nomes próprios locais.
  - O modelo repetiu a mesma resposta inventada quando contestado e respondeu com a mesma confiança a acertos e erros.

---

## 7. Limitações atuais

- 2 GB de RAM; sem interface gráfica sobram ~1,5 GB para modelo, KV cache e buffers.
- CPU sem SSSE3/SSE4/AVX; velocidade de ~1 a 1,5 t/s com modelo de 0,5B.
- Compilação nativa inviável; depende de PC de build com contêiner Debian 12.
- Binário sem OpenSSL: o llama.cpp não baixa modelos sozinho (baixar no PC e enviar por `scp`).
- Quantização e eventual treino/fine-tuning devem ser feitos no PC 64 bits.
- Resultados de qualidade são impressões; falta um conjunto fixo de perguntas e métricas objetivas.

---

## 8. Registro para reprodutibilidade

| Item | Valor |
|---|---|
| Commit llama.cpp | `bed0a8566` (conferir o hash completo em `commit.txt`) |
| Contêiner de build | `debian:bookworm` (registrar o digest com `docker images --digest debian:bookworm`) |
| Compilador | GCC 12.2.0, `-m32 -O3 -msse3 -mfpmath=sse` |
| Extensões SIMD | somente até SSE3; SSSE3, SSE4.x, AVX*, FMA, F16C, BMI2 desligados |
| Modelo testado | `qwen2.5-0.5b-instruct-q5_k_m.gguf` |
| Parâmetros do bench | `-t 1,2 -p 64 -n 32 -r 3` |
| Parâmetros do chat | `-t 2 -c 1024 -b 128 -lm none --temp 0.3 -n 128` |
| Não registrados | governor de CPU, temperatura, hash SHA-256 do modelo |

Pendências de registro: anotar governor (`cpufreq`) e temperatura (`sensors`) em cada medição, e o hash do arquivo `.gguf`.

---

## 9. Próximos passos sugeridos (sem brainstorming extra)

1. Rebuild com `safe.directory` para embutir o commit no binário.
2. Repetir o `llama-bench` com `-lm none` e anotar o modo de carregamento em cada resultado.
3. Comparar quantizações do mesmo modelo (Q8_0, Q4_0, Q5_K_M) com `llama-bench`.
4. Criar um conjunto fixo de perguntas e rodar com `--temp 0 --seed 42`, medindo acertos e t/s.
5. Rodar `perf` no `llama-bench` para confirmar onde o tempo é gasto antes de qualquer otimização de código.
