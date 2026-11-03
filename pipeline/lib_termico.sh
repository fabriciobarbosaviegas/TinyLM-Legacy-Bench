#!/bin/bash
# lib_termico.sh - funções térmicas do pipeline (coretemp + applesmc). Uso: source lib_termico.sh
# Requer bash >= 5 ($EPOCHREALTIME). Não executar diretamente.
#
# Variáveis (valor padrão):
#   TARGET=52      núcleos devem estar <= TARGET °C para iniciar uma janela de medição
#   GATE_HS=47.0   sensor GATE_LABEL (padrão applesmc:TC0H) deve estar <= GATE_HS °C
#   MAXWAIT=1200   limite (s) de cada espera por resfriamento
#   POLL=2  DT=1   intervalo de checagem da espera / de amostragem do log (s)
#   ABORT_C=95     se algum núcleo chegar a esse valor, encerra llama-bench/server/perplexity
#   FAN_RPM=       vazio = ventoinha automática (SMC). Com valor: fixa a rotação (sudo; restaura ao sair)
#   SUDO=sudo      vazio para testes sem sudo      SYSROOT= prefixo de /sys (apenas testes)

S=${SYSROOT:-}
TARGET=${TARGET:-52}
GATE_HS=${GATE_HS:-47.0}
GATE_LABEL=${GATE_LABEL:-applesmc:TC0H}
MAXWAIT=${MAXWAIT:-1200}
POLL=${POLL:-2}
DT=${DT:-1}
ABORT_C=${ABORT_C:-95}
FAN_RPM=${FAN_RPM:-}
SUDO=${SUDO-sudo}

