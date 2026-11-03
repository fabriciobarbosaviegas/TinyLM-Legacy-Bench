# Ambiente e build do llama.cpp (32 bits, SSE3)

O Mac mini 1,1 usa um Core Duo (Yonah): 32 bits e instruções só até SSE3 (sem SSSE3, SSE4, AVX, FMA, F16C). O llama.cpp precisa ser compilado **sem** essas extensões, e a compilação deve ser feita **fora do Mac mini**.

## Por que não compilar no Mac mini

Duas tentativas nativas falharam com *internal compiler error* do GCC 12 (arquivos `Unity/unity_2_cxx.cxx` e `llama-kv-cache.cpp`, falhas em pontos diferentes). A causa provável é memória ou pilha do GCC de 32 bits, mas não foi confirmada (hardware também ficou como suspeita; `memtest86+` não foi executado). Ver [ADR 0001](adr/0001-compilar-em-conteiner-debian12.md).

## Receita (contêiner Debian 12, amd64, multilib)

Use `build/build-i386-sse3.sh` (resumo do que faz):

1. Entra num contêiner `debian:bookworm` com `gcc-multilib g++-multilib cmake ninja-build git`.
2. Compila com `-m32 -O3 -msse3 -mfpmath=sse` e as extensões acima desligadas explicitamente (`GGML_NATIVE=OFF` não basta: com ele o ggml ainda liga SSE4.2 e BMI2 por padrão).
3. Alvos: `llama-cli llama-bench llama-perplexity llama-server`.

Por que Debian 12: o binário precisa de `glibc` ≤ 2.36 e `libstdc++` do GCC 12 (`GLIBCXX` ≤ 3.4.30), que é o que o Mac mini tem. Um binário feito com GCC 14 numa distribuição recente exigiu `GLIBC_2.38` e `GLIBC_2.43` e não rodou.

## Verificações obrigatórias antes de enviar

`build/check-binary.sh <pasta_bin>` confere:

- `llama-cli` é ELF 32-bit, Intel 80386;
- maior `GLIBC_` ≤ 2.36, maior `GLIBCXX_` ≤ 3.4.30, maior `CXXABI_` ≤ 1.3.13;
- zero ocorrências de instruções SSSE3 ou superiores nas bibliotecas (`pshufb`, `pblendvb`, `pmaddubsw`, `phaddw`, `vfmadd`, `vpadd`). A checagem cobre só esses padrões; o teste definitivo é executar no Mac mini.

## Implantação no Mac mini

```bash
tar czf llama32.tar.gz -C build32 bin
sha256sum llama32.tar.gz > llama32.sha256
scp llama32.tar.gz llama32.sha256 gaia@IP_DO_MAC:~/
# no Mac mini:
rm -rf ~/bin && sha256sum -c llama32.sha256 && tar xzf llama32.tar.gz
sudo apt install libgomp1 libatomic1
cd ~/bin && LD_LIBRARY_PATH=. ./llama-cli --version
```

O `LD_LIBRARY_PATH=.` é necessário porque as bibliotecas `libggml*.so` e `libllama*.so` ficam na mesma pasta do executável.

## Registro obrigatório de cada build

Anote em `experiments/<EXP>/PROTOCOLO.md`: commit do llama.cpp, imagem do contêiner (digest), versão do compilador, flags e o resultado de `check-binary.sh`. O build usado até agora tem commit `bed0a8566` (llama.cpp 0.5.0-dev, ggml 0.25.3); o contêiner foi invocado sem `safe.directory`, então o binário mostra `build: unknown`. O script `build/build-i386-sse3.sh` já corrige isso.

## Problemas conhecidos

| Sintoma | Causa | Solução |
|---|---|---|
| `#error ... non-finite math` | `-ffast-math` inclui `-ffinite-math-only` e o ggml usa infinitos | não usar `-ffast-math` |
| `Adding CPU backend variant: -msse4.2;-mbmi2` | padrão do ggml com `GGML_NATIVE=OFF` | desligar SSSE3, SSE4.2, BMI2, AVX, FMA etc. explicitamente |
| `unknown pseudo-op: .base64` | GCC 15 emitindo diretiva que o `as` instalado não reconheceu (hipótese: binutils antigo) | compilar com GCC 12 no contêiner |
| `GLIBC_2.38 not found` | binário feito em distribuição mais nova | compilar no contêiner Debian 12 |
| `invalid argument: --no-mmap` / `-cnv` no `llama-cli` | flags removidas nesta versão | usar `-lm none` (carregamento) e o modo conversa padrão; consultar `--help` |
| `-DCMAKE_UNITY_BUILD=OFF` sem efeito | o projeto tem mecanismo próprio de "unity build" | não depender dessa opção |

## Avisos de compilação conhecidos (não impediram a execução)

- `ggml_thread_apply_affinity`: cast ponteiro→inteiro em 32 bits, só na mensagem de erro de afinidade.
- `LLAMA_QUANT_MAX_BUF_SIZE` (8 GiB) e `auto_min_size` (4 GiB) viram 0 em `size_t` de 32 bits: o primeiro está no caminho de **quantização** (não quantize no Mac mini); o segundo, no carregador de modelos (efeito não investigado; o carregamento funcionou).
