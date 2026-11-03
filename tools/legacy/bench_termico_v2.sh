#!/bin/bash
# bench_termico_v2.sh - llama-bench com registro térmico (coretemp + applesmc) no Mac mini 1,1
#
# Uso (dentro da pasta bin, onde está o llama-bench):
#   AMB=24 ../bench_termico_v2.sh ~/modelo.gguf [args extras do llama-bench]
# Variáveis opcionais:
#   AMB (temp. ambiente, °C)  BASE=60  DT=1  THREADS=2
#   TARGET=52   -> só inicia o teste e só encerra quando todos os núcleos estiverem <= TARGET °C
#   MAXWAIT=900 -> limite (s) de espera para esfriar
#   MINCOOL=60  -> resfriamento mínimo (s) depois do teste
#
# Pré-requisitos: sudo apt install lm-sensors ; sudo modprobe coretemp applesmc
set -u
export LC_ALL=C     # ponto decimal e $EPOCHREALTIME consistentes

MODEL=${1:?uso: $0 modelo.gguf [args extras do llama-bench]}
shift
BASE=${BASE:-60}
DT=${DT:-1}
THREADS=${THREADS:-2}
TARGET=${TARGET:-52}
MAXWAIT=${MAXWAIT:-900}
MINCOOL=${MINCOOL:-60}
OUT=termico_$(date +%Y%m%d_%H%M%S)
mkdir -p "$OUT"
LOG="$OUT/log.csv"

# ---------- descoberta de sensores ----------
# coretemp expõe os arquivos em /sys/class/hwmon/hwmonN/. O applesmc os expõe no
# dispositivo de plataforma (/sys/devices/platform/applesmc.*), por isso o glob extra.
TEMPS=(); FANS=(); CORES=()
declare -A SEEN
for f in /sys/class/hwmon/hwmon*/temp*_input /sys/class/hwmon/hwmon*/device/temp*_input \
         /sys/devices/platform/applesmc.*/temp*_input; do
  [ -e "$f" ] || continue
  r=$(readlink -f "$f"); [ -n "${SEEN[$r]:-}" ] && continue; SEEN[$r]=1
  TEMPS+=("$f")
done
for f in /sys/class/hwmon/hwmon*/fan*_input /sys/class/hwmon/hwmon*/device/fan*_input \
         /sys/devices/platform/applesmc.*/fan*_input; do
  [ -e "$f" ] || continue
  r=$(readlink -f "$f"); [ -n "${SEEN[$r]:-}" ] && continue; SEEN[$r]=1
  FANS+=("$f")
