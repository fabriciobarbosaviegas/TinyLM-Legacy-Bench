#!/bin/bash
# bench_termico_v3.sh - llama-bench com registro térmico (coretemp + applesmc) no Mac mini 1,1
#
# Uso (dentro da pasta bin, onde está o llama-bench):
#   AMB=24 ../bench_termico_v3.sh ~/modelo.gguf [args extras do llama-bench]
#
# Variáveis opcionais (valor padrão entre parênteses):
#   AMB          temperatura ambiente em °C, só para registro
#   THREADS=2    BASE=60 (s de linha de base)   DT=1 (s entre amostras)
#   TARGET=52    núcleos devem estar <= TARGET °C para iniciar/encerrar
#   GATE_HS=47.0 dissipador deve estar <= GATE_HS °C (sensor GATE_LABEL=applesmc:TC0H)
#                Observado em repouso: TC0H ~45,5-46,0 °C. Use o MESMO valor em todas as rodadas.
#   MAXWAIT=1200 limite (s) de cada espera para esfriar     MINCOOL=60 (s mínimos após o teste)
#   ABORT_C=95   se algum núcleo chegar a esse valor, o llama-bench é encerrado (crit do chip: 100 °C)
#   FAN_RPM=     vazio = controle automático do SMC. Com valor, fixa a ventoinha nessa rotação
#                (exige sudo; restaura o modo automático ao sair). NÃO verificado no Mac mini 1,1.
#   SKIPHASH=1   pula a verificação do sha256 do modelo (feita DEPOIS do teste)
#   DROPCACHE=1  inclui um 3º hash depois de limpar o cache de páginas (exige sudo)
#
# Pré-requisitos: sudo apt install lm-sensors ; sudo modprobe coretemp applesmc
set -u
export LC_ALL=C     # ponto decimal e $EPOCHREALTIME consistentes (bash >= 5)

MODEL=${1:?uso: $0 modelo.gguf [args extras do llama-bench]}
shift
BASE=${BASE:-60}
DT=${DT:-1}
THREADS=${THREADS:-2}
TARGET=${TARGET:-52}
GATE_HS=${GATE_HS:-47.0}
GATE_LABEL=${GATE_LABEL:-applesmc:TC0H}
MAXWAIT=${MAXWAIT:-1200}
MINCOOL=${MINCOOL:-60}
POLL=${POLL:-2}
ABORT_C=${ABORT_C:-95}
FAN_RPM=${FAN_RPM:-}
SKIPHASH=${SKIPHASH:-0}
DROPCACHE=${DROPCACHE:-0}
SUDO=${SUDO-sudo}          # vazio para testes sem sudo
S=${SYSROOT:-}             # prefixo de /sys (apenas para testes)
OUT=termico_$(date +%Y%m%d_%H%M%S)
mkdir -p "$OUT"
LOG="$OUT/log.csv"

