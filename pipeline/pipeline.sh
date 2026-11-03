#!/bin/bash
# pipeline.sh - pipeline de benchmark de modelos GGUF no Mac mini 1,1 (llama.cpp 32 bits)
#
# Uso:  ./pipeline.sh models.csv
#   STAGES="verify bench eval ppl"  (padrão: "verify bench eval")
#
# Por modelo do manifesto, executa (nesta ordem):
#   verify  sha256 duas vezes (e contra o hash esperado, se informado)
#   bench   llama-bench com espera por equilíbrio térmico, linha de base e registro térmico/memória
#   eval    llama-server + conjunto fixo de perguntas (temperatura 0, seed 42) -> acertos e t/s
#   ppl     llama-perplexity num texto (opcional; exige PPL_FILE)
# No fim, roda aggregate.py (python3) para gerar resultados.csv e resumo.md.
#
# Variáveis principais (padrão):
#   BIN=$HOME/bin  RUNS=$HOME/runs  RUN_DIR=<novo>  (RUN_DIR existente retoma: modelos com DONE são pulados)
#   THREADS="2" (lista; cada valor é uma janela de benchmark)  PP=64 TG=32 REPS=3
#   BASE=60 (s de linha de base)   AMB= (temperatura ambiente, só registro)
#   CTX=1024 MAXTOK=64 PORT=8089 QUESTIONS=./questions_pt.jsonl QLIMIT= (limita nº de perguntas)
#   STRICT=1 (pula o modelo se o hash divergir do esperado ou for instável)   DROPCACHE=0
#   PPL_FILE= PPL_CTX=512 CHUNKS=2     BENCH_EXTRA= SERVER_EXTRA= PPL_EXTRA=
#   WATTS=31 TARIFA=1.00 (só para a estimativa de energia no resumo; TDP não é consumo medido)
#   Térmica: TARGET GATE_HS GATE_LABEL MAXWAIT POLL DT ABORT_C FAN_RPM (ver lib_termico.sh)
set -u
export LC_ALL=C
HERE=$(cd "$(dirname "$0")" && pwd)
MANIFEST=${1:?uso: $0 models.csv}
STAGES=${STAGES:-"verify bench eval"}
BIN=${BIN:-$HOME/bin}
RUNS=${RUNS:-$HOME/runs}
THREADS=${THREADS:-2}
PP=${PP:-64}; TG=${TG:-32}; REPS=${REPS:-3}
BASE=${BASE:-60}
CTX=${CTX:-1024}; MAXTOK=${MAXTOK:-64}; PORT=${PORT:-8089}
QUESTIONS=${QUESTIONS:-$HERE/questions_pt.jsonl}
SYSTEM_PROMPT=${SYSTEM_PROMPT:-"Responda em português, de forma curta e direta, em uma frase."}
ENDPOINT_DEFAULT=${ENDPOINT:-chat}
READY_TIMEOUT=${READY_TIMEOUT:-900}
STRICT=${STRICT:-1}
DROPCACHE=${DROPCACHE:-0}
PPL_FILE=${PPL_FILE:-}; PPL_CTX=${PPL_CTX:-512}; CHUNKS=${CHUNKS:-2}
BENCH_EXTRA=${BENCH_EXTRA:-}; SERVER_EXTRA=${SERVER_EXTRA:-}; PPL_EXTRA=${PPL_EXTRA:-}
WATTS=${WATTS:-31}; TARIFA=${TARIFA:-1.00}
ETHREADS=${ETHREADS:-${THREADS%% *}}
SUDO=${SUDO-sudo}

# shellcheck source=lib_termico.sh
source "$HERE/lib_termico.sh"

has_stage() { case " $STAGES " in *" $1 "*) return 0;; esac; return 1; }

