# Build do llama.cpp para o Mac mini (32 bits, SSE3)

| Arquivo | Função |
|---|---|
| `build-i386-sse3.sh` | Compila num contêiner `debian:bookworm` (amd64 multilib) e gera `bin/` 32 bits. |
| `check-binary.sh` | Verifica arquitetura, versões mínimas de bibliotecas e instruções proibidas. |

Uso:

```bash
git clone https://github.com/ggml-org/llama.cpp ~/llama.cpp && cd ~/llama.cpp && git checkout <commit>
build/build-i386-sse3.sh ~/llama.cpp          # a partir da raiz deste repositório
build/check-binary.sh ~/llama.cpp/build32-bk/bin
```

Detalhes e problemas conhecidos: [`docs/01-ambiente-e-build.md`](../docs/01-ambiente-e-build.md). Requer Docker. **Registre** commit do llama.cpp, digest da imagem e a saída do `check-binary.sh` em cada experimento.
