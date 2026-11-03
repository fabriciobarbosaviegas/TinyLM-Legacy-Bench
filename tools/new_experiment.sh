#!/bin/bash
# new_experiment.sh - cria experiments/EXP-AAAA-NNN-<slug>/ a partir de experiments/_template
# Uso: tools/new_experiment.sh <slug-em-minusculas-com-hifens> ["Título legível"]
set -eu
ROOT=$(cd "$(dirname "$0")/.." && pwd)
SLUG=${1:?uso: $0 <slug> [titulo]}
TITULO=${2:-$SLUG}
case "$SLUG" in *[!a-z0-9._-]*|'') echo "ERRO: slug só pode ter a-z, 0-9, ponto, hífen e sublinhado."; exit 1;; esac
ANO=$(date +%Y)
ULT=$(ls -1 "$ROOT/experiments" 2>/dev/null | grep -E "^EXP-$ANO-[0-9]{3}-" | sed -E "s/^EXP-$ANO-([0-9]{3})-.*/\1/" | sort -n | tail -1 || true)
N=$(printf "%03d" $(( 10#${ULT:-0} + 1 )))
ID="EXP-$ANO-$N"
DIR="$ROOT/experiments/$ID-$SLUG"
[ -e "$DIR" ] && { echo "ERRO: $DIR já existe."; exit 1; }
cp -r "$ROOT/experiments/_template" "$DIR"
HOJE=$(date +%Y-%m-%d)
for f in "$DIR"/*.md; do
  sed -i "s/{{ID}}/$ID/g; s/{{TITULO}}/$TITULO/g; s/{{DATA}}/$HOJE/g" "$f"
done
echo "Criado: $DIR"
echo "Próximos passos: preencher PREREGISTRO.md ANTES de coletar dados, e registrar a linha em experiments/README.md."