# ---------- verificações iniciais ----------
[ -n "${EPOCHREALTIME:-}" ] || { echo "ERRO: bash >= 5 é necessário (\$EPOCHREALTIME)."; exit 1; }
[ -r "$MANIFEST" ] || { echo "ERRO: manifesto não encontrado: $MANIFEST"; exit 1; }
if has_stage bench; then [ -x "$BIN/llama-bench" ] || { echo "ERRO: $BIN/llama-bench não encontrado."; exit 1; }; fi
if has_stage eval; then
  [ -x "$BIN/llama-server" ] || { echo "ERRO: $BIN/llama-server não encontrado."; exit 1; }
  command -v python3 >/dev/null || { echo "ERRO: python3 é necessário para a etapa eval (sudo apt install python3)."; exit 1; }
  [ -r "$QUESTIONS" ] || { echo "ERRO: arquivo de perguntas não encontrado: $QUESTIONS"; exit 1; }
fi
if has_stage ppl; then
  [ -x "$BIN/llama-perplexity" ] || { echo "ERRO: $BIN/llama-perplexity não encontrado."; exit 1; }
  [ -r "$PPL_FILE" ] || { echo "ERRO: defina PPL_FILE com um arquivo de texto para a perplexidade."; exit 1; }
fi

RUN=${RUN_DIR:-$RUNS/run_$(date +%Y%m%d_%H%M%S)}
mkdir -p "$RUN"
therm_discover
[ ${#TEMPS[@]} -gt 0 ] || echo "AVISO: nenhum sensor de temperatura encontrado (sudo modprobe coretemp applesmc); a espera térmica ficará sem efeito."
[ -n "$GATE_FILE" ] || echo "AVISO: sensor '$GATE_LABEL' não encontrado; a espera usará só os núcleos."
trap therm_cleanup EXIT
trap 'therm_cleanup; exit 130' INT TERM

{
  echo "pipeline: bench_pipeline"
  echo "data: $(date -Is)"
  echo "kernel: $(uname -r)"
  echo "cpu: $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2- | sed 's/^ *//')"
  echo "governor: $(cat "$S"/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo n/d)"
  echo "temperatura_ambiente_C: ${AMB:-nao_informada}"
  echo "stages: $STAGES"
  echo "threads: $THREADS"
  echo "pp: $PP"
  echo "tg: $TG"
  echo "reps: $REPS"
  echo "base_s: $BASE"
  echo "ctx: $CTX"
  echo "maxtok: $MAXTOK"
  echo "endpoint: $ENDPOINT_DEFAULT"
  echo "questions: $QUESTIONS"
  echo "qlimit: ${QLIMIT:-todas}"
  echo "target_nucleos_C: $TARGET"
  echo "gate_sensor: $GATE_LABEL"
  echo "gate_max_C: $GATE_HS"
  echo "maxwait_s: $MAXWAIT"
  echo "abort_C: $ABORT_C"
  echo "ventoinha: $([ -n "$FAN_RPM" ] && echo "manual $FAN_RPM rpm" || echo "automatica (SMC)")"
  echo "strict: $STRICT"
  echo "dropcache: $DROPCACHE"
  echo "ppl_file: ${PPL_FILE:-nenhum}"
  echo "watts_estimativa: $WATTS"
  echo "tarifa_R\$_kWh: $TARIFA"
  echo "bin: $BIN"
  echo "manifesto: $MANIFEST"
} > "$RUN/run_meta.txt"
cp "$MANIFEST" "$RUN/models.csv"
command -v sensors >/dev/null && sensors > "$RUN/sensors_inicio.txt" 2>&1

if [ -n "$FAN_RPM" ]; then
  echo "Fixando ventoinha em ${FAN_RPM} rpm..."
  set_fan || { echo "Abortando antes dos testes."; exit 1; }
  sleep 10
fi

# ---------- etapas ----------
stage_verify() {   # define VERIFY_OK (1/0)
  local h1 h2 h3=""
  echo "  [verify] calculando sha256 (2 leituras)..."
  mark verify_inicio
  h1=$(sha256sum "$FILE" | cut -d' ' -f1)
  h2=$(sha256sum "$FILE" | cut -d' ' -f1)
  if [ "$DROPCACHE" = 1 ]; then
    sync; echo 3 | $SUDO tee /proc/sys/vm/drop_caches >/dev/null 2>&1
    h3=$(sha256sum "$FILE" | cut -d' ' -f1)
  fi
  mark verify_fim
  meta "sha256_leitura1: $h1"; meta "sha256_leitura2: $h2"; [ -n "$h3" ] && meta "sha256_apos_drop_cache: $h3"
  VERIFY_OK=1
  if [ "$h1" = "$h2" ] && { [ -z "$h3" ] || [ "$h1" = "$h3" ]; }; then meta "hash_estavel: sim"
  else meta "hash_estavel: NAO"; VERIFY_OK=0; echo "  ALERTA: sha256 instável entre leituras (suspeite de RAM/disco)."; fi
  if [ -n "$SHA" ]; then
    if [ "$h1" = "$SHA" ]; then meta "hash_confere_manifesto: sim"
    else meta "hash_confere_manifesto: NAO (esperado $SHA)"; VERIFY_OK=0; echo "  ALERTA: sha256 não confere com o manifesto."; fi
  else
    meta "hash_confere_manifesto: nao_verificado (manifesto sem sha256)"
  fi
}

stage_bench_window() {   # $1 = nº de threads
  local t=$1 rc BPID
  echo "  [bench] threads=$t: esperando equilíbrio térmico..."
  mark "bench_t${t}_espera_inicio"; wait_cool 0; mark "bench_t${t}_espera_fim"
  fmt10 "$HS10"
  meta "bench_t${t}_inicio_core_max_C: $CM"; meta "bench_t${t}_inicio_gate_C: $T10"; meta "bench_t${t}_gate_ok: $GATE_RESULT"
  if [ "$CM" -ge "$ABORT_C" ]; then echo "  ERRO: núcleo já em ${CM} °C; janela não executada."; meta "bench_t${t}_rc: nao_executado_quente"; return; fi
  mark "bench_t${t}_baseline_inicio"; sleep "$BASE"
  echo "  [bench] threads=$t: llama-bench -p $PP -n $TG -r $REPS ..."
  mark "bench_t${t}_inicio"
  # shellcheck disable=SC2086
  LD_LIBRARY_PATH="$BIN" "$BIN/llama-bench" -m "$FILE" -t "$t" -p "$PP" -n "$TG" -r "$REPS" -o csv $BENCH_EXTRA \
    > "$MDIR/bench_t$t.csv" 2> "$MDIR/bench_t$t.err" < /dev/null &
  BPID=$!; CHILD=$BPID; echo "$BPID" > "$PIDFILE"
  wait "$BPID"; rc=$?
  CHILD=""; : > "$PIDFILE"
  mark "bench_t${t}_fim"
  meta "bench_t${t}_rc: $rc"
  [ "$rc" -eq 0 ] || { echo "  AVISO: llama-bench terminou com código $rc (veja bench_t$t.err)"; STATUS="$STATUS bench_t${t}_falhou"; }
}

stage_eval() {
  local SPID rc
  echo "  [eval] iniciando llama-server (porta $PORT)..."
  mark eval_inicio
  # shellcheck disable=SC2086
  LD_LIBRARY_PATH="$BIN" "$BIN/llama-server" -m "$FILE" -t "$ETHREADS" -c "$CTX" \
    --host 127.0.0.1 --port "$PORT" $SERVER_EXTRA > "$MDIR/server.log" 2>&1 < /dev/null &
  SPID=$!; CHILD=$SPID; echo "$SPID" > "$PIDFILE"
  python3 "$HERE/eval_client.py" --url "http://127.0.0.1:$PORT" --questions "$QUESTIONS" \
    --out "$MDIR/eval" --max-tokens "$MAXTOK" --ready-timeout "$READY_TIMEOUT" --pid "$SPID" \
    --system "$SYSTEM_PROMPT" --endpoint "$ENDPOINT" ${QLIMIT:+--limit "$QLIMIT"} \
    > "$MDIR/eval.log" 2>&1 < /dev/null
  rc=$?
  kill "$SPID" 2>/dev/null; wait "$SPID" 2>/dev/null
  CHILD=""; : > "$PIDFILE"
  mark eval_fim
  meta "eval_rc: $rc"
  tail -n 3 "$MDIR/eval.log" | sed 's/^/    /'
  [ "$rc" -eq 0 ] || { echo "  AVISO: etapa eval terminou com código $rc (veja eval.log e server.log)"; STATUS="$STATUS eval_falhou"; }
}

stage_ppl() {
  local PID rc
  echo "  [ppl] llama-perplexity ($CHUNKS blocos de $PPL_CTX tokens)..."
  mark ppl_inicio
  # shellcheck disable=SC2086
  LD_LIBRARY_PATH="$BIN" "$BIN/llama-perplexity" -m "$FILE" -f "$PPL_FILE" -c "$PPL_CTX" --chunks "$CHUNKS" \
    -t "$ETHREADS" $PPL_EXTRA > "$MDIR/ppl.txt" 2>&1 < /dev/null &
  PID=$!; CHILD=$PID; echo "$PID" > "$PIDFILE"
  wait "$PID"; rc=$?
  CHILD=""; : > "$PIDFILE"
  mark ppl_fim
  meta "ppl_rc: $rc"
  [ "$rc" -eq 0 ] || { echo "  AVISO: llama-perplexity terminou com código $rc (confira as flags com --help)"; STATUS="$STATUS ppl_falhou"; }
}

# ---------- laço dos modelos ----------
process_model() {
  NAME=$1; FILE=$2; QUANT=$3; PARAMS=$4; SHA=$5; CHAT=$6
  MDIR="$RUN/$NAME"; MARK="$MDIR/marcadores.csv"; META="$MDIR/meta.txt"
  ENDPOINT=${CHAT:-$ENDPOINT_DEFAULT}; STATUS="ok"
  if [ -e "$MDIR/DONE" ]; then echo "[$NAME] já concluído (DONE); pulando."; return; fi
  mkdir -p "$MDIR"
  echo "[$NAME] ===================================="
  if [ ! -r "$FILE" ]; then
    echo "[$NAME] ERRO: arquivo não encontrado: $FILE"; echo "status=ERRO_ARQUIVO" > "$MDIR/status.txt"; return
  fi
  { echo "nome: $NAME"; echo "arquivo: $FILE"; echo "quant: $QUANT"; echo "params_B: $PARAMS"
    echo "endpoint: $ENDPOINT"; echo "tamanho_arquivo: $(stat -c '%s bytes; modificado em %y' "$FILE")"
    echo "inicio: $(date -Is)"; } >> "$META"
  therm_start "$MDIR"
  VERIFY_OK=1
  if has_stage verify; then
    stage_verify
    if [ "$VERIFY_OK" -ne 1 ] && [ "$STRICT" = 1 ]; then
      echo "[$NAME] PULADO: falha de integridade (STRICT=1)."; STATUS="SKIP_INTEGRIDADE"
    fi
  else
    meta "hash_estavel: nao_executado"
  fi
  if [ "$STATUS" = "ok" ]; then
    if has_stage bench; then for t in $THREADS; do stage_bench_window "$t"; done; fi
    if has_stage eval;  then stage_eval; fi
    if has_stage ppl;   then stage_ppl;  fi
  fi
  [ -e "$MDIR/ABORTADO.txt" ] && STATUS="$STATUS ABORTADO_TERMICO"
  therm_stop
  meta "fim: $(date -Is)"
  echo "status=$STATUS" > "$MDIR/status.txt"
  touch "$MDIR/DONE"
  echo "[$NAME] concluído (status: $STATUS)"
}

while IFS=, read -r name file quant params sha chat _rest <&3; do
  case "$name" in ''|\#*|name) continue;; esac
  process_model "$name" "$file" "$quant" "$params" "$sha" "$chat"
done 3< "$MANIFEST"

command -v sensors >/dev/null && sensors > "$RUN/sensors_fim.txt" 2>&1
echo "Resultados brutos em: $RUN"
if command -v python3 >/dev/null; then
  python3 "$HERE/aggregate.py" "$RUN" --watts "$WATTS" --tarifa "$TARIFA" || echo "AVISO: aggregate.py falhou (rode no PC: python3 aggregate.py $RUN)"
else
  echo "python3 ausente: copie $RUN para o PC e rode: python3 aggregate.py <pasta>"
fi