done
if [ ${#TEMPS[@]} -eq 0 ]; then
  echo "ERRO: nenhum sensor de temperatura encontrado."
  echo "Rode: sudo modprobe coretemp applesmc   e confira com 'sensors'"
  exit 1
fi

label() {
  local d b n l
  d=$(dirname "$1"); b=$(basename "$1" _input)
  n=$(cat "$d/name" 2>/dev/null); [ -n "$n" ] || n=$(basename "$d")
  l=$(cat "$d/${b}_label" 2>/dev/null); [ -n "$l" ] || l=$b
  echo "${n}:${l}" | tr ' ' '_'
}

HDR="epoch"
for f in "${TEMPS[@]}"; do
  l=$(label "$f"); HDR+=",${l}_C"
  case "$l" in coretemp:Core*) CORES+=("$f");; esac
done
for f in "${FANS[@]}"; do HDR+=",$(label "$f")_rpm"; done
HDR+=",freq_cpu0_kHz,freq_cpu1_kHz,load1,throttle_count"
echo "$HDR" > "$LOG"

# ---------- funções (usam só builtins no laço de amostragem, para perturbar pouco a CPU) ----------
rd()       { REPLY=""; [ -r "$1" ] && read -r REPLY < "$1"; }
fmt_temp() { if [ -n "$1" ]; then TT="$(( $1 / 1000 )).$(( ($1 % 1000) / 100 ))"; else TT=""; fi; }
mark()     { echo "$1,$EPOCHREALTIME" >> "$OUT/marcadores.csv"; }

core_max() {
  local f v; CM=0
  for f in "${CORES[@]}"; do
    rd "$f"
    if [ -n "$REPLY" ]; then v=$(( REPLY / 1000 )); [ "$v" -gt "$CM" ] && CM=$v; fi
  done
}

wait_cool() {   # $1 = tempo mínimo de espera (s)
  local t0=$SECONDS el
  while :; do
    core_max; el=$(( SECONDS - t0 ))
    if [ "$el" -ge "$1" ] && [ "$CM" -le "$TARGET" ]; then echo "  ok: ${CM} °C após ${el}s"; return; fi
    if [ "$el" -ge "$MAXWAIT" ]; then echo "  AVISO: limite de espera atingido (${CM} °C > ${TARGET} °C)"; return; fi
    sleep 2
  done
}

F0=/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq
F1=/sys/devices/system/cpu/cpu1/cpufreq/scaling_cur_freq
THR_FILES=(/sys/devices/system/cpu/cpu*/thermal_throttle/core_throttle_count)
[ -e "${THR_FILES[0]}" ] || THR_FILES=()    # sem arquivo => coluna vazia (não finge zero)

logger() {
  local line f thr l1 _x TT
  while :; do
    line="$EPOCHREALTIME"
    for f in "${TEMPS[@]}"; do rd "$f"; fmt_temp "$REPLY"; line+=",$TT"; done
    for f in "${FANS[@]}";  do rd "$f"; line+=",$REPLY"; done
    rd "$F0"; line+=",$REPLY"
    rd "$F1"; line+=",$REPLY"
    read -r l1 _x < /proc/loadavg; line+=",$l1"
    thr=""
    if [ ${#THR_FILES[@]} -gt 0 ]; then
      thr=0; for f in "${THR_FILES[@]}"; do rd "$f"; thr=$(( thr + ${REPLY:-0} )); done
    fi
    line+=",$thr"
    echo "$line" >> "$LOG"
    sleep "$DT"
  done
}

# ---------- metadados ----------
{
  echo "data: $(date -Is)"
  echo "kernel: $(uname -r)"
  echo "cpu: $(grep -m1 'model name' /proc/cpuinfo)"
  echo "governor: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo n/d)"
  echo "modelo: $MODEL"
  echo "sha256_modelo: $(sha256sum "$MODEL" | cut -d' ' -f1)"
  echo "threads: $THREADS"
  echo "temperatura_ambiente_C: ${AMB:-nao_informada}"
  echo "tdp_nominal_W: 31 (especificação Intel do T2300; confirme na ficha oficial)"
  echo "target_C: $TARGET  maxwait_s: $MAXWAIT  mincool_s: $MINCOOL  base_s: $BASE"
  echo "sensores_temp: ${#TEMPS[@]}  ventoinhas: ${#FANS[@]}  throttle_disponivel: $([ ${#THR_FILES[@]} -gt 0 ] && echo sim || echo nao)"
} > "$OUT/meta.txt"
sensors > "$OUT/sensors_inicio.txt" 2>&1

# ---------- execução ----------
trap 'kill $LOGPID 2>/dev/null' EXIT
logger & LOGPID=$!

echo "Esperando núcleos <= ${TARGET} °C (máx ${MAXWAIT}s)..."
mark espera_inicio; wait_cool 0; mark espera_fim
echo "inicio_max_core_C: $CM" >> "$OUT/meta.txt"

echo "Linha de base: ${BASE}s..."
mark baseline_inicio; sleep "$BASE"

echo "Rodando llama-bench..."
mark bench_inicio
LD_LIBRARY_PATH=. ./llama-bench -m "$MODEL" -t "$THREADS" -p 64 -n 32 -r 3 -o csv "$@" \
  > "$OUT/bench.csv" 2> "$OUT/bench.err"
mark bench_fim

echo "Resfriamento (mín ${MINCOOL}s, até <= ${TARGET} °C)..."
wait_cool "$MINCOOL"
echo "fim_max_core_C: $CM" >> "$OUT/meta.txt"
mark fim

# ---------- resumo da janela do benchmark ----------
T0=$(grep '^bench_inicio' "$OUT/marcadores.csv" | cut -d, -f2)
T1=$(grep '^bench_fim'    "$OUT/marcadores.csv" | cut -d, -f2)
awk -F, -v s="$T0" -v e="$T1" '
  NR==1 {for(i=1;i<=NF;i++) h[i]=$i; n=NF; next}
  $1>=s && $1<=e {c++; for(i=2;i<=n;i++){ if($i=="") continue; sum[i]+=$i; k[i]++;
                    if(!(i in mx)||$i>mx[i]) mx[i]=$i; if(!(i in mn)||$i<mn[i]) mn[i]=$i }}
  END { if(!c){print "sem amostras na janela"; exit}
        printf "%-34s %9s %9s %9s\n","coluna","min","media","max";
        for(i=2;i<=n;i++) if(k[i]) printf "%-34s %9.1f %9.1f %9.1f\n",h[i],mn[i],sum[i]/k[i],mx[i] }
' "$LOG" | tee "$OUT/resumo_bench.txt"

echo
[ ${#THR_FILES[@]} -eq 0 ] && echo "AVISO: contador de throttling indisponível neste kernel/CPU (coluna vazia)."
echo "Arquivos em $OUT/: log.csv, marcadores.csv, bench.csv, meta.txt, sensors_inicio.txt, resumo_bench.txt"
