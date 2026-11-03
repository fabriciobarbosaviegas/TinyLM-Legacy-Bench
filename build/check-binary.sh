#!/bin/bash
# check-binary.sh - verifica se os binários 32 bits servem ao Mac mini 1,1 (Debian 12, Core Duo).
# Uso: build/check-binary.sh <pasta_bin>
# Saída: PASS/FAIL por verificação; código 1 se alguma falhar.
set -u
BIN=${1:?uso: $0 <pasta_bin>}
ok=1
pass() { echo "PASS  $1"; }
fail() { echo "FAIL  $1"; ok=0; }
vmax() {  # $1 = prefixo (GLIBC_, GLIBCXX_, CXXABI_) -> maior versão encontrada
  objdump -T "$BIN"/*.so "$BIN"/llama-cli 2>/dev/null | grep -o -E "$1[0-9.]+" | sort -uV | tail -1
}
verle() {  # $1 <= $2 (versões do tipo X.Y.Z, sem prefixo)
  [ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | tail -1)" = "$2" ]
}
[ -x "$BIN/llama-cli" ] || { fail "llama-cli não encontrado em $BIN"; exit 1; }
if file "$BIN/llama-cli" | grep -q "ELF 32-bit.*Intel 80386"; then pass "llama-cli é ELF 32-bit, Intel 80386"; else fail "llama-cli não é ELF 32-bit i386"; fi
g=$(vmax GLIBC_);   if [ -n "$g" ] && verle "${g#GLIBC_}" 2.36;     then pass "maior $g (limite GLIBC_2.36)"; else fail "maior ${g:-?} excede GLIBC_2.36"; fi
x=$(vmax GLIBCXX_); if [ -n "$x" ] && verle "${x#GLIBCXX_}" 3.4.30; then pass "maior $x (limite GLIBCXX_3.4.30)"; else fail "maior ${x:-?} excede GLIBCXX_3.4.30"; fi
c=$(vmax CXXABI_);  if [ -n "$c" ] && verle "${c#CXXABI_}" 1.3.13;  then pass "maior $c (limite CXXABI_1.3.13)"; else fail "maior ${c:-?} excede CXXABI_1.3.13"; fi
for f in "$BIN"/*.so; do
  n=$(objdump -d "$f" 2>/dev/null | grep -c -E 'pshufb|pblendvb|pmaddubsw|phaddw|vfmadd|vpadd')
  if [ "$n" -eq 0 ]; then pass "$(basename "$f"): 0 instruções SSSE3+/AVX/FMA (padrões verificados)"; else fail "$(basename "$f"): $n ocorrência(s) de instruções acima de SSE3"; fi
done
echo
echo "Nota: a checagem cobre só os padrões listados; o teste definitivo é executar no Mac mini."
[ "$ok" = 1 ] && echo "BINÁRIO OK PARA ENVIO" || { echo "BINÁRIO COM PROBLEMAS: não envie"; exit 1; }