hs_tenths() { local v=$1; case "$v" in *.*) v=${v/./};; *) v="${v}0";; esac; echo $(( 10#$v )); }
GATE10=$(hs_tenths "$GATE_HS")

# ---------- primitivas (somente builtins, para perturbar pouco a CPU medida) ----------
rd()       { REPLY=""; [ -r "$1" ] && read -r REPLY < "$1"; }
fmt_temp() { if [ -n "$1" ]; then TT="$(( $1 / 1000 )).$(( ($1 % 1000) / 100 ))"; else TT=""; fi; }
fmt10()    { if [ -n "$1" ]; then T10="$(( $1 / 10 )).$(( $1 % 10 ))"; else T10="n/d"; fi; }
mark()     { echo "$1,$EPOCHREALTIME" >> "$MARK"; }
meta()     { echo "$1" >> "$META"; }

# ---------- descoberta de sensores ----------
TEMPS=(); FANS=(); CORES=(); GATE_FILE=""; THERM_HDR="epoch"
label() {
  local d b n l
  d=$(dirname "$1"); b=$(basename "$1" _input)
  n=$(cat "$d/name" 2>/dev/null); [ -n "$n" ] || n=$(basename "$d")
  l=$(cat "$d/${b}_label" 2>/dev/null); [ -n "$l" ] || l=$b
  echo "${n}:${l}" | tr ' ' '_'
}
therm_discover() {
  local f r l; declare -gA SEEN=()
  for f in "$S"/sys/class/hwmon/hwmon*/temp*_input "$S"/sys/class/hwmon/hwmon*/device/temp*_input \
           "$S"/sys/devices/platform/applesmc.*/temp*_input; do
    [ -e "$f" ] || continue
    r=$(readlink -f "$f"); [ -n "${SEEN[$r]:-}" ] && continue; SEEN[$r]=1; TEMPS+=("$f")
  done
  for f in "$S"/sys/class/hwmon/hwmon*/fan*_input "$S"/sys/class/hwmon/hwmon*/device/fan*_input \
           "$S"/sys/devices/platform/applesmc.*/fan*_input; do
    [ -e "$f" ] || continue
    r=$(readlink -f "$f"); [ -n "${SEEN[$r]:-}" ] && continue; SEEN[$r]=1; FANS+=("$f")
  done
  for f in "${TEMPS[@]}"; do
    l=$(label "$f"); THERM_HDR+=",${l}_C"
    case "$l" in coretemp:Core*) CORES+=("$f");; esac
    [ "$l" = "$GATE_LABEL" ] && GATE_FILE="$f"
  done
  for f in "${FANS[@]}"; do THERM_HDR+=",$(label "$f")_rpm"; done
  THERM_HDR+=",freq_cpu0_kHz,freq_cpu1_kHz,load1,throttle_count,mem_avail_kB,swap_used_kB,proc_rss_kB,proc_hwm_kB"
  F0="$S"/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq
  F1="$S"/sys/devices/system/cpu/cpu1/cpufreq/scaling_cur_freq
  THR_FILES=("$S"/sys/devices/system/cpu/cpu*/thermal_throttle/core_throttle_count)
  [ -e "${THR_FILES[0]}" ] || THR_FILES=()
  FANDIR=$(ls -d "$S"/sys/devices/platform/applesmc.* 2>/dev/null | head -1)
}

# ---------- espera por equilíbrio térmico ----------
core_max() {
  local f v; CM=0
  for f in "${CORES[@]}"; do
    rd "$f"
    if [ -n "$REPLY" ]; then v=$(( REPLY / 1000 )); [ "$v" -gt "$CM" ] && CM=$v; fi
  done
}
gate_ok() {    # define CM e HS10 (décimos de °C); retorna 0 se núcleos e sensor-gate estão frios
  core_max
  HS10=""
  if [ -n "$GATE_FILE" ]; then rd "$GATE_FILE"; [ -n "$REPLY" ] && HS10=$(( REPLY / 100 )); fi
  [ "$CM" -le "$TARGET" ] || return 1
  if [ -n "$HS10" ]; then [ "$HS10" -le "$GATE10" ] || return 1; fi
  return 0
}
wait_cool() {  # $1 = tempo mínimo de espera (s); define GATE_RESULT (sim/nao)
  local t0=$SECONDS el lastp=$SECONDS
  GATE_RESULT=sim
  while :; do
    el=$(( SECONDS - t0 ))
    if gate_ok && [ "$el" -ge "$1" ]; then
      fmt10 "$HS10"; echo "    ok: núcleos ${CM} °C, ${GATE_LABEL##*:} ${T10} °C após ${el}s"; return
    fi
    if [ "$el" -ge "$MAXWAIT" ]; then
      fmt10 "$HS10"; GATE_RESULT=nao
      echo "    AVISO: limite de espera atingido (núcleos ${CM} °C, ${GATE_LABEL##*:} ${T10} °C)"; return
    fi
    if [ $(( SECONDS - lastp )) -ge 30 ]; then
      lastp=$SECONDS; fmt10 "$HS10"; echo "    ... ${el}s: núcleos ${CM} °C, ${GATE_LABEL##*:} ${T10} °C"
    fi
    sleep "$POLL"
  done
}

# ---------- logger ----------
read_mem() {   # define MEMAV e SWAPU (kB)
  local k v _u st=0 sf=0; MEMAV=""
  while read -r k v _u; do
    case "$k" in MemAvailable:) MEMAV=$v;; SwapTotal:) st=$v;; SwapFree:) sf=$v;; esac
  done < /proc/meminfo
  SWAPU=$(( st - sf ))
}
read_proc() {  # lê PID de $PIDFILE e define PRSS/PHWM (kB) do processo medido, se existir
  local p="" k v _u; PRSS=""; PHWM=""
  [ -r "$PIDFILE" ] && read -r p < "$PIDFILE"
  if [ -n "$p" ] && [ -r "/proc/$p/status" ]; then
    while read -r k v _u; do
      case "$k" in VmRSS:) PRSS=$v;; VmHWM:) PHWM=$v;; esac
    done < "/proc/$p/status"
  fi
}
therm_logger() {
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
    read_mem; read_proc
    line+=",$MEMAV,$SWAPU,$PRSS,$PHWM"
    echo "$line" >> "$MLOG"
    sleep "$DT"
  done
}

# ---------- ventoinha (opcional) ----------
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
}

# ---------- vigia térmico ----------
therm_watchdog() {
  while :; do
    core_max
    if [ "$CM" -ge "$ABORT_C" ]; then
      if [ ! -e "$WD_DIR/ABORTADO.txt" ]; then
        echo "ABORTADO: núcleo a ${CM} °C (limite ${ABORT_C} °C)" | tee -a "$WD_DIR/ABORTADO.txt"
        echo "abortado_termico,$EPOCHREALTIME" >> "$WD_DIR/marcadores.csv"
      fi
      pkill -x llama-bench 2>/dev/null; pkill -x llama-server 2>/dev/null; pkill -x llama-perplexity 2>/dev/null
      fan_restore
    fi
    sleep 2
  done
}

# ---------- início/fim por modelo ----------
therm_start() {  # $1 = diretório do modelo
  MLOG="$1/log.csv"; PIDFILE="$1/proc.pid"; WD_DIR="$1"
  [ -s "$MLOG" ] || echo "$THERM_HDR" > "$MLOG"
  : > "$PIDFILE"
  therm_logger & LOGPID=$!
  therm_watchdog & WDPID=$!
}
therm_stop() {
  [ -n "${LOGPID:-}" ] && kill "$LOGPID" 2>/dev/null
  [ -n "${WDPID:-}" ]  && kill "$WDPID"  2>/dev/null
  LOGPID=""; WDPID=""
}
therm_cleanup() {
  therm_stop
  [ -n "${CHILD:-}" ] && kill "$CHILD" 2>/dev/null
  fan_restore
}
