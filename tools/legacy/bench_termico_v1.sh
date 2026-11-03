#!/bin/bash
# bench_termico.sh - roda o llama-bench registrando dados térmicos do Mac mini 1,1
#
# Uso (dentro da pasta bin, onde está o llama-bench):
#   ./bench_termico.sh ~/modelo.gguf [args extras do llama-bench]
# Variáveis opcionais: AMB=24 (temp. ambiente em °C), BASE=60, COOL=120, DT=1, THREADS=2
#
# Pré-requisitos (uma vez):
#   sudo apt install lm-sensors
#   sudo modprobe coretemp applesmc
set -u

MODEL=${1:?uso: $0 modelo.gguf [args extras do llama-bench]}
shift
BASE=${BASE:-60}      # segundos de linha de base (ocioso) antes do teste
COOL=${COOL:-120}     # segundos de resfriamento depois do teste
DT=${DT:-1}           # intervalo de amostragem (s)
THREADS=${THREADS:-2}
OUT=termico_$(date +%Y%m%d_%H%M%S)
mkdir -p "$OUT"
LOG="$OUT/log.csv"

# --- descoberta dos sensores (hwmon) ---
TEMPS=(); FANS=()
for f in /sys/class/hwmon/hwmon*/temp*_input; do [ -e "$f" ] && TEMPS+=("$f"); done
for f in /sys/class/hwmon/hwmon*/fan*_input;  do [ -e "$f" ] && FANS+=("$f"); done
if [ ${#TEMPS[@]} -eq 0 ]; then
  echo "AVISO: nenhum sensor de temperatura em /sys/class/hwmon."
  echo "Rode: sudo modprobe coretemp applesmc  (e confira com 'sensors')"
  exit 1
fi

label() {
  local d b n l
  d=$(dirname "$1"); b=$(basename "$1" _input)
  n=$(cat "$d/name" 2>/dev/null)
  l=$(cat "$d/${b}_label" 2>/dev/null || echo "$b")
  echo "${n}:${l}" | tr ' ' '_'
}

HDR="epoch"
for f in "${TEMPS[@]}"; do HDR+=",$(label "$f")_C"; done
for f in "${FANS[@]}";  do HDR+=",$(label "$f")_rpm"; done
HDR+=",freq_cpu0_kHz,freq_cpu1_kHz,load1,throttle_count"
echo "$HDR" > "$LOG"

mark() { echo "$1,$(date +%s.%N)" >> "$OUT/marcadores.csv"; }

logger() {
  local line v f0 f1 thr
  while true; do
    line=$(date +%s.%N)
    for f in "${TEMPS[@]}"; do v=$(cat "$f" 2>/dev/null); line+=",${v:+$((v/1000))}"; done
    for f in "${FANS[@]}";  do v=$(cat "$f" 2>/dev/null); line+=",$v"; done
    f0=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq 2>/dev/null)
    f1=$(cat /sys/devices/system/cpu/cpu1/cpufreq/scaling_cur_freq 2>/dev/null)
    thr=$(cat /sys/devices/system/cpu/cpu*/thermal_throttle/core_throttle_count 2>/dev/null \
          | awk '{s+=$1} END{print s+0}')
    line+=",$f0,$f1,$(cut -d' ' -f1 /proc/loadavg),$thr"
    echo "$line" >> "$LOG"
    sleep "$DT"
  done
}

# --- metadados do experimento ---
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
} > "$OUT/meta.txt"

trap 'kill $LOGPID 2>/dev/null' EXIT
logger & LOGPID=$!

echo "Linha de base: ${BASE}s com o sistema ocioso..."
mark baseline_inicio
sleep "$BASE"

echo "Rodando llama-bench..."
mark bench_inicio
LD_LIBRARY_PATH=. ./llama-bench -m "$MODEL" -t "$THREADS" -p 64 -n 32 -r 3 -o csv "$@" \
  > "$OUT/bench.csv" 2> "$OUT/bench.err"
mark bench_fim

echo "Resfriamento: ${COOL}s..."
sleep "$COOL"
mark fim

# --- resumo da janela do benchmark ---
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
echo "Arquivos em $OUT/: log.csv, marcadores.csv, bench.csv, meta.txt, resumo_bench.txt"
echo "Se throttle_count (min vs max) mudou, houve redução de frequência por temperatura."
