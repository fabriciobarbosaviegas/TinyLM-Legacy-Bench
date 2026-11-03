# ADR 0001: compilar o llama.cpp em contêiner Debian 12 (amd64, multilib) com `-m32`

- **Data:** 2026-10-03
- **Status:** aceita

## Contexto

A compilação nativa no Mac mini falhou duas vezes com *internal compiler error* do GCC 12. O PC de build tinha GCC 15 (erro `.base64` do assembler) e, com GCC 14, o binário exigiu `GLIBC_2.38`/`2.43` e `GLIBCXX_3.4.32`, incompatíveis com o Debian 12 do Mac mini (glibc 2.36, libstdc++ do GCC 12).

## Decisão

Compilar num contêiner `debian:bookworm` amd64 com `gcc-multilib g++-multilib`, gerando binário 32 bits (`-m32`) contra as bibliotecas do Debian 12, com verificação automática (`build/check-binary.sh`).

## Consequências


- Binário compatível com o Mac mini; compilador de 64 bits evita o limite de memória do GCC 32 bits.
- O contêiner é o **ambiente de build de referência**: registrar digest da imagem e commit em cada experimento.
- Dependência de Docker no PC de build.

## Alternativas consideradas

Compilação nativa (falhou); GCC 14/15 no PC (incompatibilidade de bibliotecas/assembler); `-static-libstdc++` (não resolve a glibc); chroot i386 (também viável, não testado).
