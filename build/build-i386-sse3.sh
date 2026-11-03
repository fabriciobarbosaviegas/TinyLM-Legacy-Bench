#!/bin/bash
# build-i386-sse3.sh - compila o llama.cpp (32 bits, até SSE3) num contêiner Debian 12 amd64 multilib.
# Uso: build/build-i386-sse3.sh <pasta_do_llama.cpp> [pasta_de_saida_relativa=build32-bk]
# Requer Docker (use sudo se necessário: DOCKER="sudo docker").
set -eu
SRC=${1:?uso: $0 <pasta_do_llama.cpp> [saida]}
OUTDIR=${2:-build32-bk}
DOCKER=${DOCKER:-docker}
IMAGE=${IMAGE:-debian:bookworm}
SRC=$(cd "$SRC" && pwd)
[ -f "$SRC/CMakeLists.txt" ] || { echo "ERRO: $SRC não parece ser o llama.cpp"; exit 1; }
echo "commit: $(git -C "$SRC" rev-parse HEAD 2>/dev/null || echo desconhecido)" | tee "$SRC/build-commit.txt"
$DOCKER image inspect "$IMAGE" >/dev/null 2>&1 || $DOCKER pull "$IMAGE"
echo "imagem: $($DOCKER image inspect "$IMAGE" --format '{{index .RepoDigests 0}}' 2>/dev/null || echo sem-digest)" | tee -a "$SRC/build-commit.txt"

$DOCKER run --rm -v "$SRC":/src -w /src -e OUTDIR="$OUTDIR" "$IMAGE" bash -c '
set -e
apt-get update
apt-get install -y build-essential gcc-multilib g++-multilib cmake ninja-build git
git config --global --add safe.directory /src   # embute o commit no binário
rm -rf "$OUTDIR"
cmake -S . -B "$OUTDIR" -G Ninja \
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
cmake --build "$OUTDIR" --target llama-cli llama-bench llama-perplexity llama-server -j"$(nproc)"
'
$DOCKER run --rm -v "$SRC":/src alpine chown -R "$(id -u):$(id -g)" "/src/$OUTDIR" 2>/dev/null || sudo chown -R "$(id -u):$(id -g)" "$SRC/$OUTDIR" || true
echo "Pronto: $SRC/$OUTDIR/bin. Rode: build/check-binary.sh $SRC/$OUTDIR/bin"
