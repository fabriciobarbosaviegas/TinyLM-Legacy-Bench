#!/bin/bash
# selftest.sh - valida a lógica do pipeline com llama-bench/llama-server/llama-perplexity e sensores SIMULADOS.
# Não mede nada real e não substitui um teste no Mac mini. Requer bash >= 5 e python3. Leva ~1 minuto.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
T=${T:-/tmp/bp_selftest}
rm -rf "$T"; mkdir -p "$T/bin" "$T/models"
S=$T/fake
H=$S/sys/class/hwmon/hwmon1; A=$S/sys/devices/platform/applesmc.768; C=$S/sys/devices/system/cpu
mkdir -p "$H" "$A" "$C"/cpu{0,1}/cpufreq "$C"/cpu{0,1}/thermal_throttle
echo coretemp > "$H/name"; echo "Core 0" > "$H/temp1_label"; echo 48000 > "$H/temp1_input"
echo "Core 1" > "$H/temp2_label"; echo 49000 > "$H/temp2_input"
echo applesmc > "$A/name"; echo TC0H > "$A/temp1_label"; echo 46000 > "$A/temp1_input"
echo Master > "$A/fan1_label"; echo 1500 > "$A/fan1_input"; echo 1500 > "$A/fan1_min"; echo 5500 > "$A/fan1_max"
echo 0 > "$A/fan1_manual"; echo 0 > "$A/fan1_output"
for c in 0 1; do echo 1666540 > "$C/cpu$c/cpufreq/scaling_cur_freq"; echo 0 > "$C/cpu$c/thermal_throttle/core_throttle_count"; done
echo performance > "$C/cpu0/cpufreq/scaling_governor"

cat > "$T/bin/llama-bench" <<'EOF'
#!/bin/bash
while [ $# -gt 0 ]; do case "$1" in -m) M=$2; shift;; -t) T=$2; shift;; -p) P=$2; shift;; -n) N=$2; shift;; esac; shift; done
sleep 1
echo 'build_commit,build_number,model_filename,model_type,model_size,model_n_params,n_threads,n_prompt,n_gen,avg_ts,stddev_ts'
echo "\"abc\",\"1\",\"$M\",\"qwen2 1B Q5_K - Medium\",\"516238848\",\"630167424\",\"$T\",\"$P\",\"0\",\"1.60\",\"0.004\""
echo "\"abc\",\"1\",\"$M\",\"qwen2 1B Q5_K - Medium\",\"516238848\",\"630167424\",\"$T\",\"0\",\"$N\",\"1.25\",\"0.004\""
EOF
cat > "$T/bin/llama-perplexity" <<'EOF'
#!/bin/bash
sleep 1; echo "Final estimate: PPL = 17.4321 +/- 0.5123"
EOF
cat > "$T/bin/llama-server" <<'EOF'
#!/usr/bin/env python3
import sys, json, time
from http.server import BaseHTTPRequestHandler, HTTPServer
a = sys.argv; port = int(a[a.index('--port') + 1]); t0 = time.time()
ANS = {'capital do brasil': 'Brasília.', 'capital da frança': 'Paris.', 'planeta vermelho': 'Marte.', 'maior oceano': 'Atlântico.'}
class H(BaseHTTPRequestHandler):
    def log_message(self, *x): pass
    def do_GET(self):
        ok = time.time() - t0 > 1.5
        self.send_response(200 if ok else 503); self.end_headers(); self.wfile.write(b'{}')
    def do_POST(self):
        b = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        q = b['messages'][-1]['content'].lower()
        ans = next((v for k, v in ANS.items() if k in q), 'Não tenho certeza.')
        r = {'choices': [{'message': {'content': ans}, 'finish_reason': 'stop'}],
             'timings': {'prompt_n': 30, 'predicted_n': 12, 'prompt_per_second': 1.6, 'predicted_per_second': 1.25}}
        self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers()
        self.wfile.write(json.dumps(r).encode())
HTTPServer(('127.0.0.1', port), H).serve_forever()
EOF
chmod +x "$T"/bin/*
head -c 100000 /dev/urandom > "$T/models/a.gguf"; head -c 80000 /dev/urandom > "$T/models/b.gguf"
cat > "$T/models.csv" <<EOF
name,file,quant,params_b,sha256,chat
modelo-a,$T/models/a.gguf,Q5_K_M,0.5,$(sha256sum "$T/models/a.gguf" | cut -d' ' -f1),chat
modelo-b,$T/models/b.gguf,Q4_0,0.36,,chat
EOF

env SYSROOT="$S" SUDO= BIN="$T/bin" RUNS="$T/runs" THREADS="1 2" BASE=1 POLL=1 DT=0.3 MAXWAIT=4 \
  QLIMIT=4 PORT=8794 READY_TIMEOUT=20 STAGES="verify bench eval ppl" PPL_FILE="$T/models/a.gguf" \
  "$HERE/pipeline.sh" "$T/models.csv" > "$T/saida.log" 2>&1
RUN=$(ls -d "$T"/runs/run_* | head -1)

ok=1
chk() { if eval "$2"; then echo "PASS  $1"; else echo "FAIL  $1"; ok=0; fi; }
chk "resultados.csv gerado"            "[ -s '$RUN/resultados.csv' ]"
chk "4 linhas (2 modelos x 2 threads)" "[ \$(tail -n +2 '$RUN/resultados.csv' | wc -l) -eq 4 ]"
chk "resumo.md gerado"                 "[ -s '$RUN/resumo.md' ]"
chk "hash confere (modelo-a)"          "grep -q 'hash_confere_manifesto: sim' '$RUN/modelo-a/meta.txt'"
chk "avaliação registrada (3/4)"       "grep -q '\"acertos\": 3' '$RUN/modelo-a/eval/eval_summary.json'"
chk "perplexidade lida"                "grep -q '17.4321' '$RUN/modelo-a/ppl.txt'"
chk "log térmico com colunas de memória" "head -1 '$RUN/modelo-a/log.csv' | grep -q 'proc_hwm_kB'"
chk "marcadores de janela de bench"    "grep -q 'bench_t2_fim' '$RUN/modelo-a/marcadores.csv'"
echo
if [ "$ok" = 1 ]; then echo "AUTOTESTE OK (pasta: $T)"; else echo "AUTOTESTE COM FALHAS: veja $T/saida.log"; exit 1; fi