hs_tenths() { local v=$1; case "$v" in *.*) v=${v/./};; *) v="${v}0";; esac; echo $(( 10#$v )); }
GATE10=$(hs_tenths "$GATE_HS")

# ---------- descoberta de sensores ----------
# coretemp expõe os arquivos em /sys/class/hwmon/hwmonN/. O applesmc os expõe no
# dispositivo de plataforma (/sys/devices/platform/applesmc.*).
TEMPS=(); FANS=(); CORES=(); GATE_FILE=""
declare -A SEEN
for f in "$S"/sys/class/hwmon/hwmon*/temp*_input "$S"/sys/class/hwmon/hwmon*/device/temp*_input \
         "$S"/sys/devices/platform/applesmc.*/temp*_input; do
  [ -e "$f" ] || continue
  r=$(readlink -f "$f"); [ -n "${SEEN[$r]:-}" ] && continue; SEEN[$r]=1
  TEMPS+=("$f")
done
for f in "$S"/sys/class/hwmon/hwmon*/fan*_input "$S"/sys/class/hwmon/hwmon*/device/fan*_input \
         "$S"/sys/devices/platform/applesmc.*/fan*_input; do
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
  [ "$l" = "$GATE_LABEL" ] && GATE_FILE="$f"
done
for f in "${FANS[@]}"; do HDR+=",$(label "$f")_rpm"; done
HDR+=",freq_cpu0_kHz,freq_cpu1_kHz,load1,throttle_count"
echo "$HDR" > "$LOG"
[ -n "$GATE_FILE" ] || echo "AVISO: sensor '$GATE_LABEL' não encontrado; a espera usará só os núcleos."

# ---------- funções (builtins no laço de amostragem, para perturbar pouco a CPU) ----------
rd()       { REPLY=""; [ -r "$1" ] && read -r REPLY < "$1"; }
fmt_temp() { if [ -n "$1" ]; then TT="$(( $1 / 1000 )).$(( ($1 % 1000) / 100 ))"; else TT=""; fi; }
fmt10()    { if [ -n "$1" ]; then T10="$(( $1 / 10 )).$(( $1 % 10 ))"; else T10="n/d"; fi; }
mark()     { echo "$1,$EPOCHREALTIME" >> "$OUT/marcadores.csv"; }
meta()     { echo "$1" >> "$OUT/meta.txt"; }

core_max() {
  local f v; CM=0
  for f in "${CORES[@]}"; do
    rd "$f"
    if [ -n "$REPLY" ]; then v=$(( REPLY / 1000 )); [ "$v" -gt "$CM" ] && CM=$v; fi
  done
}

gate_ok() {    # define CM e HS10 (décimos de °C); retorna 0 se núcleos e dissipador estão frios
  core_max
  HS10=""
  if [ -n "$GATE_FILE" ]; then rd "$GATE_FILE"; [ -n "$REPLY" ] && HS10=$(( REPLY / 100 )); fi
  [ "$CM" -le "$TARGET" ] || return 1
  if [ -n "$HS10" ]; then [ "$HS10" -le "$GATE10" ] || return 1; fi
  return 0
}

wait_cool() {  # $1 = tempo mínimo de espera (s); define GATE_RESULT
  local t0=$SECONDS el lastp=$SECONDS
  GATE_RESULT=sim
  while :; do
    el=$(( SECONDS - t0 ))
    if gate_ok && [ "$el" -ge "$1" ]; then
      fmt10 "$HS10"; echo "  ok: núcleos ${CM} °C, dissipador ${T10} °C após ${el}s"; return
    fi
    if [ "$el" -ge "$MAXWAIT" ]; then
      fmt10 "$HS10"; GATE_RESULT=nao
      echo "  AVISO: limite de espera atingido (núcleos ${CM} °C, dissipador ${T10} °C)"; return
    fi
    if [ $(( SECONDS - lastp )) -ge 30 ]; then
      lastp=$SECONDS; fmt10 "$HS10"; echo "  ... ${el}s: núcleos ${CM} °C, dissipador ${T10} °C"
    fi
    sleep "$POLL"
  done
}

F0="$S"/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq
F1="$S"/sys/devices/system/cpu/cpu1/cpufreq/scaling_cur_freq
THR_FILES=("$S"/sys/devices/system/cpu/cpu*/thermal_throttle/core_throttle_count)
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

# ---------- ventoinha (opcional) ----------
FANDIR=$(ls -d "$S"/sys/devices/platform/applesmc.* 2>/dev/null | head -1)
FAN_MANUAL_SET=0
fan_restore() {
  if [ "$FAN_MANUAL_SET" = 1 ]; then
    echo 0 | $SUDO tee "$FANDIR/fan1_manual" >/dev/null 2>&1
    FAN_MANUAL_SET=0
  fi
}
set_fan() {
  local fmin fmax
  [ -n "$FANDIR" ] && [ -e "$FANDIR/fan1_manual" ] && [ -e "$FANDIR/fan1_output" ] \
    || { echo "ERRO: controle manual da ventoinha indisponível (fan1_manual/fan1_output)."; return 1; }
  rd "$FANDIR/fan1_min"; fmin=$REPLY; rd "$FANDIR/fan1_max"; fmax=$REPLY
  case "$FAN_RPM" in ''|*[!0-9]*) echo "ERRO: FAN_RPM deve ser um inteiro."; return 1;; esac
  if [ -n "$fmin" ] && [ "$FAN_RPM" -lt "$fmin" ]; then echo "ERRO: FAN_RPM abaixo do mínimo ($fmin)."; return 1; fi
  if [ -n "$fmax" ] && [ "$FAN_RPM" -gt "$fmax" ]; then echo "ERRO: FAN_RPM acima do máximo ($fmax)."; return 1; fi
  echo 1 | $SUDO tee "$FANDIR/fan1_manual" >/dev/null || return 1
  FAN_MANUAL_SET=1
  echo "$FAN_RPM" | $SUDO tee "$FANDIR/fan1_output" >/dev/null || { fan_restore; return 1; }
  return 0
}

# ---------- vigia térmico: encerra o benchmark se algum núcleo chegar a ABORT_C ----------
watchdog() {
  while :; do
    core_max
    if [ "$CM" -ge "$ABORT_C" ]; then
      if [ ! -e "$OUT/ABORTADO.txt" ]; then
        echo "ABORTADO: núcleo a ${CM} °C (limite ${ABORT_C} °C)" | tee -a "$OUT/ABORTADO.txt"
        mark abortado_termico
      fi
      pkill -x llama-bench 2>/dev/null
      fan_restore
    fi
    sleep 2
  done
}

cleanup() {
  [ -n "${LOGPID:-}" ] && kill "$LOGPID" 2>/dev/null
  [ -n "${WDPID:-}" ]  && kill "$WDPID"  2>/dev/null
  fan_restore
}
trap cleanup EXIT
trap 'cleanup; exit 130' INT TERM

# ---------- metadados (o hash é calculado DEPOIS do teste, para não aquecer o sistema antes) ----------
{
  echo "script: bench_termico_v3.sh"
  echo "data: $(date -Is)"
  echo "kernel: $(uname -r)"
  echo "cpu: $(grep -m1 'model name' /proc/cpuinfo)"
  echo "governor: $(cat "$S"/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo n/d)"
  echo "modelo: $MODEL"
  echo "modelo_stat: $(stat -c '%s bytes; modificado em %y' "$MODEL")"
  echo "threads: $THREADS"
  echo "temperatura_ambiente_C: ${AMB:-nao_informada}"
  echo "tdp_nominal_W: 31 (especificação Intel do T2300; confirme na ficha oficial)"
  echo "target_nucleos_C: $TARGET  gate: $GATE_LABEL <= $GATE_HS C  maxwait_s: $MAXWAIT  mincool_s: $MINCOOL  base_s: $BASE"
  echo "abort_C: $ABORT_C  ventoinha: $([ -n "$FAN_RPM" ] && echo "manual $FAN_RPM rpm" || echo "automatica (SMC)")"
  echo "sensores_temp: ${#TEMPS[@]}  ventoinhas: ${#FANS[@]}  gate_sensor: $([ -n "$GATE_FILE" ] && echo sim || echo nao)  throttle_disponivel: $([ ${#THR_FILES[@]} -gt 0 ] && echo sim || echo nao)"
} > "$OUT/meta.txt"
command -v sensors >/dev/null && sensors > "$OUT/sensors_inicio.txt" 2>&1

# ---------- execução ----------
logger & LOGPID=$!

if [ -n "$FAN_RPM" ]; then
  echo "Fixando ventoinha em ${FAN_RPM} rpm..."
  set_fan || { echo "Abortando antes do teste."; exit 1; }
  sleep 10
fi
echo "Esperando núcleos <= ${TARGET} °C e dissipador <= ${GATE_HS} °C (máx ${MAXWAIT}s)..."
mark espera_inicio; wait_cool 0; mark espera_fim
fmt10 "$HS10"
meta "inicio_core_max_C: $CM"; meta "inicio_dissipador_C: $T10"; meta "gate_inicio_ok: $GATE_RESULT"
if [ "$CM" -ge "$ABORT_C" ]; then
  echo "ERRO: núcleo já em ${CM} °C (>= ${ABORT_C}) antes de iniciar. Teste não executado."; exit 1
fi
watchdog & WDPID=$!

echo "Linha de base: ${BASE}s..."
mark baseline_inicio; sleep "$BASE"

echo "Rodando llama-bench..."
mark bench_inicio
LD_LIBRARY_PATH=. ./llama-bench -m "$MODEL" -t "$THREADS" -p 64 -n 32 -r 3 -o csv "$@" \
  > "$OUT/bench.csv" 2> "$OUT/bench.err"
mark bench_fim

echo "Resfriamento (mín ${MINCOOL}s, até núcleos <= ${TARGET} °C e dissipador <= ${GATE_HS} °C)..."
wait_cool "$MINCOOL"
fmt10 "$HS10"
meta "fim_core_max_C: $CM"; meta "fim_dissipador_C: $T10"; meta "gate_fim_ok: $GATE_RESULT"
mark fim
[ -e "$OUT/ABORTADO.txt" ] && meta "ABORTADO_TERMICO: sim (veja ABORTADO.txt)"

kill "$LOGPID" "$WDPID" 2>/dev/null
command -v sensors >/dev/null && sensors > "$OUT/sensors_fim.txt" 2>&1
fan_restore

# ---------- integridade do modelo (depois do teste) ----------
if [ "$SKIPHASH" != 1 ]; then
  echo "Verificando sha256 do modelo (2 leituras)..."
  H1=$(sha256sum "$MODEL" | cut -d' ' -f1)
  H2=$(sha256sum "$MODEL" | cut -d' ' -f1)
  H3=""
  if [ "$DROPCACHE" = 1 ]; then
    sync; echo 3 | $SUDO tee /proc/sys/vm/drop_caches >/dev/null 2>&1
    H3=$(sha256sum "$MODEL" | cut -d' ' -f1)
  fi
  meta "sha256_leitura1: $H1"; meta "sha256_leitura2: $H2"; [ -n "$H3" ] && meta "sha256_apos_drop_cache: $H3"
  if [ "$H1" = "$H2" ] && { [ -z "$H3" ] || [ "$H1" = "$H3" ]; }; then
    meta "hash_estavel: sim"
  else
    meta "hash_estavel: NAO"
    echo "ALERTA: o sha256 do modelo NÃO é estável entre leituras. Suspeite de RAM/disco (memtest86+, smartctl)."
  fi
fi

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
[ -e "$OUT/ABORTADO.txt" ] && echo "ATENÇÃO: o teste foi abortado por temperatura; os resultados são parciais."
echo "Arquivos em $OUT/: log.csv, marcadores.csv, bench.csv, meta.txt, sensors_*.txt, resumo_bench.txt"
